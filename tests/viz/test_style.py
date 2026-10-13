"""Tests for visualization style module.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from traffic_lab.viz.style import apply_style, get_arm_color, get_arm_label, plot_ci_band


def test_style_application() -> None:
    """Test that apply_style modifies matplotlib rcParams."""
    apply_style()
    assert plt.rcParams["figure.dpi"] == 300
    assert plt.rcParams["axes.grid"] is True


def test_arm_colors_and_labels() -> None:
    """Test helper functions for arm colors and labels."""
    assert get_arm_color("webster") == "#1f77b4"
    assert get_arm_color("actuated") == "#ff7f0e"
    assert get_arm_color("unknown_arm") == "#333333"

    assert get_arm_label("webster") == "Webster Fixed-Time"
    assert get_arm_label("max_pressure") == "Max-Pressure"
    assert get_arm_label("custom_arm") == "custom_arm"


def test_plot_ci_band() -> None:
    """Test plot_ci_band creates a Polygon in the axes."""
    fig, ax = plt.subplots()
    plot_ci_band(ax, [1, 2, 3], [0, 1, 2], [2, 3, 4], color="#1f77b4")
    assert len(ax.collections) == 1
    plt.close(fig)
