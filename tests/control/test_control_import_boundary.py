"""`traffic_lab.control` does not import `TrueState` (`06_ARCHITECTURE.md` SS4.3).

The first and cheapest of the three layers that keep ground truth out of the
control path, and the one SS4.3 says "actually catches things". `control/`
depends on `domain` **minus `TrueState`** (SS10's module map), so a controller
only ever receives `Observation` / `EstimatedState` -- in every experimental arm,
including the oracle arm. There is no path to leak through because there is no
path.

T1.9 owns the canonical version of this test, which will cover the sensing and
estimation packages too. This one exists because `control/` is created here and
an unchecked boundary between now and then is an unchecked boundary.

Checked by static AST inspection of each module's own imports, matching
`tests/domain/test_import_boundary.py`: importing the package and inspecting it
would only prove today's transitive closure is clean.
"""

from __future__ import annotations

import ast
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parents[2] / "traffic_lab" / "control"

# `SignalState` is deliberately not on this list. A controller knows its own
# signals exactly (`05_DOMAIN_MODEL.md` SS4.2) and `EstimatedState` carries them,
# so importing the type is legitimate; `TrueState` is the thing that must not
# cross.
FORBIDDEN_NAMES = frozenset({"TrueState", "VehicleState", "LaneState", "RunCounters"})

FORBIDDEN_MODULES = ("traci", "libsumo", "sumolib")


def _imports(source: str) -> tuple[set[str], set[str]]:
    """(imported module names, imported member names) of one module's own imports."""
    modules: set[str] = set()
    members: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                modules.add(node.module)
            members.update(alias.name for alias in node.names)
    return modules, members


def test_control_does_not_import_true_state() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(CONTROL_DIR.glob("*.py")):
        _, members = _imports(path.read_text())
        hit = members & FORBIDDEN_NAMES
        if hit:
            violations[path.name] = hit
    assert not violations, f"control modules import ground-truth state: {violations}"


def test_control_does_not_import_a_backend() -> None:
    """Only `backend/` may import TraCI or LibSUMO (`06_ARCHITECTURE.md` SS10)."""
    violations: dict[str, set[str]] = {}
    for path in sorted(CONTROL_DIR.glob("*.py")):
        modules, _ = _imports(path.read_text())
        hit = {name for name in modules if name.split(".")[0] in FORBIDDEN_MODULES}
        if hit:
            violations[path.name] = hit
    assert not violations, f"control modules import a backend package: {violations}"


def test_control_depends_only_on_domain() -> None:
    """`control/` depends on `domain` and nothing else in the project."""
    violations: dict[str, set[str]] = {}
    for path in sorted(CONTROL_DIR.glob("*.py")):
        modules, _ = _imports(path.read_text())
        hit = {
            name
            for name in modules
            if name.startswith("traffic_lab")
            and not (name == "traffic_lab.domain" or name.startswith("traffic_lab.domain."))
            and not (name == "traffic_lab.control" or name.startswith("traffic_lab.control."))
        }
        if hit:
            violations[path.name] = hit
    assert not violations, f"control modules import outside domain: {violations}"
