"""D-008's gridlock N, derived from signal timing (register v1.12, set by the owner).

`N = ceil(1.5 * sum over phases of (max_green_s + yellow_s + all_red_s) / step)`,
the maximum over signalized intersections: half as long again as the longest
cycle the constraint layer can run. A vehicle alone at a red waits less than one
such cycle, so it must never be flagged -- which a hand-picked N could do.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl
import pytest

from tests.backend.conftest import Scenario
from tests.experiments.controllers import CycleFrom, hold_first
from tests.experiments.support import make_spec
from tests.generated_scenario import TIMING
from traffic_lab.domain.network import IntersectionId, Network, SignalTiming, TurnDirection
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import (
    MANIFEST_FILE,
    RESULT_FILE,
    TRIPINFO_FILE,
    derive_gridlock_steps,
    run_many,
)


def _with_timing(network: Network, timing: SignalTiming) -> Network:
    (intersection,) = network.signalized_intersections
    return dataclasses.replace(
        network, signalized_intersections=(dataclasses.replace(intersection, timing=timing),)
    )


def test_the_formula_on_the_shared_fixture(scenario: Scenario) -> None:
    """Four phases of 60 s max green, 3 s yellow and 2 s all-red: a 260 s longest
    cycle, so N is 390 s of steps."""
    assert SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0) == TIMING
    assert len(scenario.built.intersection.phases) == 4
    assert derive_gridlock_steps(scenario.network, 1.0) == 390
    assert derive_gridlock_steps(scenario.network, 0.5) == 780
    assert derive_gridlock_steps(scenario.network, 0.1) == 3900  # not 3901: 390/0.1 rounding
    # A ceiling, not a rounding: 1.5 x 4 x 65.5 = 393 s over 2 s steps is 196.5.
    longer = _with_timing(scenario.network, dataclasses.replace(TIMING, max_green_s=60.5))
    assert derive_gridlock_steps(longer, 2.0) == 197


def test_the_largest_intersection_sets_n(scenario: Scenario) -> None:
    (intersection,) = scenario.network.signalized_intersections
    slower = dataclasses.replace(
        intersection,
        id=IntersectionId(1),
        timing=dataclasses.replace(TIMING, max_green_s=90.0),
    )
    network = dataclasses.replace(scenario.network, signalized_intersections=(intersection, slower))
    assert derive_gridlock_steps(network, 1.0) == 570  # 1.5 x 4 x (90 + 3 + 2)


def test_a_timing_without_max_green_is_refused(scenario: Scenario, tmp_path: Path) -> None:
    unbounded = _with_timing(scenario.network, dataclasses.replace(TIMING, max_green_s=0.0))
    spec = make_spec(scenario, tmp_path, hold_first)
    with pytest.raises(ValueError, match="max_green_s"):
        dataclasses.replace(spec, network=unbounded)


#: Every phase held to its max green: the constraint layer's override cycles them.
HOLD_EVERY_PHASE = functools.partial(CycleFrom, start_s=1e9)


def test_a_long_red_wait_alone_at_low_demand_is_not_gridlock(
    scenario: Scenario, tmp_path: Path
) -> None:
    """One vehicle reaches its stop line just as its phase goes red and waits
    there, alone and motionless, for nearly a whole longest cycle -- every step
    of it a step on which no vehicle moves. It is a signal doing its job."""
    built = scenario.built
    timing = built.spec.timing
    period_s = timing.max_green_s + timing.yellow_s + timing.all_red_s  # 65 s per phase
    # The third phase serves approach 1's through movement; held to max green, it
    # is green on [130, 190) s and next on [390, 450) s.
    phase = built.intersection.phases[2]
    served = {
        movement
        for group in built.intersection.signal_groups
        if group.id in phase.green_groups
        for movement in group.movements
    }
    movement = next(
        m for m in built.movements if m.id in served and m.turn is TurnDirection.THROUGH
    )
    red_from_s = 2 * period_s + timing.max_green_s  # 190 s: its yellow begins
    travel_s = built.spec.approach_length_m / built.spec.speed_limit_mps
    depart_s = round(red_from_s - travel_s + 2.0)  # at the line in its yellow
    edges = f"{built.ids.edges[movement.from_edge]} {built.ids.edges[movement.to_edge]}"
    routes = tmp_path / "alone.rou.xml"
    routes.write_text(
        f'<routes>\n    <route id="r" edges="{edges}"/>\n'
        f'    <vehicle id="alone" route="r" depart="{depart_s}" departSpeed="max"/>\n'
        "</routes>\n"
    )
    config = RunConfig(
        name="alone", master_seed=1, warmup_s=60.0, measurement_s=300.0, cooldown_s=180.0
    )
    spec = make_spec(scenario, tmp_path / "run", HOLD_EVERY_PHASE, routes=routes, config=config)
    run_many([spec], tmp_path / "experiment", jobs=1)

    (trip,) = ET.parse(spec.output_dir / TRIPINFO_FILE).getroot().iter("tripinfo")
    waited_s = float(trip.attrib["waitingTime"])
    assert trip.attrib["waitingCount"] == "1"  # one unbroken halt (192 s on SUMO 1.27.1)
    assert 150.0 < waited_s < spec.gridlock_steps  # long, and alone: the whole network still
    assert float(trip.attrib["arrival"]) > 4 * period_s + 2 * period_s  # it went on its next green

    row = pl.read_parquet(spec.output_dir / RESULT_FILE).row(0, named=True)
    assert row["gridlock_detected"] is False
    assert row["valid"] is True
    manifest = json.loads((spec.output_dir / MANIFEST_FILE).read_text())
    assert manifest["config"]["gridlock_steps"] == 390
    assert manifest["validity"]["gridlock_detected"] is False
