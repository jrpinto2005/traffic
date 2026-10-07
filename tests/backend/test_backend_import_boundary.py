"""Only `traffic_lab.backend` imports TraCI or LibSUMO; sumolib also in `scenarios/`.

`06_ARCHITECTURE.md` SS10 rule 2, enforcing `00_RESEARCH_SPECIFICATION.md` SS25's
hard boundary "as a test rather than a convention". The rule as clarified on
2026-10-07 also allows `sumolib` -- offline file tooling (binary lookup, net
parsing), never a running simulation -- in `traffic_lab/scenarios/`, which
generates SUMO input files (T1.3 Amendment A5). `traci` and `libsumo` stay
backend-only.

Checked by static AST inspection of each module's own import statements, for the
same reason `tests/domain/test_import_boundary.py` gives: importing the package
and inspecting `sys.modules` would only prove today's transitive closure happens
to be clean, and would pass even where a module directly names a forbidden
import that something else already put on the path.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "traffic_lab"
BACKEND_DIR = PACKAGE_DIR / "backend"
SCENARIOS_DIR = PACKAGE_DIR / "scenarios"

#: The three distributions that speak to SUMO. `sumo` covers any future
#: `sumo.*` module; `eclipse-sumo` ships binaries, not an importable package.
FORBIDDEN_ROOTS = frozenset({"traci", "libsumo", "sumolib", "sumo"})

#: Allowed in `scenarios/` as well as `backend/`: it reads and writes files and
#: finds binaries, and cannot drive a simulation.
OFFLINE_TOOLING_ROOTS = frozenset({"sumolib"})


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_only_the_backend_package_imports_a_sumo_library() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if path.is_relative_to(BACKEND_DIR):
            continue
        forbidden = FORBIDDEN_ROOTS
        if path.is_relative_to(SCENARIOS_DIR):
            forbidden = FORBIDDEN_ROOTS - OFFLINE_TOOLING_ROOTS
        hit = {
            name
            for name in _imported_module_names(path.read_text())
            if name.split(".")[0] in forbidden
        }
        if hit:
            violations[str(path.relative_to(PACKAGE_DIR))] = hit
    assert not violations, (
        f"only traffic_lab/backend may import a SUMO library, and traffic_lab/scenarios "
        f"sumolib (06_ARCHITECTURE.md SS10 rule 2); found: {violations}"
    )


def test_the_backend_package_does_import_one() -> None:
    """The counterpart, so the test above cannot pass by the imports having moved.

    If SUMO stopped being imported anywhere, the boundary test would still pass
    while asserting nothing at all.
    """
    imported: set[str] = set()
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        imported |= {
            name
            for name in _imported_module_names(path.read_text())
            if name.split(".")[0] in FORBIDDEN_ROOTS
        }
    assert {"traci", "libsumo"} <= imported


def test_the_backend_package_depends_only_on_domain() -> None:
    """`06_ARCHITECTURE.md` SS10: `backend/` depends on `domain`, and nothing else."""
    violations: dict[str, set[str]] = {}
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        forbidden = {
            name
            for name in _imported_module_names(path.read_text())
            if name.startswith("traffic_lab.")
            and not name.startswith(("traffic_lab.domain", "traffic_lab.backend"))
        }
        if forbidden:
            violations[str(path.relative_to(PACKAGE_DIR))] = forbidden
    assert not violations, f"backend/ may import only domain/: {violations}"
