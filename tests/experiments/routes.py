"""Route files the runner tests need beyond the shared fixture. Test support only.

Demand generation is T1.5's; these exist to provoke one SUMO behaviour each.
"""

from __future__ import annotations

from pathlib import Path

from tests.generated_scenario import Built

#: Departure times of `out_of_order_routes`, in file order. The second precedes
#: the first, which SUMO 1.27.1 answers by dropping it with a warning.
OUT_OF_ORDER_DEPARTS_S = (20, 10, 30)


def out_of_order_routes(built: Built, path: Path) -> Path:
    """Three vehicles on one movement, the second departing before the first."""
    movement = built.movements[0]
    edges = f"{built.ids.edges[movement.from_edge]} {built.ids.edges[movement.to_edge]}"
    lines = ["<routes>", f'    <route id="r" edges="{edges}"/>']
    lines += [
        f'    <vehicle id="v{k}" route="r" depart="{depart}"/>'
        for k, depart in enumerate(OUT_OF_ORDER_DEPARTS_S)
    ]
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")
    return path
