import argparse
import os
import time
from saleae import automation
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Saleae capture and export raw CSV data."
    )
    parser.add_argument(
        "--export-dir",
        required=True,
        help="Directory where raw CSV export will be saved.",
    )
    parser.add_argument(
        "--test-device",
        action="store_true",
        help="Use the test device ID (F4241). If omitted, device_id is None.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=3,
        help="How many seconds to capture (default: 3).",
    )
    return parser.parse_args()


CHANNELS = [0, 1]


def main() -> int:
    args = parse_args()

    print(
        "Starting capture",
        f"(seconds={args.seconds})",
        "channels",
        CHANNELS,
        flush=True,
    )

    try:
        # Connect to Logic 2
        with automation.Manager.connect(port=10430) as s:
            print("Connected to Logic 2.", flush=True)

            # Configure device
            device_config = automation.LogicDeviceConfiguration(
                enabled_digital_channels=CHANNELS,  # CH1 = estop, CH2 = dangerous output device
                digital_sample_rate=10_000_000,  # 10 MHz — adjust as needed
                digital_threshold_volts=3.3,
            )

            # Capture for requested duration
            capture_config = automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=args.seconds)
            )

            device_id = "F4241" if args.test_device else None
            if args.test_device:
                print("Test device is in use.", flush=True)

            with s.start_capture(
                device_id=device_id,
                device_configuration=device_config,
                capture_configuration=capture_config,
            ) as capture:
                print("Capture started.", flush=True)
                capture.wait()
                print("Capture complete.", flush=True)

                # Export raw digital data to CSV
                capture.export_raw_data_csv(
                    directory=os.path.abspath(args.export_dir),
                    digital_channels=CHANNELS,
                )
                print(f"Raw data exported to {args.export_dir}", flush=True)

                # Wait some and exit - saleae wont exit on its own
                time.sleep(0.1)
                return 0

    except Exception as exc:
        print(f"Measurement failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
