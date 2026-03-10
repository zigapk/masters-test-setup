"""Measurement campaign runner for Go and Hertz (React) measurements.

Generates the full parameter-space job list, skips already-completed runs
(those whose data/<dirname>/digital.csv already exists), shows a progress bar
with an accurate ETA that is not distorted by skipped runs, and exits
immediately on any measurement failure so the hardware can be reset and the
campaign resumed later.

Usage (from within ``nix develop`` shell):
    cd measurement
    uv run campaign.py            # real campaign
    uv run campaign.py --dry-run  # just print the job list
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from tqdm import tqdm

# Paths
BASE_DIR = Path("/home/zigapk/masters-test-setup")
MEASUREMENT_DIR = BASE_DIR / "measurement"
GO_RUNNER_DIR = BASE_DIR / "go-runner"
HERTZ_RUNNER_DIR = BASE_DIR / "hertz-runner"
DATA_DIR = MEASUREMENT_DIR / "data"

# Parameters
N_VALUES = [0, 10, 20, 40, 50, 75, 100]

# Calibration: 143 events in 100 seconds => 1.43 events/sec.
EVENTS_PER_SEC = 145 / 100


def _seconds_for_events(target_events: int) -> int:
    raw = target_events / EVENTS_PER_SEC
    return int(raw * 1.05) + 1  # ceiling + margin


SECONDS_10K = _seconds_for_events(10_000)
SECONDS_500 = _seconds_for_events(500)


# Job generation
def _go_jobs() -> List[Dict[str, Any]]:
    """Go pin-follow jobs: vary n over N_VALUES."""
    jobs: List[Dict[str, Any]] = []
    for n in N_VALUES:
        jobs.append(
            {
                "dirname": f"campaign-go-n{n}",
                "build_cmd": "go build -o pin-follow ./cmd/pin-follow",
                "build_cwd": str(GO_RUNNER_DIR),
                "run_cmd": f"./pin-follow -n {n}",
                "run_cwd": str(GO_RUNNER_DIR),
                "seconds": SECONDS_10K,
                "min_events": 10_000,
            }
        )
    return jobs


def _hertz_jobs() -> List[Dict[str, Any]]:
    """All Hertz (React) jobs."""
    jobs: List[Dict[str, Any]] = []

    # --- follow, shallow ---
    for n in N_VALUES:
        jobs.append(
            {
                "dirname": f"campaign-hertz-follow-shallow-n{n}",
                "build_cmd": "pnpm build",
                "build_cwd": str(HERTZ_RUNNER_DIR),
                "run_cmd": f"pnpm follow -n {n} -f shallow",
                "run_cwd": str(HERTZ_RUNNER_DIR),
                "seconds": SECONDS_10K,
                "min_events": 10_000,
            }
        )

    # --- follow, deep ---
    for n in N_VALUES:
        jobs.append(
            {
                "dirname": f"campaign-hertz-follow-deep-n{n}",
                "build_cmd": "pnpm build",
                "build_cwd": str(HERTZ_RUNNER_DIR),
                "run_cmd": f"pnpm follow -n {n} -f deep",
                "run_cwd": str(HERTZ_RUNNER_DIR),
                "seconds": SECONDS_10K,
                "min_events": 10_000,
            }
        )

    # --- follow-using-error-boundary, shallow ---
    for n in N_VALUES:
        jobs.append(
            {
                "dirname": f"campaign-hertz-eb-shallow-n{n}",
                "build_cmd": "pnpm build",
                "build_cwd": str(HERTZ_RUNNER_DIR),
                "run_cmd": f"pnpm follow-using-error-boundary -n {n} -f shallow",
                "run_cwd": str(HERTZ_RUNNER_DIR),
                "seconds": SECONDS_10K,
                "min_events": 10_000,
            }
        )

    # --- follow-using-error-boundary, deep, d=0 ---
    for n in N_VALUES:
        jobs.append(
            {
                "dirname": f"campaign-hertz-eb-deep-d0-n{n}",
                "build_cmd": "pnpm build",
                "build_cwd": str(HERTZ_RUNNER_DIR),
                "run_cmd": f"pnpm follow-using-error-boundary -n {n} -f deep -d 0",
                "run_cwd": str(HERTZ_RUNNER_DIR),
                "seconds": SECONDS_10K,
                "min_events": 10_000,
            }
        )

    # --- follow-using-error-boundary, n=50, deep, vary d (0..49) ---
    for d in range(50):
        jobs.append(
            {
                "dirname": f"campaign-hertz-eb-deep-n50-d{d}",
                "build_cmd": "pnpm build",
                "build_cwd": str(HERTZ_RUNNER_DIR),
                "run_cmd": f"pnpm follow-using-error-boundary -n 50 -f deep -d {d}",
                "run_cwd": str(HERTZ_RUNNER_DIR),
                "seconds": SECONDS_500,
                "min_events": 500,
            }
        )

    return jobs


def generate_jobs() -> List[Dict[str, Any]]:
    """Return the full ordered job list: Go first, then Hertz."""
    return _go_jobs() + _hertz_jobs()


# Completion check
def _is_complete(dirname: str) -> bool:
    """Return True if data/<dirname>/digital.csv already exists."""
    return (DATA_DIR / dirname / "digital.csv").is_file()


# Execution helpers
_ANALYSIS_RE = re.compile(r"Analysis features:\s*(\{.*\})")


def _parse_analysis(output: str) -> Dict[str, Any] | None:
    """Extract the analysis JSON dict from orchestrator output."""
    match = _ANALYSIS_RE.search(output)
    if match:
        try:
            # The orchestrator prints Python-style dicts (single quotes).
            # Replace single quotes with double quotes for JSON parsing.
            raw = match.group(1).replace("'", '"')
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _run_job(job: Dict[str, Any]) -> None:
    """Execute a single build+measure job.  Raises on any failure."""
    dirname = job["dirname"]

    # --- Build step ---
    print(f"\n{'=' * 60}")
    print(f"[BUILD] {dirname}")
    print(f"  cmd:  {job['build_cmd']}")
    print(f"  cwd:  {job['build_cwd']}")
    print(f"{'=' * 60}")

    build_result = subprocess.run(
        job["build_cmd"],
        shell=True,
        cwd=job["build_cwd"],
    )
    if build_result.returncode != 0:
        print(
            f"\nFATAL: Build failed for {dirname} (exit {build_result.returncode})",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Measurement step ---
    orchestrate_cmd = (
        f"uv run orchestrate.py"
        f" --command '{job['run_cmd']}'"
        f" --cwd {job['run_cwd']}"
        f" --export-dir ./data/{dirname}"
        f" --seconds {job['seconds']}"
    )

    print(f"\n{'=' * 60}")
    print(f"[MEASURE] {dirname}")
    print(f"  cmd:     {orchestrate_cmd}")
    print(f"  seconds: {job['seconds']}  (need >= {job['min_events']} events)")
    print(f"{'=' * 60}")

    measure_result = subprocess.run(
        orchestrate_cmd,
        shell=True,
        cwd=str(MEASUREMENT_DIR),
        capture_output=True,
        text=True,
    )

    # Print captured output so it's visible in the log.
    if measure_result.stdout:
        print(measure_result.stdout, end="")
    if measure_result.stderr:
        print(measure_result.stderr, end="", file=sys.stderr)

    if measure_result.returncode != 0:
        print(
            f"\nFATAL: Measurement failed for {dirname} (exit {measure_result.returncode})",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Validate event count ---
    analysis = _parse_analysis(measure_result.stdout)
    if analysis is None:
        # Also try stderr since orchestrator may log there.
        analysis = _parse_analysis(measure_result.stderr)

    if analysis is None:
        print(
            f"\nFATAL: Could not parse analysis output for {dirname}", file=sys.stderr
        )
        sys.exit(1)

    count = analysis.get("count", 0)
    if count == 0:
        print(f"\nFATAL: Zero events captured for {dirname}", file=sys.stderr)
        sys.exit(1)

    if count < job["min_events"]:
        print(
            f"\nWARNING: Only {count} events captured for {dirname} "
            f"(wanted >= {job['min_events']}). Continuing anyway.",
            file=sys.stderr,
        )

    print(f"\n[OK] {dirname}: {count} events captured.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full measurement campaign.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the job list without executing anything.",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="Smoke-test mode: override pending jobs to 20s capture / 25 min events.",
    )
    args = parser.parse_args()

    jobs = generate_jobs()

    # --short: override seconds and min_events for jobs that haven't completed yet.
    if args.short:
        for job in jobs:
            if not _is_complete(job["dirname"]):
                job["seconds"] = 20
                job["min_events"] = 25

    if args.dry_run:
        done = 0
        pending = 0
        for i, job in enumerate(jobs, 1):
            complete = _is_complete(job["dirname"])
            status = "DONE" if complete else "PENDING"
            if complete:
                done += 1
            else:
                pending += 1
            print(
                f"{i:3d}. [{status:7s}] {job['dirname']:<45s}  "
                f"cmd={job['run_cmd']!r}  seconds={job['seconds']}  min_events={job['min_events']}"
            )
        print(f"\nTotal: {len(jobs)} jobs  |  Done: {done}  |  Pending: {pending}")

        # Estimate remaining time.
        remaining_sec = sum(
            j["seconds"] for j in jobs if not _is_complete(j["dirname"])
        )
        remaining_h = remaining_sec / 3600
        print(f"Estimated remaining time: {remaining_sec}s ({remaining_h:.1f}h)")
        return 0

    # --- Real run ---
    total = len(jobs)
    already_done = sum(1 for j in jobs if _is_complete(j["dirname"]))
    remaining = total - already_done

    print(
        f"Campaign: {total} total jobs, {already_done} already complete, {remaining} to run."
    )
    if remaining == 0:
        print("Nothing to do - all jobs already have results.")
        return 0

    # Progress bar: set initial to already_done so the bar starts partially filled.
    # tqdm will compute ETA based only on the jobs that actually execute (the ones
    # that call bar.update(1)), which gives an accurate time estimate.
    bar = tqdm(
        total=total,
        initial=already_done,
        unit="job",
        desc="Campaign",
        dynamic_ncols=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    )

    try:
        for job in jobs:
            if _is_complete(job["dirname"]):
                continue  # already counted in initial

            _run_job(job)
            bar.update(1)

    except KeyboardInterrupt:
        bar.close()
        completed_now = bar.n - already_done
        print(
            f"\n\nCampaign interrupted. Completed {completed_now} new jobs this session."
        )
        print("Re-run this script to resume from where you left off.")
        return 1
    finally:
        bar.close()

    print(f"\n\nCampaign complete! All {total} jobs finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
