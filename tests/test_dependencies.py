"""Dependency exclusions that a test enforces rather than a comment (D-004).

pyarrow is the reflexive companion to "Parquet", so someone will propose adding it,
or it will arrive transitively. It must not: libsumo bundles its own libarrow, both
register the `file` filesystem scheme in one process, and `pyarrow.parquet.write_table`
then fails with `ArrowKeyError` -- after the simulation has run, on every run of every
sweep. polars and duckdb read and write Parquet natively without it. Evidence is in
`research/M0_environment.md`, Finding 2.
"""

from __future__ import annotations

import importlib.util


def test_pyarrow_is_not_installed() -> None:
    assert importlib.util.find_spec("pyarrow") is None, (
        "pyarrow is installed. It collides with libsumo's bundled libarrow and breaks "
        "Parquet writes in the runner process (D-004, research/M0_environment.md). "
        "Find what pulled it in with `uv tree --invert --package pyarrow`."
    )
