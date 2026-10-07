"""The truth/observation import boundaries (`06_ARCHITECTURE.md` SS4.3 and SS10).

The first and cheapest of the three layers that keep ground truth out of the
control path, and the one SS4.3 says "actually catches things". A controller only
ever receives `Observation` / `EstimatedState` -- in every experimental arm,
including the oracle arm -- because the oracle is a sensor and not a bypass
(SS4.1). There is no path to leak through because there is no path. That holds
only while these three packages stay as the module map (SS10) draws them:

| Package       | May read `TrueState` | Depends on                |
| ------------- | -------------------- | ------------------------- |
| `control/`    | no                   | `domain` (not `backend/`) |
| `estimation/` | no                   | `domain` (not `backend/`) |
| `sensing/`    | yes -- it is a sensor | `domain` (not `backend/`) |

`TrueState` and the parts it is made of (`VehicleState`, `LaneState`,
`RunCounters`) are what must not cross into `control/` and `estimation/`.
`SignalState` is deliberately not forbidden: a controller knows its own signals
exactly (`05_DOMAIN_MODEL.md` SS4.2) and `EstimatedState` carries them.

This is the one canonical version of the test (T1.9). It is checked by static AST
inspection of each module's own imports, matching `tests/domain/test_import_boundary.py`:
importing the package and inspecting it would only prove today's transitive
closure is clean. The detector is itself tested on synthetic sources below, so
the boundary cannot go quiet because the detector stopped seeing things.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "traffic_lab"

#: Package directories under test, by name.
PACKAGES = {name: PACKAGE_DIR / name for name in ("control", "estimation", "sensing")}

#: Packages that must never see ground truth. `sensing/` is absent on purpose.
TRUTH_BLIND = ("control", "estimation")

FORBIDDEN_NAMES = frozenset({"TrueState", "VehicleState", "LaneState", "RunCounters"})

FORBIDDEN_ROOTS = frozenset({"traci", "libsumo", "sumolib"})


@dataclass(frozen=True)
class _Imports:
    """What one module imports and which names it mentions, from its AST alone."""

    #: Every absolute dotted module an import names. For `from m import n` that is
    #: both `m` and `m.n`, since `n` may itself be a module.
    modules: frozenset[str]
    #: Names pulled in by `from ... import name`.
    members: frozenset[str]
    #: Every identifier or attribute name used anywhere in the code.
    mentioned: frozenset[str]
    #: Modules star-imported, whose members a static check cannot list.
    star_imported: frozenset[str]


def _scan(source: str, package: str) -> _Imports:
    """Analyse one module's source. `package` is its own dotted package, for relative imports."""
    modules: set[str] = set()
    members: set[str] = set()
    mentioned: set[str] = set()
    star_imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                # `from ..backend import x` is `traffic_lab.backend` from `traffic_lab.estimation`.
                parts = package.split(".")
                base = parts[: len(parts) - (node.level - 1)]
                module = ".".join([*base, node.module] if node.module else base)
            modules.add(module)
            for alias in node.names:
                if alias.name == "*":
                    star_imported.add(module)
                else:
                    members.add(alias.name)
                    modules.add(f"{module}.{alias.name}")
        elif isinstance(node, ast.Name):
            mentioned.add(node.id)
        elif isinstance(node, ast.Attribute):
            mentioned.add(node.attr)
    return _Imports(
        modules=frozenset(modules),
        members=frozenset(members),
        mentioned=frozenset(mentioned),
        star_imported=frozenset(star_imported),
    )


def _truth_violations(imports: _Imports) -> set[str]:
    """Ground-truth types brought in, mentioned, or hidden behind a star import."""
    hit = set((imports.members | imports.mentioned) & FORBIDDEN_NAMES)
    # `from traffic_lab.domain.state import *` would import them all unnamed.
    hit |= {f"* from {m}" for m in imports.star_imported if m.split(".")[0] == "traffic_lab"}
    return hit


def _sumo_violations(imports: _Imports) -> set[str]:
    return {name for name in imports.modules if name.split(".")[0] in FORBIDDEN_ROOTS}


def _dependency_violations(imports: _Imports, own_package: str) -> set[str]:
    """Anything in `traffic_lab` outside `domain` and the package itself."""
    allowed = ("traffic_lab.domain", own_package)
    return {
        name
        for name in imports.modules
        if name.split(".")[0] == "traffic_lab"
        and not any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed)
    }


def _modules_of(package_name: str) -> dict[str, _Imports]:
    """Every module of a package, recursively, keyed by path relative to `traffic_lab`."""
    result: dict[str, _Imports] = {}
    for path in sorted(PACKAGES[package_name].rglob("*.py")):
        relative = path.relative_to(PACKAGE_DIR)
        package = ".".join(("traffic_lab", *relative.parts[:-1]))
        result[str(relative)] = _scan(path.read_text(), package)
    return result


# --- the boundaries -------------------------------------------------------------------


@pytest.mark.parametrize("package_name", TRUTH_BLIND)
def test_package_does_not_import_true_state(package_name: str) -> None:
    violations = {
        module: hit
        for module, imports in _modules_of(package_name).items()
        if (hit := _truth_violations(imports))
    }
    assert not violations, f"{package_name}/ reaches ground-truth state: {violations}"


