import argparse
import logging
import os
import shlex
import signal
import subprocess
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a target command and capture measurements concurrently."
    )
    parser.add_argument(
        "--command",
        required=True,
        help="Target command to run. Provide as one quoted string, e.g. --command 'python app.py --arg 1'",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory for the target command (default: .)",
    )
    parser.add_argument(
        "--stabilization-delay",
        type=float,
        default=5.0,
        help="Seconds to wait after target start before launching measurement.",
    )
    parser.add_argument(
        "--workload-core",
        default="3",
        help="Core for workload (default: 3).",  # kept configurable for lab flexibility
    )
    parser.add_argument(
        "--measure-core",
        default=None,
        help="Core for measurement process; defaults to first available core != workload core.",
    )
    parser.add_argument(
        "--measure-python",
        default=sys.executable,
        help="Python interpreter for measurement process.",
    )
    return parser.parse_known_args()


def pick_non_workload_core(workload_core: str) -> str:
    if hasattr(os, "sched_getaffinity"):
        available = sorted(os.sched_getaffinity(0))
        for core in available:
            if str(core) != str(workload_core):
                return str(core)
    return "0"


def kill_process_group(
    proc: subprocess.Popen | None, label: str, timeout: float = 2.0
) -> None:
    if proc is None or proc.poll() is not None:
        return

    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None

    logging.warning("Cleaning up: killing %s process group", label)
    if pgid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            logging.exception("SIGTERM group kill failed for %s", label)
    else:
        proc.terminate()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if pgid:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                logging.exception("SIGKILL group kill failed for %s", label)
        else:
            proc.kill()


def start_workload(command: str, cwd: str, workload_core: str) -> subprocess.Popen:
    target = shlex.split(command)
    if not target:
        raise ValueError("--command must not be empty")

    workload_cmd = ["chrt", "-f", "99", "taskset", "-c", str(workload_core)] + target
    logging.info(
        "Starting workload on core %s: %s", workload_core, " ".join(workload_cmd)
    )
    return subprocess.Popen(
        workload_cmd,
        cwd=cwd,
        stdout=None,
        stderr=None,
        start_new_session=True,
    )


def start_measurement(measure_python: str, measure_core: str, measure_args):
    measure_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "measure.py"
    )
    measure_cmd = [measure_python, measure_script] + measure_args
    if measure_core is not None:
        measure_cmd = ["taskset", "-c", str(measure_core)] + measure_cmd

    logging.info("Starting measurement: %s", " ".join(measure_cmd))
    return subprocess.Popen(
        measure_cmd,
        stdout=None,
        stderr=None,
        start_new_session=True,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args, measure_args = parse_args()
    measure_core = args.measure_core or pick_non_workload_core(args.workload_core)

    logging.info("Orchestrator args: command=%r cwd=%r", args.command, args.cwd)
    logging.info("Orchestrator passed measurement args: %s", measure_args)
    logging.info("Resolved measure core: %s", measure_core)

    workload_proc = None
    measure_proc = None

    try:
        workload_proc = start_workload(args.command, args.cwd, args.workload_core)
        logging.info("Workload PID: %s", workload_proc.pid)

        delay_end = time.monotonic() + max(0.0, args.stabilization_delay)
        logging.info(
            "Waiting %.2f seconds for workload stabilization", args.stabilization_delay
        )
        while time.monotonic() < delay_end:
            rc = workload_proc.poll()
            if rc is not None:
                logging.error("Workload exited early with code %s", rc)
                raise RuntimeError("Workload failed before measurement started")
            time.sleep(0.1)

        measure_proc = start_measurement(
            args.measure_python, measure_core, measure_args
        )
        logging.info("Measurement PID: %s", measure_proc.pid)

        while True:
            workload_rc = workload_proc.poll()
            if workload_rc is not None:
                logging.error(
                    "Workload exited while measurement is running (code=%s)",
                    workload_rc,
                )
                raise RuntimeError("Workload failed during measurement")

            measure_rc = measure_proc.poll()
            if measure_rc is not None:
                logging.info("Measurement finished with code %s", measure_rc)
                break

            time.sleep(0.1)

    except (RuntimeError, ValueError) as exc:
        logging.error("Orchestration failed: %s", exc)
        kill_process_group(measure_proc, "measurement")
        kill_process_group(workload_proc, "workload")
        return 1

    except Exception:
        logging.exception("Unexpected orchestration failure")
        kill_process_group(measure_proc, "measurement")
        kill_process_group(workload_proc, "workload")
        return 1

    finally:
        if measure_proc and measure_proc.poll() is None:
            logging.info("Measurement still running after loop exit, terminating")
            kill_process_group(measure_proc, "measurement")

        if workload_proc and workload_proc.poll() is None:
            logging.info("Killing workload after measurement completion")
            kill_process_group(workload_proc, "workload")

    if workload_proc and workload_proc.returncode is not None:
        logging.warning("Workload final return code: %s", workload_proc.returncode)
    if measure_proc is None:
        return 1

    measure_return = measure_proc.returncode
    logging.info("Orchestration complete, measurement return code: %s", measure_return)
    return int(measure_return or 0)


if __name__ == "__main__":
    raise SystemExit(main())
