"""`movements_of()`: the Movement view computed from lane connections (D-011).

D-011 requires `Movement` to be derived, never stored. These tests exercise
the computation directly rather than asserting on a pre-built `Movement`
instance, since there is no other producer of one.
"""

from __future__ import annotations

from tests.domain.factories import (
    C_E_TO_W,
    C_N_TO_S,
    C_S_TO_N,
    C_W_TO_E,
    E_E_IN,
    E_N_IN,
    E_S_IN,
    E_W_IN,
    J0,
    build_valid_network,
)
from traffic_lab.domain.network import MovementId, TurnDirection, movements_of


def test_movements_of_groups_by_approach_edge_and_turn() -> None:
    network = build_valid_network()
    movements = movements_of(network, J0)
    assert len(movements) == 4
    by_from_edge = {m.from_edge: m for m in movements}
    assert set(by_from_edge) == {E_N_IN, E_S_IN, E_E_IN, E_W_IN}
    for movement in movements:
        assert movement.turn is TurnDirection.THROUGH
        assert movement.junction == J0
        assert movement.signal_group is None  # a pure topology view; D-011


def test_movements_of_assigns_each_connection_to_exactly_one_movement() -> None:
    network = build_valid_network()
    movements = movements_of(network, J0)
    all_connections = [c for m in movements for c in m.connections]
    assert sorted(all_connections) == sorted([C_S_TO_N, C_N_TO_S, C_E_TO_W, C_W_TO_E])
    assert len(all_connections) == len(set(all_connections))  # no connection in two movements


def test_movements_of_respects_start_id_offset() -> None:
    network = build_valid_network()
    offset_movements = movements_of(network, J0, start_id=MovementId(100))
    ids = sorted(int(m.id) for m in offset_movements)
    assert ids == [100, 101, 102, 103]


def test_movements_of_is_not_stored_anywhere_on_junction_or_network() -> None:
    # D-011: Movement is a view, not a field. Assert the negative directly so a
    # future change that adds a `movements` field to Junction/Network is caught.
    from traffic_lab.domain.network import Junction, Network

    assert "movements" not in Junction.__dataclass_fields__
    assert "movements" not in Network.__dataclass_fields__
