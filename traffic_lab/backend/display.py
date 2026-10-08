"""From what the constraint layer says the signal must show to SUMO's state string.

The outbound half of D-034; `projection.py` decodes the inbound half. This
package is the only one that knows SUMO's state characters.
"""

from __future__ import annotations

from traffic_lab.domain.network import IntersectionId, Network, PhaseId, green_link_indices
from traffic_lab.domain.state import SignalStage

#: SUMO's state characters, as emitted here. `'g'` (permissive green) is never
#: emitted at M1: no scenario declares a permitted pair (D-023, point 4).
_GREEN, _YELLOW, _RED = "G", "y", "r"


def display_state(
    network: Network, intersection: IntersectionId, stage: SignalStage, phase: PhaseId | None
) -> str:
    """GREEN: 'G' on `phase`'s green links. YELLOW: 'y' on `phase`'s (the phase being left).
    ALL_RED: `phase` is None, all 'r'. Every other link 'r'.

    Indexed by `SignalizedIntersection.controlled_connections`, which is SUMO's
    link order; green links come from `green_link_indices()`, the same table the
    decode reads. No link stays green across a transition (T1.14, Non-goal 2):
    a yellow marks yellow exactly the links green in the phase being left.
    """
    size = _display_size(network, intersection)
    if stage is SignalStage.ALL_RED:
        if phase is not None:
            raise ValueError(f"ALL_RED shows no phase, got phase {int(phase)}")
        return _RED * size
    if phase is None:
        raise ValueError(f"{stage.name} needs a phase: the one green, or the one being left")
    char = _GREEN if stage is SignalStage.GREEN else _YELLOW
    links = green_link_indices(network, intersection, phase)
    return "".join(char if link in links else _RED for link in range(size))


def _display_size(network: Network, intersection: IntersectionId) -> int:
    for candidate in network.signalized_intersections:
        if candidate.id == intersection:
            return len(candidate.controlled_connections)
    raise KeyError(f"network has no signalized intersection {int(intersection)}")
