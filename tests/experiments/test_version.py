"""Git code-version and SUMO-version detection invariants (D-004, D-008, D-032)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from traffic_lab.experiments.version import get_code_version, get_sumo_version


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "file.txt").write_text("v1\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_clean_tree_has_no_dirty_suffix(clean_repo: Path) -> None:
    version = get_code_version(clean_repo)
    assert not version.endswith("-dirty")
    assert len(version) == 40  # a bare git SHA


def test_dirty_tree_gets_dirty_suffix(clean_repo: Path) -> None:
    """A dirty working tree produces a code_version ending in '-dirty' (ticket acceptance)."""
    (clean_repo / "file.txt").write_text("v2 — uncommitted\n")
    version = get_code_version(clean_repo)
    assert version.endswith("-dirty")


def test_dirty_suffix_wraps_the_real_sha(clean_repo: Path) -> None:
    clean_sha = get_code_version(clean_repo)
    (clean_repo / "file.txt").write_text("v2\n")
    dirty_version = get_code_version(clean_repo)
    assert dirty_version == f"{clean_sha}-dirty"


def test_untracked_file_also_counts_as_dirty(clean_repo: Path) -> None:
    (clean_repo / "untracked.txt").write_text("new\n")
    assert get_code_version(clean_repo).endswith("-dirty")


def test_not_a_git_repo_raises(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    with pytest.raises(RuntimeError):
        get_code_version(not_a_repo)


def test_sumo_version_matches_pinned_lockfile_version() -> None:
    """D-004: SUMO is pinned in uv.lock; the manifest must report that exact version."""
    assert get_sumo_version() == "1.27.1"
