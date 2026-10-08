"""Running SUMO's command-line tools (`jtrrouter`, `sumo`) as subprocesses.

`scenarios/` may find and run SUMO binaries through `sumolib`, never drive a
simulation through `traci` or `libsumo` (`06_ARCHITECTURE.md` SS10 rule 2).
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
from collections.abc import Sequence

import sumolib


class SumoToolError(RuntimeError):
    """A SUMO tool failed, or warned about files this package generated."""


def run_tool(
    name: str,
    args: Sequence[str],
    *,
    allow_failure: bool = False,
    expected_warnings: Sequence[str] = (),
) -> tuple[int, str]:
    """Run SUMO tool `name` with `args`; returns (exit code, combined output).

    Any warning raises: the files fed to these tools are generated here, so a
    warning about them is a generator defect, not noise (as in
    `generator._netconvert`). `LC_ALL=C` silences SUMO's "Could not set locale"
    and `--xml-validation never` its "SUMO_HOME is not set ... disabling XML
    validation": both describe the process, not the files, and the second only
    makes explicit what SUMO does anyway. A warning starting with one of
    `expected_warnings` is a known property of the input and passes. A non-zero exit raises unless
    `allow_failure`, for a caller that must read the errors first.
    """
    argv = [sumolib.checkBinary(name), *args, "--xml-validation", "never"]
    result = subprocess.run(
        argv, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"}, check=False
    )
    output = result.stdout + result.stderr
    warnings = [
        line
        for line in output.splitlines()
        if line.startswith("Warning")
        and not any(line.startswith(f"Warning: {w}") for w in expected_warnings)
    ]
    if warnings:
        raise SumoToolError(f"{name} warned:\n" + "\n".join(warnings))
    if result.returncode != 0 and not allow_failure:
        raise SumoToolError(f"{name} failed ({result.returncode}):\n{output}")
    return result.returncode, output


@functools.cache
def sumo_version() -> str:
    """The version of the `sumo` binary this environment runs, e.g. `1.27.1`."""
    result = subprocess.run(
        [sumolib.checkBinary("sumo"), "--version"],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        check=True,
    )
    match = re.match(r"Eclipse SUMO sumo (\S+)", result.stdout)
    if match is None:
        raise SumoToolError(f"cannot read the SUMO version from: {result.stdout[:200]!r}")
    return match.group(1)
