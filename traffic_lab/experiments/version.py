"""Code and simulator version detection for the run manifest (D-004, D-008).

State files and behaviour are SUMO-version-sensitive (D-032), and reproducing a
result means reproducing the exact code that produced it, dirty tree or not. Both
are always obtainable at run start, before any simulation exists:

- `sumo_version` comes from installed package metadata. SUMO is installed as the
  `eclipse-sumo` PyPI distribution pinned in `uv.lock` (D-004), not a system
  package, so its version is fixed at environment-build time and readable without
  launching a simulator process.
- `code_version` comes from `git`, which is always available for a checkout of
  this repository.
"""

from __future__ import annotations

import subprocess
from importlib.metadata import version as _package_version
from pathlib import Path

_DEFAULT_REPO_DIR = Path(__file__).resolve().parent


def get_code_version(repo_dir: Path = _DEFAULT_REPO_DIR) -> str:
    """Git SHA of HEAD, suffixed `-dirty` if the working tree has uncommitted changes.

    `repo_dir` anchors the git lookup to the `traffic_lab` source location (not the
    process's current working directory), so this is correct however the CLI was
    invoked. `git` walks upward from `repo_dir` to find the repository root itself.

    Raises `RuntimeError` if `repo_dir` is not inside a git working tree, or `git`
    is unavailable — a manifest must never silently omit the code version.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"code_version requires a git checkout at or above {repo_dir}") from exc
    return f"{sha}-dirty" if status.strip() else sha


def get_sumo_version() -> str:
    """The installed `eclipse-sumo` distribution version."""
    return _package_version("eclipse-sumo")
