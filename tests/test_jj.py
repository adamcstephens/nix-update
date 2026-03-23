from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from nix_update import is_jj_repo, jj_commit, jj_has_diff
from nix_update.eval import Package, Version

JJ = shutil.which("jj")

pytestmark = pytest.mark.skipif(JJ is None, reason="jj not found in PATH")


def make_package(
    *,
    attribute: str = "test-pkg",
    old_version: str = "1.0.0",
    new_version: str = "2.0.0",
    src_dir: str = "/fake/src",
) -> Package:
    pkg = Package.__new__(Package)
    pkg.attribute = attribute
    pkg.old_version = old_version
    pkg.new_version = Version(number=new_version, rev=None)
    pkg.rev = None
    pkg.diff_url = None
    pkg.changelog = None
    pkg.filename = f"{src_dir}/default.nix"
    pkg.cargo_lock = None
    pkg.raw_version_position = None
    return pkg


@pytest.fixture
def jj_repo(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary colocated jj+git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        monkeypatch.setenv("GIT_AUTHOR_NAME", "nix-update")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "nix-update@example.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "nix-update")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "nix-update@example.com")
        subprocess.run(["jj", "git", "init", "--colocate"], cwd=repo, check=True)
        # Create an initial file and commit so the repo is non-empty
        (repo / "default.nix").write_text("{ }")
        subprocess.run(
            ["jj", "commit", "--message", "initial"],
            cwd=repo,
            check=True,
        )
        yield repo


class TestIsJjRepo:
    def test_true_when_jj_dir_exists(self, jj_repo: Path) -> None:
        assert is_jj_repo(str(jj_repo)) is True

    def test_false_when_no_jj_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assert is_jj_repo(tmpdir) is False


class TestJjHasDiff:
    def test_returns_true_when_diff_has_changes(self, jj_repo: Path) -> None:
        pkg = make_package(src_dir=str(jj_repo))
        (jj_repo / "default.nix").write_text("{ changed = true; }")
        assert jj_has_diff(str(jj_repo), pkg) is True

    def test_returns_false_when_no_changes(self, jj_repo: Path) -> None:
        pkg = make_package(src_dir=str(jj_repo))
        assert jj_has_diff(str(jj_repo), pkg) is False


class TestJjCommit:
    def test_creates_commit_with_message(self, jj_repo: Path) -> None:
        pkg = make_package(
            attribute="hello",
            old_version="1.0.0",
            new_version="2.0.0",
            src_dir=str(jj_repo),
        )
        (jj_repo / "default.nix").write_text("{ version = \"2.0.0\"; }")
        jj_commit(str(jj_repo), pkg)
        log = subprocess.run(
            ["jj", "log", "--no-graph", "--revisions", "@-"],
            cwd=jj_repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert "hello: 1.0.0 -> 2.0.0" in log

    def test_commit_with_unchanged_version(self, jj_repo: Path) -> None:
        """Commit works even when old and new version are the same."""
        pkg = make_package(
            attribute="test-pkg",
            old_version="1.0.0",
            new_version="1.0.0",
            src_dir=str(jj_repo),
        )
        (jj_repo / "default.nix").write_text("{ patched = true; }")
        jj_commit(str(jj_repo), pkg)
        log = subprocess.run(
            ["jj", "log", "--no-graph", "--revisions", "@-"],
            cwd=jj_repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert "test-pkg: 1.0.0 -> 1.0.0" in log
