"""
AGRA — Chart Renderer (Phase 3)
Renders structured chart JSON as high-DPI PNG images using matplotlib.

Supports:
  - bar_chart:       Vertical bar chart
  - pie_chart:       Pie/donut chart
  - line_chart:      Line chart with markers
  - comparison_bar:  Grouped/stacked bar chart
  - timeline:        Horizontal timeline

Uses matplotlib Agg backend (headless, no display required).
All charts use the ICG color palette and dark slide-matching background.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agra.chart_renderer")

# ICG palette for charts (hex strings for matplotlib)
_ICG_COLORS = [
    "#1E3A8A",  # Dark Blue
    "#D4A537",  # Gold
    "#06B6D4",  # Teal
    "#10B981",  # Green
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
]

_BG_COLOR = "#0B1020"      # Navy (matches slide background)
_TEXT_COLOR = "#E0E0E0"     # Light gray
_GRID_COLOR = "#1E2D4A"    # Subtle grid


def _get_output_dir() -> Path:
    """Get the chart temp output directory."""
    import os
    data_dir = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
    if not data_dir.exists():
        data_dir = Path(__file__).resolve().parent.parent.parent / "agra_data"
    chart_dir = data_dir / "outputs" / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    return chart_dir


def _setup_matplotlib():
    """Configure matplotlib for headless, dark-themed chart generation."""
    import matplotlib
    matplotlib.use("Agg")  # Headless backend
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": _BG_COLOR,
        "axes.facecolor": _BG_COLOR,
        "axes.edgecolor": _TEXT_COLOR,
        "axes.labelcolor": _TEXT_COLOR,
        "text.color": _TEXT_COLOR,
        "xtick.color": _TEXT_COLOR,
        "ytick.color": _TEXT_COLOR,
        "grid.color": _GRID_COLOR,
        "grid.alpha": 0.3,
        "font.family": "sans-serif",
        "font.size": 12,
        "figure.dpi": 300,
    })
    return plt


def render_bar_chart(chart_data: Dict[str, Any]) -> str:
    """Render a vertical bar chart. Returns path to PNG file."""
    plt = _setup_matplotlib()

    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    labels = data.get("labels", [])
    values = data.get("values", [])

    if not labels or not values:
        logger.warning("Bar chart has no data — skipping.")
        return ""

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [_ICG_COLORS[i % len(_ICG_COLORS)] for i in range(len(labels))]
    bars = ax.bar(labels, values, color=colors, edgecolor="none", width=0.6)

    # Value labels on top of bars
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02,
            str(val), ha="center", va="bottom", fontsize=10, color=_TEXT_COLOR,
        )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)

    plt.xticks(rotation=30 if max(len(l) for l in labels) > 8 else 0, ha="right" if max(len(l) for l in labels) > 8 else "center")
    plt.tight_layout()

    path = _get_output_dir() / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(str(path), dpi=300, bbox_inches="tight", facecolor=_BG_COLOR)
    plt.close(fig)
    logger.info("Bar chart saved: %s", path)
    return str(path)


def render_pie_chart(chart_data: Dict[str, Any]) -> str:
    """Render a pie/donut chart. Returns path to PNG file."""
    plt = _setup_matplotlib()

    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    labels = data.get("labels", [])
    values = data.get("values", [])

    if not labels or not values:
        return ""

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = [_ICG_COLORS[i % len(_ICG_COLORS)] for i in range(len(labels))]

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.8,
        wedgeprops={"width": 0.4, "edgecolor": _BG_COLOR, "linewidth": 2},
        textprops={"color": _TEXT_COLOR, "fontsize": 9},
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color(_TEXT_COLOR)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    plt.tight_layout()

    path = _get_output_dir() / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(str(path), dpi=300, bbox_inches="tight", facecolor=_BG_COLOR)
    plt.close(fig)
    logger.info("Pie chart saved: %s", path)
    return str(path)


def render_line_chart(chart_data: Dict[str, Any]) -> str:
    """Render a line chart with markers. Returns path to PNG file."""
    plt = _setup_matplotlib()

    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    labels = data.get("labels", [])

    fig, ax = plt.subplots(figsize=(8, 4.5))

    # Support multiple series
    series_list = data.get("series", [])
    if not series_list and "values" in data:
        series_list = [{"name": "Value", "values": data["values"]}]

    for i, series in enumerate(series_list):
        color = _ICG_COLORS[i % len(_ICG_COLORS)]
        ax.plot(
            labels, series["values"],
            marker="o", color=color, linewidth=2, markersize=6,
            label=series.get("name", f"Series {i+1}"),
        )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="both", alpha=0.2)
    if len(series_list) > 1:
        ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, fontsize=9)

    plt.xticks(rotation=30 if labels and max(len(str(l)) for l in labels) > 8 else 0)
    plt.tight_layout()

    path = _get_output_dir() / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(str(path), dpi=300, bbox_inches="tight", facecolor=_BG_COLOR)
    plt.close(fig)
    logger.info("Line chart saved: %s", path)
    return str(path)


def render_comparison_bar(chart_data: Dict[str, Any]) -> str:
    """Render a grouped bar chart for comparisons. Returns path to PNG file."""
    plt = _setup_matplotlib()
    import numpy as np

    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    labels = data.get("labels", [])
    groups = data.get("groups", [])

    if not labels or not groups:
        return ""

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(labels))
    width = 0.8 / len(groups)

    for i, group in enumerate(groups):
        offset = (i - len(groups) / 2 + 0.5) * width
        color = _ICG_COLORS[i % len(_ICG_COLORS)]
        ax.bar(
            x + offset, group["values"], width,
            label=group.get("name", f"Group {i+1}"),
            color=color, edgecolor="none",
        )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(facecolor=_BG_COLOR, edgecolor=_GRID_COLOR, fontsize=9)
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()

    path = _get_output_dir() / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(str(path), dpi=300, bbox_inches="tight", facecolor=_BG_COLOR)
    plt.close(fig)
    logger.info("Comparison bar chart saved: %s", path)
    return str(path)


def render_timeline(chart_data: Dict[str, Any]) -> str:
    """Render a horizontal timeline."""
    plt = _setup_matplotlib()

    title = chart_data.get("title", "Timeline")
    data = chart_data.get("data", {})
    labels = data.get("labels", [])
    values = data.get("values", [])

    if not labels or not values:
        logger.warning("Timeline has no data — skipping.")
        return ""

    fig, ax = plt.subplots(figsize=(8, 4))
    
    y = np.zeros(len(labels))
    ax.plot(values, y, "-o", color=_ICG_COLORS[0], markerfacecolor=_ICG_COLORS[1], markersize=10, linewidth=2)
    
    for i, (label, val) in enumerate(zip(labels, values)):
        offset = 0.1 if i % 2 == 0 else -0.1
        val_align = "bottom" if i % 2 == 0 else "top"
        ax.text(val, offset, f"{label}\n({val})", ha="center", va=val_align, color=_TEXT_COLOR, fontsize=9)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.tight_layout()

    path = _get_output_dir() / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(str(path), dpi=300, bbox_inches="tight", facecolor=_BG_COLOR)
    plt.close(fig)
    return str(path)


def render_chart(chart_data: Dict[str, Any]) -> str:
    """
    Route to the appropriate chart renderer based on type.

    Args:
        chart_data: Dict with "type" and chart-specific fields.

    Returns:
        Path to the rendered PNG file, or empty string on failure.
    """
    chart_type = chart_data.get("type", "bar_chart")

    try:
        if chart_type == "pie_chart":
            return render_pie_chart(chart_data)
        elif chart_type == "line_chart":
            return render_line_chart(chart_data)
        elif chart_type == "comparison_bar":
            return render_comparison_bar(chart_data)
        elif chart_type == "timeline":
            return render_timeline(chart_data)
        else:  # bar_chart default
            return render_bar_chart(chart_data)
    except Exception as e:
        logger.error("Chart rendering failed (%s): %s", chart_type, e, exc_info=True)
        return ""
