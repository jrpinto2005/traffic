"""Handing ground truth to something that wants a belief is a type error (T1.9 A5).

The second of the three layers of `06_ARCHITECTURE.md` SS4.3: `mypy --strict`,
under which `TrueState` is not an `EstimatedState` and cannot be passed as one.
The import test is the layer that catches things; this one makes the mistake
fail to type-check even where the import is allowed, such as in a sensor.

The check is a real mypy run (`mypy.api.run`) on short probe modules written to a
temporary directory, with the project's own configuration -- not a claim made
once by hand. Each negative probe is paired with a corrected twin that must pass,
so a failure cannot be mypy tripping over the probe itself.
"""

from __future__ import annotations

from pathlib import Path

from mypy import api

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

_HEADER = """
from traffic_lab.domain.observation import EstimatedState, Observation
from traffic_lab.domain.state import SignalState, TrueState
from traffic_lab.estimation import Estimator, IdentityEstimator


def decide(estimate: EstimatedState) -> int:
    return len(estimate.lanes)
"""


def _mypy(tmp_path: Path, body: str) -> tuple[int, str]:
    """Type-check `_HEADER` + `body` under the project's strict configuration.

    Returns mypy's exit status and its stdout. A private cache keeps the run from
    touching the project's own `.mypy_cache`.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(_HEADER + body)
    stdout, _stderr, status = api.run(
        [
            "--config-file",
            str(PYPROJECT),
            "--cache-dir",
            str(tmp_path / "mypy_cache"),
            str(probe),
        ]
    )
    return status, stdout


def test_passing_true_state_where_an_estimate_is_expected_is_an_arg_type_error(
    tmp_path: Path,
) -> None:
    status, out = _mypy(
        tmp_path,
        """
def leak(truth: TrueState) -> int:
    return decide(truth)
""",
    )
    assert status == 1, out
    assert "[arg-type]" in out, out
    assert 'incompatible type "TrueState"; expected "EstimatedState"' in out, out
    assert "Found 1 error" in out, f"the probe should fail for this reason alone: {out}"


def test_the_same_module_passing_an_estimate_type_checks(tmp_path: Path) -> None:
    status, out = _mypy(
        tmp_path,
        """
def honest(estimate: EstimatedState) -> int:
    return decide(estimate)
""",
    )
    assert status == 0, out


def test_an_estimator_typed_against_true_state_does_not_satisfy_the_protocol(
    tmp_path: Path,
) -> None:
    # The `Estimator` seam takes an `Observation`. An estimator whose `update`
    # was written against `TrueState` is not one, so it cannot be plugged in.
    status, out = _mypy(
        tmp_path,
        """
class PeeksAtTruth:
    def update(
        self, obs: TrueState, signals: tuple[SignalState, ...], now_s: float
    ) -> EstimatedState:
        raise NotImplementedError


estimator: Estimator = PeeksAtTruth()
""",
    )
    assert status == 1, out
    assert "[assignment]" in out, out
    assert "PeeksAtTruth" in out and "Estimator" in out, out
    assert "Found 1 error" in out, f"the probe should fail for this reason alone: {out}"


def test_the_estimator_that_satisfies_the_protocol_type_checks(tmp_path: Path) -> None:
    status, out = _mypy(
        tmp_path,
        """
class SeesObservations:
    def update(
        self, obs: Observation, signals: tuple[SignalState, ...], now_s: float
    ) -> EstimatedState:
        raise NotImplementedError


estimator: Estimator = SeesObservations()
identity: Estimator = IdentityEstimator()
""",
    )
    assert status == 0, out
