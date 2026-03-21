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
    samples: Iterable[Tuple[float, int, int]],
    max_events: int,
    count_all: bool = False,
) -> List[float] | Tuple[List[float], int]:
    """Extract rising-edge deltas between ch0 and ch1.

    When *count_all* is False (default), returns ``List[float]`` — at most
    *max_events* deltas (stops reading the CSV early).

    When *count_all* is True, continues scanning the entire CSV after
    collecting *max_events* deltas and returns ``(deltas, total_events)``
    where *total_events* is the total number of events found in the file
    (uncapped).
    """
    deltas: List[float] = []
    if max_events <= 0 and not count_all:
        return deltas

    total_count = 0
    capped = False
    waiting_for_both_low = True
    waiting_for_ch1_up = False
    t_ch0_up = 0.0
    prev_ch0 = None
    prev_ch1 = None

    for timestamp, ch0, ch1 in samples:
        if waiting_for_both_low:
            if prev_ch0 == 0 and prev_ch1 == 0 and ch0 == 1 and ch1 == 0:
                t_ch0_up = timestamp
                waiting_for_both_low = False
                waiting_for_ch1_up = True
            elif ch0 == 0 and ch1 == 0:
                waiting_for_both_low = True
                waiting_for_ch1_up = False
            else:
                waiting_for_both_low = True
                waiting_for_ch1_up = False

        elif waiting_for_ch1_up:
            if prev_ch0 == 1 and prev_ch1 == 0 and ch0 == 1 and ch1 == 1:
                total_count += 1
                if not capped:
                    deltas.append(timestamp - t_ch0_up)
                    if len(deltas) >= max_events:
                        if not count_all:
                            prev_ch0 = ch0
                            prev_ch1 = ch1
                            break
                        capped = True
                waiting_for_both_low = True
                waiting_for_ch1_up = False
            elif ch0 == 1 and ch1 == 1:
                waiting_for_both_low = True
                waiting_for_ch1_up = False

        prev_ch0 = ch0
        prev_ch1 = ch1

    if count_all:
        return deltas, total_count
    return deltas


def _compute_stats(
    deltas: List[float], unit: str = "s", threshold_ms: float | None = None
) -> Dict[str, float | None]:
    factor = {"s": 1.0, "ms": 1_000.0, "us": 1_000_000.0}[unit]
    converted = [d * factor for d in deltas]

    if not converted:
        result: Dict[str, float | None] = {
            "count": 0,
            "average": None,
            "stddev": None,
            "min": None,
            "max": None,
        }
        if threshold_ms is not None:
            result["outlier_threshold_ms"] = threshold_ms
            result["outlier_count"] = 0
        return result

    result = {
        "count": len(converted),
        "average": statistics.mean(converted),
        "stddev": statistics.pstdev(converted),
        "min": min(converted),
        "max": max(converted),
    }
    if threshold_ms is not None:
        # Count how many deltas exceed the threshold (compare in ms)
        deltas_ms = [d * 1_000.0 for d in deltas]
        outliers = sum(1 for d in deltas_ms if d > threshold_ms)
        result["outlier_threshold_ms"] = threshold_ms
        result["outlier_count"] = outliers
    return result


def analyze_csv(
    csv_path: str,
    max_events: int = 10000,
    unit: str = "ms",
    threshold_ms: float | None = None,
) -> Dict:
    if unit not in {"s", "ms", "us"}:
        raise ValueError("unit must be one of: s, ms, us")
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    samples = _read_samples(path)
    deltas, total_events = _extract_deltas(  # type: ignore[misc]
        samples, max_events=max_events, count_all=True
    )
    stats = _compute_stats(deltas, unit=unit, threshold_ms=threshold_ms)
    return {
        "csv_path": str(path.resolve()),
        "requested_max_events": max_events,
        "unit": unit,
        "total_events": total_events,
        **stats,
    }


def _format_features(features: Dict) -> str:
    if features["count"] == 0:
        return f"No matching sequences found in {features['csv_path']} (max_events={features['requested_max_events']})"

    line = f"count={features['count']}"
    if "total_events" in features:
        line += f" (total_events={features['total_events']})"
    line += (
        f" | average={features['average']:.6f} {features['unit']} "
        f"| stddev={features['stddev']:.6f} {features['unit']} "
        f"| min={features['min']:.6f} {features['unit']} "
        f"| max={features['max']:.6f} {features['unit']}"
    )
    if "outlier_count" in features and features.get("outlier_threshold_ms") is not None:
        line += (
            f" | outliers(>{features['outlier_threshold_ms']:.1f}ms)="
            f"{int(features['outlier_count'])}/{features['count']}"
        )
    return line


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze digital channel CSV and extract ch0/ch1 rising-edge deltas."
    )
    parser.add_argument(
        "csv_path",
        help="Path to Saleae CSV export containing Time [s], Channel 0, Channel 1",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=10000,
        help="Maximum number of ch0->ch1 rise events to include (default: 10000)",
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
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        metavar="MS",
        help="Count outliers exceeding this threshold in milliseconds (e.g. 300).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    features = analyze_csv(
        args.csv_path,
        max_events=args.max_events,
        unit=args.unit,
        threshold_ms=args.threshold,
    )
    if args.json:
        print(json.dumps(features, indent=2))
    else:
        print(_format_features(features))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
