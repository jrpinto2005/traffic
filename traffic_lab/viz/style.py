"""Visualization style module for traffic_lab.

Fixes fonts, colors, figure dimensions, DPI, and the house convention
for rendering uncertainty in plots.
Implements D-004 and T1.12 scope.
"""

from __future__ import annotations

from typing import Any

import matplotlib as mpl
from matplotlib.axes import Axes

#: House color palette for controllers / arms
PALETTE: dict[str, str] = {
    "webster": "#1f77b4",  # Muted Blue
    "actuated": "#ff7f0e",  # Safety Orange
    "sumo_actuated": "#2ca02c",  # Forest Green
    "max_pressure": "#d62728",  # Crimson Red
    "oracle": "#9467bd",  # Purple
    "default": "#333333",  # Dark Charcoal
}

#: Controller display labels
CONTROLLER_LABELS: dict[str, str] = {
    "webster": "Webster Fixed-Time",
    "actuated": "Actuated (ours)",
    "sumo_actuated": "SUMO Gap-Actuated",
    "max_pressure": "Max-Pressure",
    "oracle": "Oracle",
}


def apply_style() -> None:
    """Apply the project style conventions to Matplotlib rcParams."""
    mpl.rcParams.update(
        {
            # Typography
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.titlesize": 12,
            # Layout & Spacing
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "figure.figsize": (6.5, 4.0),  # Standard single-column width in inches
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            # Axes & Grid Styling
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#555555",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": "#e0e0e0",
            "grid.linestyle": "--",
            "grid.linewidth": 0.5,
            "grid.alpha": 0.7,
            # Legend styling
            "legend.frameon": True,
            "legend.framealpha": 0.9,
            "legend.edgecolor": "#d0d0d0",
            # Lines & Markers
            "lines.linewidth": 1.5,
            "lines.markersize": 5,
        }
    )


def get_arm_color(arm_id: str) -> str:
    """Return the assigned house color for a controller arm."""
    key = arm_id.lower().replace("-", "_").replace(" ", "_")
    return PALETTE.get(key, PALETTE["default"])


def get_arm_label(arm_id: str) -> str:
    """Return the clean display label for a controller arm."""
    key = arm_id.lower().replace("-", "_").replace(" ", "_")
    return CONTROLLER_LABELS.get(key, arm_id)


def plot_ci_band(
    ax: Axes,
    x: Any,
    y_lower: Any,
    y_upper: Any,
    color: str,
    alpha: float = 0.2,
    label: str | None = None,
) -> None:
    """Plot a shaded confidence interval band following project conventions."""
    ax.fill_between(x, y_lower, y_upper, color=color, alpha=alpha, label=label, linewidth=0)
