"""2D Replay Renderer Engine and Research Overlays (D-009, D-030, M2).

Decoupled replay visualization: renders simulation runs entirely from
trace files without SUMO installed or running. Produces visual frames
with research overlays (queues, active signal heads, velocity telemetry,
and live HUD metrics) and exports animated recordings (GIF/video).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

from traffic_lab.viz.trace import StepFrame, TraceReader


@dataclass(frozen=True, slots=True)
class RenderConfig:
    """Configuration for 2D replay rendering."""

    width_px: int = 800
    height_px: int = 800
    dpi: int = 100
    show_queues: bool = True
    show_signals: bool = True
    show_metrics: bool = True
    show_vehicle_ids: bool = False
    background_color: str = "#18181c"
    road_color: str = "#2c2c34"
    lane_divider_color: str = "#606070"
    hud_bg_color: str = "#22222a"


class ReplayRenderer:
    """Standalone 2D renderer for simulation trace playback."""

    def __init__(self, trace_reader: TraceReader, config: RenderConfig | None = None) -> None:
        self.trace_reader = trace_reader
        self.config = config or RenderConfig()
        self.header = trace_reader.header
        self._setup_bounds()

    def _setup_bounds(self) -> None:
        """Calculate spatial bounding box from static network geometry."""
        junctions = self.header.geometry.get("junctions", [])
        if junctions:
            xs = [j["x"] for j in junctions]
            ys = [j["y"] for j in junctions]
            center_x = sum(xs) / len(xs)
            center_y = sum(ys) / len(ys)
        else:
            center_x, center_y = 0.0, 0.0

        # Default viewing radius around intersection center
        self.radius_m = 120.0
        self.xlim = (center_x - self.radius_m, center_x + self.radius_m)
        self.ylim = (center_y - self.radius_m, center_y + self.radius_m)
        self.center_xy = (center_x, center_y)

    def render_frame(self, frame: StepFrame) -> Image.Image:
        """Render a single StepFrame to a PIL Image."""
        cfg = self.config
        figsize = (cfg.width_px / cfg.dpi, cfg.height_px / cfg.dpi)
        fig, ax = plt.subplots(figsize=figsize, dpi=cfg.dpi)
        fig.patch.set_facecolor(cfg.background_color)
        ax.set_facecolor(cfg.background_color)

        self._draw_roads(ax)
        if cfg.show_signals:
            self._draw_signals(ax, frame)
        if cfg.show_queues:
            self._draw_queues(ax, frame)
        self._draw_vehicles(ax, frame)
        if cfg.show_metrics:
            self._draw_hud(ax, frame)

        ax.set_xlim(self.xlim)
        ax.set_ylim(self.ylim)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        canvas = cast(FigureCanvasAgg, fig.canvas)
        canvas.draw()  # type: ignore[no-untyped-call]
        rgba_buffer = canvas.buffer_rgba()  # type: ignore[no-untyped-call]
        img = Image.frombuffer(
            "RGBA", (cfg.width_px, cfg.height_px), rgba_buffer, "raw", "RGBA", 0, 1
        )
        plt.close(fig)
        return img.convert("RGB")

    def _draw_roads(self, ax: Axes) -> None:
        """Draw static road network arms and intersection box."""
        cx, cy = self.center_xy
        cfg = self.config
        road_half_width = 7.0  # 2 lanes per approach approx 7 m

        # Center junction
        junction_box = patches.Rectangle(
            (cx - road_half_width, cy - road_half_width),
            road_half_width * 2,
            road_half_width * 2,
            facecolor=cfg.road_color,
            edgecolor="none",
            zorder=1,
        )
        ax.add_patch(junction_box)

        # North & South arms
        ns_arm = patches.Rectangle(
            (cx - road_half_width, cy - self.radius_m),
            road_half_width * 2,
            self.radius_m * 2,
            facecolor=cfg.road_color,
            edgecolor="none",
            zorder=1,
        )
        ax.add_patch(ns_arm)

        # East & West arms
        ew_arm = patches.Rectangle(
            (cx - self.radius_m, cy - road_half_width),
            self.radius_m * 2,
            road_half_width * 2,
            facecolor=cfg.road_color,
            edgecolor="none",
            zorder=1,
        )
        ax.add_patch(ew_arm)

        # Center dashed dividers
        ax.plot(
            [cx, cx],
            [cy - self.radius_m, cy - road_half_width],
            color=cfg.lane_divider_color,
            linestyle="--",
            linewidth=1.5,
            zorder=2,
        )
        ax.plot(
            [cx, cx],
            [cy + road_half_width, cy + self.radius_m],
            color=cfg.lane_divider_color,
            linestyle="--",
            linewidth=1.5,
            zorder=2,
        )
        ax.plot(
            [cx - self.radius_m, cx - road_half_width],
            [cy, cy],
            color=cfg.lane_divider_color,
            linestyle="--",
            linewidth=1.5,
            zorder=2,
        )
        ax.plot(
            [cx + road_half_width, cx + self.radius_m],
            [cy, cy],
            color=cfg.lane_divider_color,
            linestyle="--",
            linewidth=1.5,
            zorder=2,
        )

    def _draw_signals(self, ax: Axes, frame: StepFrame) -> None:
        """Draw active signal heads for each approach."""
        cx, cy = self.center_xy
        offset = 9.0  # stop line distance from center
        signals = frame.signals

        active_phase = 0
        in_transition = False
        if signals:
            active_phase = signals[0].get("active_phase", 0)
            in_transition = signals[0].get("in_transition", False)

        # In 4-phase program: Phase 0/1 are East-West, Phase 2/3 are North-South
        ew_color = (
            "#2ecc71"
            if active_phase in (0, 1) and not in_transition
            else ("#f39c12" if in_transition and active_phase in (0, 1) else "#e74c3c")
        )
        ns_color = (
            "#2ecc71"
            if active_phase in (2, 3) and not in_transition
            else ("#f39c12" if in_transition and active_phase in (2, 3) else "#e74c3c")
        )

        # West approach stop-line head
        ax.plot(
            cx - offset,
            cy - 3.5,
            marker="o",
            markersize=9,
            color=ew_color,
            markeredgecolor="#ffffff",
            markeredgewidth=1.2,
            zorder=6,
        )
        # East approach stop-line head
        ax.plot(
            cx + offset,
            cy + 3.5,
            marker="o",
            markersize=9,
            color=ew_color,
            markeredgecolor="#ffffff",
            markeredgewidth=1.2,
            zorder=6,
        )
        # South approach stop-line head
        ax.plot(
            cx + 3.5,
            cy - offset,
            marker="o",
            markersize=9,
            color=ns_color,
            markeredgecolor="#ffffff",
            markeredgewidth=1.2,
            zorder=6,
        )
        # North approach stop-line head
        ax.plot(
            cx - 3.5,
            cy + offset,
            marker="o",
            markersize=9,
            color=ns_color,
            markeredgecolor="#ffffff",
            markeredgewidth=1.2,
            zorder=6,
        )

    def _draw_queues(self, ax: Axes, frame: StepFrame) -> None:
        """Draw queue accumulation indicators."""
        queues = frame.queues
        total_queued = sum(q.get("queue_count", 0) for q in queues.values())
        if total_queued > 0:
            cx, cy = self.center_xy
            # Draw subtle pulsing circle around center when queues persist
            radius = min(15.0 + total_queued * 2.0, self.radius_m * 0.8)
            q_patch = patches.Circle(
                (cx, cy),
                radius,
                facecolor="none",
                edgecolor="#e74c3c",
                linestyle=":",
                linewidth=1.2,
                alpha=0.6,
                zorder=3,
            )
            ax.add_patch(q_patch)

    def _draw_vehicles(self, ax: Axes, frame: StepFrame) -> None:
        """Draw vehicles as speed-colored markers."""
        cfg = self.config
        for v in frame.vehicles:
            vx, vy = v["x"], v["y"]
            speed = v.get("speed_mps", 0.0)
            is_halting = v.get("is_halting", False)

            # Color by velocity
            if is_halting or speed < 0.1:
                color = "#e74c3c"  # Red halting
            elif speed < 5.0:
                color = "#f39c12"  # Orange slowing
            else:
                color = "#00d2d3"  # Cyan cruising

            ax.plot(
                vx,
                vy,
                marker="s",
                markersize=5.5,
                color=color,
                markeredgecolor="#1e272e",
                markeredgewidth=0.8,
                zorder=5,
            )

            if cfg.show_vehicle_ids:
                ax.text(vx + 1.5, vy + 1.5, str(v["id"]), color="#ffffff", fontsize=6, zorder=7)

    def _draw_hud(self, ax: Axes, frame: StepFrame) -> None:
        """Draw real-time research metrics telemetry HUD."""
        cx, cy = self.center_xy
        metrics = frame.metrics
        signals = frame.signals
        phase_str = f"Phase {signals[0].get('active_phase', '-')}" if signals else "Phase -"
        if signals and signals[0].get("in_transition", False):
            phase_str += " (TRANSITION)"

        in_net = metrics.get("still_in_network", 0)
        arrived = metrics.get("arrived_at_sink", 0)
        hud_lines = [
            f"SIM TIME: {frame.time_s:5.1f}s | STEP {frame.step:04d}",
            f"SIGNAL  : {phase_str}",
            f"NETWORK : In-Network {in_net:2d} | Arrived {arrived:2d}",
        ]
        hud_text = "\n".join(hud_lines)

        # Place HUD in top-left corner
        hud_x = cx - self.radius_m + 8.0
        hud_y = cy + self.radius_m - 8.0

        ax.text(
            hud_x,
            hud_y,
            hud_text,
            color="#ecf0f1",
            fontsize=8.5,
            family="monospace",
            verticalalignment="top",
            bbox=dict(
                boxstyle="round,pad=0.5",
                facecolor=self.config.hud_bg_color,
                edgecolor="#404050",
                alpha=0.9,
            ),
            zorder=10,
        )

    def export_gif(
        self,
        out_path: Path,
        start_step: int = 0,
        end_step: int | None = None,
        fps: int = 10,
        step_stride: int = 1,
    ) -> Path:
        """Render all frames and save directly to an animated GIF."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        images: list[Image.Image] = []

        all_frames = self.trace_reader.read_all_frames()
        filtered = [
            f
            for f in all_frames
            if f.step >= start_step and (end_step is None or f.step <= end_step)
        ]
        sampled = filtered[::step_stride]
        if not sampled:
            raise ValueError("No frames found to render in the specified range")

        for frame in sampled:
            img = self.render_frame(frame)
            images.append(img)

        duration_ms = int(1000 / fps)
        images[0].save(
            out_path,
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=0,
            optimize=True,
        )
        return out_path
