"""SUMO's warnings go to a file, never to the console (T1.11 Amendment A2).

`--no-warnings` alone hid two real defects (T1.8's completion record, finding
3): SUMO drops a route entry that departs before the one above it and says so
only in a warning. With `--error-log` beside it the console stays silent and
the warning lands in the file, where the runner counts it.

**The locale line.** With `LANG` empty, SUMO 1.27.1 prints `Warning: Could not
set locale to 'C'.` to stderr before it has parsed its options, so neither
`--no-warnings` nor `--error-log` can reach it. It is a property of the shell,
not of the run (measured: silent with `LANG=en_US.UTF-8` or `LC_ALL=C`), so the
console tests pin the locale rather than tolerate stray output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.backend.conftest import Scenario, make_config
from tests.experiments.routes import out_of_order_routes
from traffic_lab.backend import SumoBackend
from traffic_lab.backend.config import count_sumo_warnings


def _drive(scenario: Scenario, routes: Path, log: Path, transport: str, steps: int) -> None:
    backend = SumoBackend()
    backend.start(
        scenario.net,
        routes,
        make_config(transport=transport, error_log_path=log),
        network=scenario.network,
    )
    try:
        for _ in range(steps):
            backend.step()
            backend.project()
    finally:
        backend.close()


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_a_dropped_route_entry_is_logged_and_the_console_is_silent(
    scenario: Scenario,
    tmp_path: Path,
    transport: str,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LC_ALL", "C")
    routes = out_of_order_routes(scenario.built, tmp_path / "ooo.rou.xml")
    log = tmp_path / "sumo-warnings.log"

    _drive(scenario, routes, log, transport, steps=60)

    console = capfd.readouterr()
    if transport == "libsumo":
        assert console.out == ""
        assert console.err == ""
    else:
        # The TraCI *client* prints " Retrying in 1 seconds" while it waits for
        # SUMO's socket. That is Python's connection loop, not a SUMO message;
        # what must not appear is anything SUMO says.
        assert "Warning" not in console.out + console.err
        assert console.err == ""
    assert count_sumo_warnings(log) == 1
    assert "ignoring 'v1'" in log.read_text()


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_a_clean_run_creates_an_empty_log(
    scenario: Scenario, tmp_path: Path, transport: str
) -> None:
    """Zero warnings is a file with none in it, not a missing file."""
    log = tmp_path / "sumo-warnings.log"
    _drive(scenario, scenario.routes, log, transport, steps=60)
    assert log.exists()
    assert count_sumo_warnings(log) == 0


def test_counting_reads_only_warning_lines(tmp_path: Path) -> None:
    log = tmp_path / "log"
    log.write_text("Warning: one\nsomething else\nWarning: two\nError: three\n")
    assert count_sumo_warnings(log) == 2


def test_a_missing_log_is_not_zero_warnings(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        count_sumo_warnings(tmp_path / "never-written.log")
