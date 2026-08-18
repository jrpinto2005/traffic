"""`traffic_lab.domain` imports nothing from `traffic_lab.*` (D-014 module map).

It is the vocabulary; it cannot depend on users of the vocabulary. Checked by
static AST inspection of each module's own import statements (not by actually
importing the package, which would only prove today's transitive closure is
clean and could pass even if a module directly names a forbidden import that
happens to already be on `sys.path` for another reason).

Cross-module imports *within* `traffic_lab.domain` (e.g. `state.py` importing
IDs from `network.py`) are fine -- the boundary is `traffic_lab.domain`
against the rest of `traffic_lab`, not domain modules against each other.
"""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "traffic_lab" / "domain"


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_no_domain_module_imports_from_outside_traffic_lab_domain() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(DOMAIN_DIR.glob("*.py")):
        imported = _imported_module_names(path.read_text())
        forbidden = {
            name
            for name in imported
            if name == "traffic_lab" or name.startswith("traffic_lab.")
            if not (name == "traffic_lab.domain" or name.startswith("traffic_lab.domain."))
        }
        if forbidden:
            violations[path.name] = forbidden
    assert not violations, f"traffic_lab.domain modules import outside domain: {violations}"


def test_no_domain_module_imports_sumo_traci_or_libsumo() -> None:
    # domain/ needs no simulator (T1.2's own Environment note): it must not
    # import SUMO, TraCI, libsumo, or sumolib either.
    forbidden_prefixes = ("traci", "libsumo", "sumolib", "sumo")
    violations: dict[str, set[str]] = {}
    for path in sorted(DOMAIN_DIR.glob("*.py")):
        imported = _imported_module_names(path.read_text())
        hit = {name for name in imported if name.split(".")[0] in forbidden_prefixes}
        if hit:
            violations[path.name] = hit
    assert not violations, f"traffic_lab.domain modules import a backend package: {violations}"