@pytest.mark.parametrize("package_name", PACKAGES)
def test_package_does_not_import_a_sumo_library(package_name: str) -> None:
    """Only `backend/` may import TraCI or LibSUMO (`06_ARCHITECTURE.md` SS10)."""
    violations = {
        module: hit
        for module, imports in _modules_of(package_name).items()
        if (hit := _sumo_violations(imports))
    }
    assert not violations, f"{package_name}/ imports a SUMO library: {violations}"


@pytest.mark.parametrize("package_name", PACKAGES)
def test_package_depends_only_on_domain(package_name: str) -> None:
    """`control/`, `estimation/` and `sensing/` depend on `domain`, so never on `backend/`."""
    violations = {
        module: hit
        for module, imports in _modules_of(package_name).items()
        if (hit := _dependency_violations(imports, f"traffic_lab.{package_name}"))
    }
    assert not violations, f"{package_name}/ imports outside domain: {violations}"


@pytest.mark.parametrize("package_name", PACKAGES)
def test_importing_the_package_loads_no_backend_transitively(package_name: str) -> None:
    """The runtime counterpart, over the whole import closure rather than each file's own lines.

    A fresh interpreter imports every module of the package and lists what that
    pulled in. The AST tests catch a module naming a forbidden import; this
    catches one arriving through something the package does import, which is what
    "transitively" in `06_ARCHITECTURE.md` SS4.3 asks for.
    """
    code = (
        "import importlib, pkgutil, sys\n"
        f"package = importlib.import_module('traffic_lab.{package_name}')\n"
        "for info in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):\n"
        "    importlib.import_module(info.name)\n"
        "print(sorted(\n"
        "    name for name in sys.modules\n"
        "    if name.split('.')[0] in {'traci', 'libsumo', 'sumolib'}\n"
        "    or name == 'traffic_lab.backend' or name.startswith('traffic_lab.backend.')\n"
        "))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", (
        f"importing traffic_lab.{package_name} loads a backend: {result.stdout.strip()}"
    )


# --- the boundaries are not vacuous ---------------------------------------------------


@pytest.mark.parametrize("package_name", PACKAGES)
def test_each_package_has_modules_to_check(package_name: str) -> None:
    assert _modules_of(package_name), f"traffic_lab/{package_name} has no modules; nothing checked"


def test_sensing_does_read_true_state() -> None:
    """The counterpart: a sensor is the one place truth enters, so the detector must see it.

    If this stopped holding, the `TRUTH_BLIND` tests could be passing because the
    detector had gone blind rather than because the packages were clean.
    """
    imported = {name for imports in _modules_of("sensing").values() for name in imports.members}
    assert "TrueState" in imported


# --- the detector, on sources that violate each boundary ------------------------------

ESTIMATION = "traffic_lab.estimation"


@pytest.mark.parametrize(
    "source",
    [
        "from traffic_lab.domain.state import TrueState",
        "from traffic_lab.domain.state import TrueState as Truth",
        "from traffic_lab.domain.state import SignalState, VehicleState",
        "from traffic_lab.domain.state import LaneState",
        "from traffic_lab.domain.state import RunCounters",
        "from traffic_lab.domain import state\nx: state.TrueState",
        "import traffic_lab.domain.state as s\ndef f(t: s.LaneState) -> None: ...",
        "from traffic_lab.domain.state import *",
        "from .. import domain\nx: domain.state.RunCounters",
    ],
)
def test_the_truth_detector_catches(source: str) -> None:
    assert _truth_violations(_scan(source, ESTIMATION))


@pytest.mark.parametrize(
    "source",
    [
        "from traffic_lab.domain.state import SignalState",
        "from traffic_lab.domain.observation import EstimatedState, Observation",
        "from traffic_lab.domain.network import LaneId",
    ],
)
def test_the_truth_detector_allows_what_a_controller_may_know(source: str) -> None:
    assert not _truth_violations(_scan(source, ESTIMATION))


@pytest.mark.parametrize(
    "source",
    [
        "import traci",
        "import libsumo as ls",
        "from sumolib import checkBinary",
        "import traci.constants",
    ],
)
def test_the_sumo_detector_catches(source: str) -> None:
    assert _sumo_violations(_scan(source, ESTIMATION))


@pytest.mark.parametrize(
    "source",
    [
        "from traffic_lab.backend import SumoBackend",
        "from traffic_lab.backend.adapter import SumoBackend",
        "import traffic_lab.backend",
        "from traffic_lab import backend",
        "from ..backend import SumoBackend",  # relative imports are resolved, not skipped
        "from ..backend.config import BackendConfig",
        "from .. import backend",
        "from traffic_lab.sensing import OracleSensor",  # a sibling is not `domain` either
        "from ..control import ConstraintLayer",
    ],
)
def test_the_dependency_detector_catches(source: str) -> None:
    assert _dependency_violations(_scan(source, ESTIMATION), ESTIMATION)


@pytest.mark.parametrize(
    "source",
    [
        "from traffic_lab.domain.observation import Observation",
        "from traffic_lab.domain import network",
        "from traffic_lab.estimation.estimator import Estimator",
        "from .estimator import Estimator",
        "from . import estimator",
        "import numpy as np",
    ],
)
def test_the_dependency_detector_allows_domain_and_the_package_itself(source: str) -> None:
    assert not _dependency_violations(_scan(source, ESTIMATION), ESTIMATION)
