"""Extract timing features from Saleae digital channel CSV captures."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def _parse_value(raw: str) -> int:
    value = float(raw)
    if value not in (0.0, 1.0):
        raise ValueError(f"Non-binary value '{raw}'")
    return int(value)


def _normalize_column(name: str) -> str:
    return name.strip().lower().replace("_", "").replace(" ", "")


def _read_samples(csv_path: Path) -> Iterable[Tuple[float, int, int]]:
    with csv_path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file '{csv_path}' has no header row")

        columns = {_normalize_column(name): name for name in reader.fieldnames}

        time_col = columns.get("time[s]") or columns.get("time")
        ch0_col = columns.get("channel0") or columns.get("ch0")
        ch1_col = columns.get("channel1") or columns.get("ch1")

        if not (time_col and ch0_col and ch1_col):
            raise ValueError(
                "CSV is missing required columns. Expected Time [s], Channel 0, Channel 1"
            )

        for row in reader:
            try:
                timestamp = float(row[time_col])
                ch0 = _parse_value(row[ch0_col])
                ch1 = _parse_value(row[ch1_col])
            except Exception:
                continue
            yield timestamp, ch0, ch1


def _extract_deltas(
    samples: Iterable[Tuple[float, int, int]], max_events: int
) -> List[float]:
    deltas: List[float] = []
    if max_events <= 0:
        return deltas

    waiting_for_ch0_down = True
    waiting_for_ch1_down = False
    t_ch0_down = 0.0
    prev_ch0 = None
    prev_ch1 = None

    for timestamp, ch0, ch1 in samples:
        if waiting_for_ch0_down:
            if prev_ch0 == 1 and prev_ch1 == 1 and ch0 == 0 and ch1 == 1:
                t_ch0_down = timestamp
                waiting_for_ch0_down = False
                waiting_for_ch1_down = True
            elif ch0 == 1 and ch1 == 1:
                waiting_for_ch0_down = True
                waiting_for_ch1_down = False
            else:
                waiting_for_ch0_down = True
                waiting_for_ch1_down = False

        elif waiting_for_ch1_down:
            if prev_ch0 == 0 and prev_ch1 == 1 and ch0 == 0 and ch1 == 0:
                deltas.append(timestamp - t_ch0_down)
                if len(deltas) >= max_events:
                    break
                waiting_for_ch0_down = True
                waiting_for_ch1_down = False
            elif ch0 == 1 and ch1 == 1:
                waiting_for_ch0_down = True
                waiting_for_ch1_down = False

        prev_ch0 = ch0
        prev_ch1 = ch1

    return deltas


def _compute_stats(deltas: List[float], unit: str = "s") -> Dict[str, float | None]:
    factor = {"s": 1.0, "ms": 1_000.0, "us": 1_000_000.0}[unit]
    converted = [d * factor for d in deltas]

    if not converted:
        return {
            "count": 0,
            "average": None,
            "stddev": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(converted),
        "average": statistics.mean(converted),
        "stddev": statistics.pstdev(converted),
        "min": min(converted),
        "max": max(converted),
    }


def analyze_csv(csv_path: str, max_events: int = 10000, unit: str = "ms") -> Dict:
    if unit not in {"s", "ms", "us"}:
        raise ValueError("unit must be one of: s, ms, us")
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    samples = _read_samples(path)
    deltas = _extract_deltas(samples, max_events=max_events)
    stats = _compute_stats(deltas, unit=unit)
    return {
        "csv_path": str(path.resolve()),
        "requested_max_events": max_events,
        "unit": unit,
        **stats,
    }


def _format_features(features: Dict) -> str:
    if features["count"] == 0:
        return f"No matching sequences found in {features['csv_path']} (max_events={features['requested_max_events']})"

    return (
        f"count={features['count']} | average={features['average']:.6f} {features['unit']} "
        f"| stddev={features['stddev']:.6f} {features['unit']} "
        f"| min={features['min']:.6f} {features['unit']} "
        f"| max={features['max']:.6f} {features['unit']}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze digital channel CSV and extract ch0/ch1 falling-edge deltas."
    )
    parser.add_argument(
        "csv_path",
        help="Path to Saleae CSV export containing Time [s], Channel 0, Channel 1",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=10000,
        help="Maximum number of ch0->ch1 drop events to include (default: 10000)",
    )
    parser.add_argument(
        "--unit",
        choices=("s", "ms", "us"),
        default="ms",
        help="Output units: seconds (s), milliseconds (ms), or microseconds (us).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output instead of compact one-line output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    features = analyze_csv(args.csv_path, max_events=args.max_events, unit=args.unit)
    if args.json:
        print(json.dumps(features, indent=2))
    else:
        print(_format_features(features))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
