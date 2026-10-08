"""`traffic_lab.metrics` imports only `traffic_lab.domain` (`06_ARCHITECTURE.md` SS10).

Static AST inspection, for the reason `tests/domain/test_import_boundary.py`
gives: importing the package would only prove today's transitive closure is
clean.
"""

from __future__ import annotations

import ast
from pathlib import Path

METRICS_DIR = Path(__file__).resolve().parents[2] / "traffic_lab" / "metrics"


def _imported_module_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_metrics_depends_only_on_the_domain() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(METRICS_DIR.glob("*.py")):
        forbidden = {
            name
            for name in _imported_module_names(path.read_text())
            if (name.startswith("traffic_lab.") or name.split(".")[0] in {"traci", "libsumo"})
            and not name.startswith(("traffic_lab.domain", "traffic_lab.metrics"))
        }
        if forbidden:
            violations[path.name] = forbidden
    assert not violations, f"metrics/ may import only domain/: {violations}"


def test_the_package_is_not_empty() -> None:
    """So the boundary test cannot pass by the modules having moved."""
    assert len(list(METRICS_DIR.glob("*.py"))) >= 2
