"""Generate latency charts from campaign measurement data.

Reads digital.csv files produced by the campaign runner, computes statistics
(mean, stddev, median, percentiles, max) from raw latency deltas, and
produces publication-ready charts in PDF, SVG and PNG.

Charts are written to measurement/charts/ and overwritten on each run.
Missing datasets are silently skipped — the script draws whatever data is
available.

Usage (from within ``nix develop`` shell):
    cd measurement
    uv run plot_charts.py
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")

from matplotlib.axes import Axes
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ---------------------------------------------------------------------------
# Import raw-delta extraction from the analyzer so we can compute arbitrary
# statistics ourselves.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from digital_analyzer import _read_samples, _extract_deltas  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
MEASUREMENT_DIR = BASE_DIR / "measurement"
DATA_DIR = MEASUREMENT_DIR / "data"
CHARTS_DIR = MEASUREMENT_DIR / "charts"

# ---------------------------------------------------------------------------
# Campaign parameters (must match campaign.py)
# ---------------------------------------------------------------------------
N_VALUES = [0, 10, 20, 40, 50, 75, 100]
ERROR_BOUNDARY_DEPTH_N_VALUES = [10, 20, 30, 40, 50, 60]
MAX_EVENTS = 10_000
MAX_EVENTS_DEPTH = 500


def _depth_range_for_n(n: int) -> range:
    """Return the depth values to measure for a given N.

    Kept as ``range(n)`` to match the historical convention in existing data
    (e.g. previous deep depth sweep used d=0..49 for N=50).
    """

    return range(n)


def _depth_count_for_n(n: int) -> int:
    """Return number of depth points for the given N."""

    return len(_depth_range_for_n(n))


# ---------------------------------------------------------------------------
# Series definitions for the "Latency vs N" charts.
# Each entry: (series_label, dirname_template, color, marker)
# dirname_template uses {n} as placeholder for the N value.
# ---------------------------------------------------------------------------
SERIES_VS_N: List[Tuple[str, str, str, str]] = [
    ("Go", "campaign-go-n{n}", "#1f77b4", "o"),
    ("Hertz follow shallow", "campaign-hertz-follow-shallow-n{n}", "#ff7f0e", "s"),
    ("Hertz follow deep", "campaign-hertz-follow-deep-n{n}", "#2ca02c", "^"),
    ("Hertz EB shallow", "campaign-hertz-eb-shallow-n{n}", "#d62728", "D"),
    ("Hertz EB deep (d=0)", "campaign-hertz-eb-deep-d0-n{n}", "#9467bd", "v"),
]

# Single series for the "Latency vs Depth" charts.
DEPTH_SERIES_COLOR = "#1f77b4"
DEPTH_SERIES_MARKER = "o"
DEPTH_SERIES_COLOR_BY_N: Dict[int, str] = {
    10: "#1f77b4",
    20: "#ff7f0e",
    30: "#2ca02c",
    40: "#d62728",
    50: "#9467bd",
    60: "#8c564b",
}
DEPTH_SERIES_MARKER_BY_N: Dict[int, str] = {
    10: "o",
    20: "s",
    30: "^",
    40: "D",
    50: "v",
    60: "x",
}
DEPTH_SERIES_LABEL_PREFIX = "Hertz EB deep"

# ---------------------------------------------------------------------------
# Outlier threshold
# ---------------------------------------------------------------------------
OUTLIER_THRESHOLD_MS = 300.0  # count data points exceeding this value (ms)

# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------
FORMATS = ["pdf", "svg", "png"]
DPI = 300  # for PNG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_deltas_ms(
    csv_path: Path, max_events: int
) -> Optional[Tuple[List[float], int]]:
    """Load a CSV and return (latency deltas in ms, total_events_in_file), or None."""
    if not csv_path.is_file():
        return None
    try:
        samples = _read_samples(csv_path)
        deltas, total_events = _extract_deltas(  # type: ignore[misc]
            samples, max_events=max_events, count_all=True
        )
    except Exception as exc:
        print(f"  WARNING: failed to read {csv_path}: {exc}")
        return None
    if isinstance(deltas, (int, float)):
        deltas = [float(deltas)]
    if not deltas:
        return None
    deltas_ms = [d * 1000.0 for d in list(deltas)]
    return deltas_ms, int(total_events)  # s → ms


def _depth_color(n: int) -> str:
    """Color for one EB-deep depth series."""

    return DEPTH_SERIES_COLOR_BY_N.get(n, DEPTH_SERIES_COLOR)


def _depth_marker(n: int) -> str:
    """Marker for one EB-deep depth series."""

    return DEPTH_SERIES_MARKER_BY_N.get(n, DEPTH_SERIES_MARKER)


def _depth_label(n: int) -> str:
    """Legend label for one EB-deep depth series."""

    return f"{DEPTH_SERIES_LABEL_PREFIX} (n={n})"


def _compute_full_stats(deltas: List[float], total_events: int) -> Dict[str, float]:
    """Compute all statistics we need from a list of latency values (ms).

    *total_events* is the total number of events found in the CSV
    (may be larger than len(deltas) if the capture was capped).
    """
    arr = np.array(deltas)
    outlier_count = int(np.sum(arr > OUTLIER_THRESHOLD_MS))
    return {
        "count": len(arr),
        "total_events": total_events,
        "mean": float(np.mean(arr)),
        "stddev": float(np.std(arr)),
        "median": float(np.median(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "p0_1": float(np.percentile(arr, 0.1)),
        "p1": float(np.percentile(arr, 1)),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "p99_9": float(np.percentile(arr, 99.9)),
        "outlier_count": outlier_count,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_vs_n_data() -> Dict[str, List[Optional[Dict[str, float]]]]:
    """For each series, load stats for every N value.

    Returns {series_label: [stats_or_None_for_each_N]}.
    """
    result: Dict[str, List[Optional[Dict[str, float]]]] = {}
    for label, tmpl, _color, _marker in SERIES_VS_N:
        series_stats: List[Optional[Dict[str, float]]] = []
        for n in N_VALUES:
            dirname = tmpl.format(n=n)
            csv_path = DATA_DIR / dirname / "digital.csv"
            loaded = _load_deltas_ms(csv_path, MAX_EVENTS)
            if loaded is not None:
                deltas, total_events = loaded
                stats = _compute_full_stats(deltas, total_events)
                series_stats.append(stats)
                if stats["outlier_count"] > 0:
                    print(
                        f"  {dirname}: {int(stats['outlier_count'])}/{int(stats['count'])} "
                        f"outliers (>{OUTLIER_THRESHOLD_MS:.0f} ms)"
                    )
            else:
                series_stats.append(None)
        result[label] = series_stats
    return result


def load_vs_depth_data() -> Dict[int, List[Optional[Dict[str, float]]]]:
    """Load EB-deep depth stats for the configured N values."""
    result: Dict[int, List[Optional[Dict[str, float]]]] = {}

    for n in ERROR_BOUNDARY_DEPTH_N_VALUES:
        depth_stats: List[Optional[Dict[str, float]]] = []
        for d in _depth_range_for_n(n):
            dirname = f"campaign-hertz-eb-deep-n{n}-d{d}"
            csv_path = DATA_DIR / dirname / "digital.csv"
            loaded = _load_deltas_ms(csv_path, MAX_EVENTS_DEPTH)
            if loaded is not None:
                deltas, total_events = loaded
                stats = _compute_full_stats(deltas, total_events)
                depth_stats.append(stats)
                if stats["outlier_count"] > 0:
                    print(
                        f"  {dirname}: {int(stats['outlier_count'])}/{int(stats['count'])} "
                        f"outliers (>{OUTLIER_THRESHOLD_MS:.0f} ms)"
                    )
            else:
                depth_stats.append(None)
        result[n] = depth_stats
    return result


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _series_color(label: str) -> str:
    for l, _t, c, _m in SERIES_VS_N:
        if l == label:
            return c
    return "#333333"


def _series_marker(label: str) -> str:
    for l, _t, _c, m in SERIES_VS_N:
        if l == label:
            return m
    return "o"


def _apply_common_style(ax: Axes, xlabel: str, ylabel: str, title: str) -> None:
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.legend(fontsize=9, loc="best")
    ax.tick_params(labelsize=10)


def _save_chart(fig: Figure, name: str) -> None:
    for fmt in FORMATS:
        out = CHARTS_DIR / f"{name}.{fmt}"
        fig.savefig(out, format=fmt, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {name}.{{pdf,svg,png}}")


def _add_linear_fit(
    ax: Axes,
    x_vals: List[float],
    y_vals: List[float],
    color: str,
    label: str = "",
) -> None:
    """Add a dashed linear fit line to the axes."""
    if len(x_vals) < 2:
        return
    coeffs = np.polyfit(x_vals, y_vals, 1)
    x_fit = np.linspace(min(x_vals), max(x_vals), 200)
    y_fit = np.polyval(coeffs, x_fit)
    ax.plot(x_fit, y_fit, color=color, linestyle="--", linewidth=1.2, alpha=0.6)


# ---------------------------------------------------------------------------
# Chart generators: Latency vs N
# ---------------------------------------------------------------------------


def _plot_vs_n_mean(
    data: Dict[str, List[Optional[Dict[str, float]]]],
    fit: bool = False,
    show_stddev: bool = True,
) -> Optional[str]:
    """Mean latency, optionally with stddev error bars."""
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for label, stats_list in data.items():
        xs, ys, errs = [], [], []
        for i, s in enumerate(stats_list):
            if s is not None:
                xs.append(N_VALUES[i])
                ys.append(s["mean"])
                errs.append(s["stddev"])
        if not xs:
            continue
        has_data = True
        color = _series_color(label)
        marker = _series_marker(label)
        if show_stddev:
            ax.errorbar(
                xs,
                ys,
                yerr=errs,
                label=label,
                color=color,
                marker=marker,
                markersize=5,
                capsize=3,
                linestyle="none",
                elinewidth=1.0,
            )
        else:
            ax.plot(
                xs,
                ys,
                label=label,
                color=color,
                marker=marker,
                markersize=5,
                linestyle="none",
            )
        if fit:
            _add_linear_fit(ax, xs, ys, color)

    if not has_data:
        plt.close(fig)
        return None

    _apply_common_style(
        ax,
        xlabel="Component count (N)",
        ylabel="Latency (ms)",
        title=(
            "E-stop latency vs component count — Mean"
            if not show_stddev
            else "E-stop latency vs component count — Mean ± StdDev"
        ),
    )
    ax.set_xticks(N_VALUES)
    if not show_stddev:
        name = "latency_vs_n_mean_nostd_fit" if fit else "latency_vs_n_mean_nostd"
    else:
        name = "latency_vs_n_mean_fit" if fit else "latency_vs_n_mean"
    _save_chart(fig, name)
    return name


def _plot_vs_n_median(
    data: Dict[str, List[Optional[Dict[str, float]]]],
    plo_key: str,
    phi_key: str,
    plo_label: str,
    phi_label: str,
    suffix: str,
    fit: bool = False,
) -> Optional[str]:
    """Median + percentile whiskers."""
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for label, stats_list in data.items():
        xs, medians, lo_errs, hi_errs = [], [], [], []
        for i, s in enumerate(stats_list):
            if s is not None:
                xs.append(N_VALUES[i])
                med = s["median"]
                medians.append(med)
                lo_errs.append(med - s[plo_key])
                hi_errs.append(s[phi_key] - med)
        if not xs:
            continue
        has_data = True
        color = _series_color(label)
        marker = _series_marker(label)
        ax.errorbar(
            xs,
            medians,
            yerr=[lo_errs, hi_errs],
            label=label,
            color=color,
            marker=marker,
            markersize=5,
            capsize=3,
            linestyle="none",
            elinewidth=1.0,
        )
        if fit:
            _add_linear_fit(ax, xs, medians, color)

    if not has_data:
        plt.close(fig)
        return None

    _apply_common_style(
        ax,
        xlabel="Component count (N)",
        ylabel="Latency (ms)",
        title=f"E-stop latency vs component count — Median ({plo_label}–{phi_label})",
    )
    ax.set_xticks(N_VALUES)
    name = (
        f"latency_vs_n_median_{suffix}_fit" if fit else f"latency_vs_n_median_{suffix}"
    )
    _save_chart(fig, name)
    return name


def _plot_vs_n_max(
    data: Dict[str, List[Optional[Dict[str, float]]]],
    fit: bool = False,
) -> Optional[str]:
    """Max latency."""
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for label, stats_list in data.items():
        xs, ys = [], []
        for i, s in enumerate(stats_list):
            if s is not None:
                xs.append(N_VALUES[i])
                ys.append(s["max"])
        if not xs:
            continue
        has_data = True
        color = _series_color(label)
        marker = _series_marker(label)
        ax.plot(
            xs,
            ys,
            label=label,
            color=color,
            marker=marker,
            markersize=5,
            linestyle="none",
        )
        if fit:
            _add_linear_fit(ax, xs, ys, color)

    if not has_data:
        plt.close(fig)
        return None

    _apply_common_style(
        ax,
        xlabel="Component count (N)",
        ylabel="Latency (ms)",
        title="E-stop latency vs component count — Max",
    )
    ax.set_xticks(N_VALUES)
    name = "latency_vs_n_max_fit" if fit else "latency_vs_n_max"
    _save_chart(fig, name)
    return name


# ---------------------------------------------------------------------------
# Chart generators: Latency vs Depth
# ---------------------------------------------------------------------------


def _plot_vs_depth_mean(
    depth_data: Dict[int, List[Optional[Dict[str, float]]]],
    fit: bool = False,
    show_stddev: bool = True,
) -> Optional[str]:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for n, stats in depth_data.items():
        xs, ys, errs = [], [], []
        for d, s in enumerate(stats):
            if s is not None:
                xs.append(d)
                ys.append(s["mean"])
                errs.append(s["stddev"])
        if not xs:
            continue
        has_data = True
        color = _depth_color(n)
        marker = _depth_marker(n)
        if show_stddev:
            ax.errorbar(
                xs,
                ys,
                yerr=errs,
                label=_depth_label(n),
                color=color,
                marker=marker,
                markersize=4,
                capsize=2,
                linestyle="none",
                elinewidth=0.8,
            )
        else:
            ax.plot(
                xs,
                ys,
                label=_depth_label(n),
                color=color,
                marker=marker,
                markersize=4,
                linestyle="none",
            )
        if fit:
            _add_linear_fit(ax, xs, ys, color)

    if not has_data:
        plt.close(fig)
        return None

    if not depth_data:
        plt.close(fig)
        return None
    max_depth = max(_depth_count_for_n(n) for n in depth_data)
    if max_depth > 0:
        ax.set_xticks(range(max_depth))

    _apply_common_style(
        ax,
        xlabel="Error boundary depth (D)",
        ylabel="Latency (ms)",
        title=(
            "E-stop latency vs error-boundary depth — Mean"
            if not show_stddev
            else "E-stop latency vs error-boundary depth — Mean ± StdDev"
        ),
    )
    if not show_stddev:
        name = (
            "latency_vs_depth_mean_nostd_fit" if fit else "latency_vs_depth_mean_nostd"
        )
    else:
        name = "latency_vs_depth_mean_fit" if fit else "latency_vs_depth_mean"
    _save_chart(fig, name)
    return name


def _plot_vs_depth_median(
    depth_data: Dict[int, List[Optional[Dict[str, float]]]],
    plo_key: str,
    phi_key: str,
    plo_label: str,
    phi_label: str,
    suffix: str,
    fit: bool = False,
) -> Optional[str]:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for n, stats in depth_data.items():
        xs, medians, lo_errs, hi_errs = [], [], [], []
        for d, s in enumerate(stats):
            if s is not None:
                xs.append(d)
                med = s["median"]
                medians.append(med)
                lo_errs.append(med - s[plo_key])
                hi_errs.append(s[phi_key] - med)
        if not xs:
            continue
        has_data = True
        color = _depth_color(n)
        marker = _depth_marker(n)

        ax.errorbar(
            xs,
            medians,
            yerr=[lo_errs, hi_errs],
            label=_depth_label(n),
            color=color,
            marker=marker,
            markersize=4,
            capsize=2,
            linestyle="none",
            elinewidth=0.8,
        )
        if fit:
            _add_linear_fit(ax, xs, medians, color)

    if not has_data:
        plt.close(fig)
        return None

    if not depth_data:
        plt.close(fig)
        return None
    max_depth = max(_depth_count_for_n(n) for n in depth_data)
    if max_depth > 0:
        ax.set_xticks(range(max_depth))

    _apply_common_style(
        ax,
        xlabel="Error boundary depth (D)",
        ylabel="Latency (ms)",
        title=f"E-stop latency vs error-boundary depth — Median ({plo_label}–{phi_label})",
    )
    name = (
        f"latency_vs_depth_median_{suffix}_fit"
        if fit
        else f"latency_vs_depth_median_{suffix}"
    )
    _save_chart(fig, name)
    return name


def _plot_vs_depth_max(
    depth_data: Dict[int, List[Optional[Dict[str, float]]]],
    fit: bool = False,
) -> Optional[str]:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    has_data = False

    for n, stats in depth_data.items():
        xs, ys = [], []
        for d, s in enumerate(stats):
            if s is not None:
                xs.append(d)
                ys.append(s["max"])
        if not xs:
            continue
        has_data = True
        color = _depth_color(n)
        marker = _depth_marker(n)

        ax.plot(
            xs,
            ys,
            label=_depth_label(n),
            color=color,
            marker=marker,
            markersize=4,
            linestyle="none",
        )
        if fit:
            _add_linear_fit(ax, xs, ys, color)

    if not has_data:
        plt.close(fig)
        return None

    if not depth_data:
        plt.close(fig)
        return None
    max_depth = max(_depth_count_for_n(n) for n in depth_data)
    if max_depth > 0:
        ax.set_xticks(range(max_depth))

    _apply_common_style(
        ax,
        xlabel="Error boundary depth (D)",
        ylabel="Latency (ms)",
        title="E-stop latency vs error-boundary depth — Max",
    )
    name = "latency_vs_depth_max_fit" if fit else "latency_vs_depth_max"
    _save_chart(fig, name)
    return name


# ---------------------------------------------------------------------------
# Percentile chart configs
# ---------------------------------------------------------------------------
PERCENTILE_CONFIGS = [
    ("p5", "p95", "P5", "P95", "p5_95"),
    ("p1", "p99", "P1", "P99", "p1_99"),
    ("p0_1", "p99_9", "P0.1", "P99.9", "p01_999"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    generated: List[str] = []
    skipped: List[str] = []

    def _track(name: Optional[str], desc: str) -> None:
        if name:
            generated.append(name)
        else:
            skipped.append(desc)

    # --- Load data ---
    print("Loading latency-vs-N data...")
    vs_n_data = load_vs_n_data()
    total_vs_n = sum(
        1 for stats_list in vs_n_data.values() for s in stats_list if s is not None
    )
    print(f"  Loaded {total_vs_n} datasets across {len(vs_n_data)} series.")

    print("Loading latency-vs-depth data...")
    vs_depth_data = load_vs_depth_data()
    total_depth = sum(
        1
        for depth_stats in vs_depth_data.values()
        for s in depth_stats
        if s is not None
    )
    total_depth_expected = sum(
        _depth_count_for_n(n) for n in ERROR_BOUNDARY_DEPTH_N_VALUES
    )
    print(
        f"  Loaded {total_depth} / {total_depth_expected} depth datasets across configured N values."
    )

    # --- Generate Latency vs N charts ---
    print("\nGenerating latency-vs-N charts...")

    # Mean + stddev
    _track(_plot_vs_n_mean(vs_n_data, fit=False), "latency_vs_n_mean")
    _track(_plot_vs_n_mean(vs_n_data, fit=True), "latency_vs_n_mean_fit")
    _track(
        _plot_vs_n_mean(vs_n_data, fit=False, show_stddev=False),
        "latency_vs_n_mean_nostd",
    )
    _track(
        _plot_vs_n_mean(vs_n_data, fit=True, show_stddev=False),
        "latency_vs_n_mean_nostd_fit",
    )

    # Median + percentile variants
    for plo_key, phi_key, plo_label, phi_label, suffix in PERCENTILE_CONFIGS:
        _track(
            _plot_vs_n_median(
                vs_n_data, plo_key, phi_key, plo_label, phi_label, suffix, fit=False
            ),
            f"latency_vs_n_median_{suffix}",
        )
        _track(
            _plot_vs_n_median(
                vs_n_data, plo_key, phi_key, plo_label, phi_label, suffix, fit=True
            ),
            f"latency_vs_n_median_{suffix}_fit",
        )

    # Max
    _track(_plot_vs_n_max(vs_n_data, fit=False), "latency_vs_n_max")
    _track(_plot_vs_n_max(vs_n_data, fit=True), "latency_vs_n_max_fit")

    # --- Generate Latency vs Depth charts ---
    print("\nGenerating latency-vs-depth charts...")

    # Mean + stddev
    _track(_plot_vs_depth_mean(vs_depth_data, fit=False), "latency_vs_depth_mean")
    _track(_plot_vs_depth_mean(vs_depth_data, fit=True), "latency_vs_depth_mean_fit")
    _track(
        _plot_vs_depth_mean(vs_depth_data, fit=False, show_stddev=False),
        "latency_vs_depth_mean_nostd",
    )
    _track(
        _plot_vs_depth_mean(vs_depth_data, fit=True, show_stddev=False),
        "latency_vs_depth_mean_nostd_fit",
    )

    # Median + percentile variants
    for plo_key, phi_key, plo_label, phi_label, suffix in PERCENTILE_CONFIGS:
        _track(
            _plot_vs_depth_median(
                vs_depth_data, plo_key, phi_key, plo_label, phi_label, suffix, fit=False
            ),
            f"latency_vs_depth_median_{suffix}",
        )
        _track(
            _plot_vs_depth_median(
                vs_depth_data, plo_key, phi_key, plo_label, phi_label, suffix, fit=True
            ),
            f"latency_vs_depth_median_{suffix}_fit",
        )

    # Max
    _track(_plot_vs_depth_max(vs_depth_data, fit=False), "latency_vs_depth_max")
    _track(_plot_vs_depth_max(vs_depth_data, fit=True), "latency_vs_depth_max_fit")

    # --- Outlier summary ---
    print(f"\n{'=' * 80}")
    print(f"Outlier summary (threshold > {OUTLIER_THRESHOLD_MS:.0f} ms)")
    print(f"{'=' * 80}")
    print(f"  {'dataset':45s}  {'outliers':>8s}  {'analysed':>8s}  {'total':>8s}")
    print(f"  {'-' * 45}  {'-' * 8}  {'-' * 8}  {'-' * 8}")

    grand_analysed = 0
    grand_total_events = 0
    grand_outliers = 0

    for label, stats_list in vs_n_data.items():
        for i, s in enumerate(stats_list):
            if s is not None:
                n = N_VALUES[i]
                cnt = int(s["count"])
                total_ev = int(s["total_events"])
                out = int(s["outlier_count"])
                grand_analysed += cnt
                grand_total_events += total_ev
                grand_outliers += out
                tmpl = [t for l, t, _, _ in SERIES_VS_N if l == label][0]
                dirname = tmpl.format(n=n)
                print(f"  {dirname:45s}  {out:>8d}  {cnt:>8d}  {total_ev:>8d}")

    for n, stats_list in vs_depth_data.items():
        for d, s in enumerate(stats_list):
            if s is not None:
                dirname = f"campaign-hertz-eb-deep-n{n}-d{d}"
                cnt = int(s["count"])
                total_ev = int(s["total_events"])
                out = int(s["outlier_count"])
                grand_analysed += cnt
                grand_total_events += total_ev
                grand_outliers += out
                print(f"  {dirname:45s}  {out:>8d}  {cnt:>8d}  {total_ev:>8d}")

    print(f"  {'-' * 45}  {'-' * 8}  {'-' * 8}  {'-' * 8}")
    print(
        f"  {'TOTAL':45s}  {grand_outliers:>8d}  {grand_analysed:>8d}  {grand_total_events:>8d}"
    )
    print(f"{'=' * 80}")

    # --- Chart summary ---
    print(
        f"\nGenerated {len(generated)} charts ({len(generated) * len(FORMATS)} files)"
    )
    if skipped:
        print(f"Skipped {len(skipped)} charts (no data): {', '.join(skipped)}")
    print(f"Output directory: {CHARTS_DIR}")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
