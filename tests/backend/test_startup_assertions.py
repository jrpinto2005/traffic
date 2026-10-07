"""Every startup assertion of `06_ARCHITECTURE.md` SS5.4 fails loudly.

"These are hard failures at startup. A run that violates them produces no
results rather than wrong ones." Each assertion therefore gets a test that it
*fires*, not merely that it exists -- an assertion nobody has ever seen fail is
indistinguishable from one that cannot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.backend.conftest import make_config
from traffic_lab.backend import (
    SNAPSHOT_SIDECAR_SUFFIX,
    BackendStartupError,
    SnapshotMismatchError,
    SumoBackend,
)


def test_teleporting_enabled_by_magnitude_is_refused() -> None:
    """D-008 assertion 1, in the form the prior art actually gets wrong.

    PyTSC sets `time_to_teleport: 10000`, which disables teleporting only until
    an episode outlasts it (`08_AGENT_HANDOFF_PROTOCOL.md` SS7: "a validity
    setting disabled by magnitude rather than by flag"). A large value must be
    rejected exactly as firmly as a small one.
    """
    for value in (10000.0, 300.0, 0.0):
        with pytest.raises(BackendStartupError, match=r"must be exactly -1\.0"):
            SumoBackend().start(
                Path("unused.net.xml"),
                Path("unused.rou.xml"),
                make_config(time_to_teleport_s=value),
            )


def test_step_length_that_does_not_divide_the_decision_interval_is_refused() -> None:
    """D-020: Δt must be an integer multiple of the SUMO step length."""
    with pytest.raises(BackendStartupError, match="does not divide"):
        SumoBackend().start(
            Path("unused.net.xml"),
            Path("unused.rou.xml"),
            make_config(step_length_s=0.4, decision_interval_s=5.0),
        )


def test_step_length_that_does_divide_is_accepted(
    reference_net: Path, reference_routes: Path
) -> None:
    """The counterpart, so the assertion above is not merely rejecting everything.

    0.5 s divides 5 s exactly; 0.4 s does not. Both are floats, so the check has
    to tolerate representation error without tolerating a real mismatch.
    """
    backend = SumoBackend()
    backend.start(
        reference_net,
        reference_routes,
        make_config(step_length_s=0.5, decision_interval_s=5.0),
    )
    backend.close()


def test_snapshot_from_a_different_network_is_refused(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """D-032: "loading a snapshot against a different network is a hard error"."""
    snapshot = tmp_path / "state.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        for _ in range(20):
            backend.step()
            backend.project()
        backend.save_state(snapshot)

        sidecar = snapshot.with_name(snapshot.name + SNAPSHOT_SIDECAR_SUFFIX)
        payload = json.loads(sidecar.read_text())
        payload["network_sha256"] = "0" * 64
        sidecar.write_text(json.dumps(payload))

        with pytest.raises(SnapshotMismatchError, match="was produced on network sha256"):
            backend.load_state(snapshot)
    finally:
        backend.close()


def test_snapshot_from_a_different_sumo_version_is_refused(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """D-032's caveat: "SUMO state files are sensitive to the SUMO version"."""
    snapshot = tmp_path / "state.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        for _ in range(20):
            backend.step()
            backend.project()
        backend.save_state(snapshot)

        sidecar = snapshot.with_name(snapshot.name + SNAPSHOT_SIDECAR_SUFFIX)
        payload = json.loads(sidecar.read_text())
        payload["sumo_version"] = "SUMO 0.0.0"
        sidecar.write_text(json.dumps(payload))

        with pytest.raises(SnapshotMismatchError, match=r"was produced by SUMO 0\.0\.0"):
            backend.load_state(snapshot)
    finally:
        backend.close()


def test_snapshot_without_a_sidecar_is_refused(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """A bare SUMO state file carries neither guard, so it cannot be trusted.

    Loading it anyway would be the undefined behaviour D-032 exists to
    prevent -- the guards would simply not run.
    """
    snapshot = tmp_path / "state.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        for _ in range(20):
            backend.step()
            backend.project()
        backend.save_state(snapshot)
        snapshot.with_name(snapshot.name + SNAPSHOT_SIDECAR_SUFFIX).unlink()

        with pytest.raises(SnapshotMismatchError, match=r"has no \S+ sidecar"):
            backend.load_state(snapshot)
    finally:
        backend.close()


def test_the_seed_reaches_the_simulator(reference_net: Path, reference_routes: Path) -> None:
    """The prior-art defect this project refuses to repeat.

    PyTSC's `seed` never reaches SUMO; it seeds only Python's `random`. "A
    parameter that appears to be set and is not is worse than one that is
    absent." `start()` therefore reads the value back out of the running
    simulator, and here we confirm the readback is a real one by checking that
    two different seeds are both observed.
    """
    for seed in (7, 12345):
        backend = SumoBackend()
        backend.start(reference_net, reference_routes, make_config(seed=seed))
        try:
            assert backend._require_started().option("seed") == str(seed)
        finally:
            backend.close()


def test_a_settings_mismatch_reported_by_sumo_is_refused(
    reference_net: Path, reference_routes: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The readback assertion fires when the simulator disagrees.

    Simulated by making SUMO report a different seed than the one requested,
    which is precisely the situation the assertion exists to catch and which no
    honest configuration can produce.
    """
    from traffic_lab.backend import transport as transport_module

    monkeypatch.setattr(transport_module._SumoTransport, "option", lambda self, name: "999")
    with pytest.raises(BackendStartupError, match="did not reach the simulator"):
        SumoBackend().start(reference_net, reference_routes, make_config())


def test_using_the_backend_before_starting_it_is_refused() -> None:
    backend = SumoBackend()
    with pytest.raises(BackendStartupError, match="has not been started"):
        backend.step()
    with pytest.raises(BackendStartupError, match="has not been started"):
        backend.project()
    with pytest.raises(BackendStartupError, match="has not been started"):
        _ = backend.index
    # `close()` before `start()` is a no-op, not an error: teardown must be safe
    # to call from a `finally` that a failed `start()` never got past.
    backend.close()


def test_the_config_itself_rejects_missing_required_fields() -> None:
    """`decision_interval_s` and `gridlock_steps` are required, not defaulted.

    Both decide whether a run is valid, and `08_AGENT_HANDOFF_PROTOCOL.md` SS2.2
    is explicit that a Builder never decides "a default parameter that affects
    results". Requiring them pushes the choice up to the config file, where the
    manifest records it.
    """
    from traffic_lab.backend import BackendConfig

    with pytest.raises(ValidationError):
        BackendConfig(seed=1)  # type: ignore[call-arg]
