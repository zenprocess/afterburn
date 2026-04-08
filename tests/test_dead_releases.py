"""Tests for dead release detection."""

import os
import subprocess

import pytest

from afterburn.dead_releases import (
    check_callers,
    detect_dead_releases,
    find_new_symbols_in_range,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with two tags."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def run_git(*args):
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@t.com",
            },
        )

    run_git("init")
    run_git("config", "user.email", "t@t.com")
    run_git("config", "user.name", "Test")

    # First commit + tag: one function that will be called
    (repo / "lib.py").write_text("def helper():\n    return 42\n")
    (repo / "main.py").write_text("from lib import helper\n\nresult = helper()\n")
    run_git("add", ".")
    run_git("commit", "-m", "initial")
    run_git("tag", "v1.0.0")

    # Second commit + tag: add a called function AND a dead function
    (repo / "lib.py").write_text(
        "def helper():\n    return 42\n\n"
        "def used_func():\n    return 99\n\n"
        "def dead_func():\n    return 0\n"
    )
    (repo / "main.py").write_text(
        "from lib import helper, used_func\n\nresult = helper()\nother = used_func()\n"
    )
    run_git("add", ".")
    run_git("commit", "-m", "add functions")
    run_git("tag", "v2.0.0")

    return str(repo)


def test_detect_dead_releases_finds_dead_function(git_repo):
    """Verify detect_dead_releases flags the unwired function."""
    findings = detect_dead_releases(git_repo)

    assert len(findings) >= 1
    # Should find dead_func as dead code in v2.0.0
    v2_findings = [f for f in findings if "v2.0.0" in f.description]
    assert len(v2_findings) == 1
    assert "dead_func" in v2_findings[0].evidence
    assert v2_findings[0].theme == "dead_release"


def test_detect_dead_releases_does_not_flag_called_function(git_repo):
    """Verify used_func is NOT flagged since it has a caller."""
    findings = detect_dead_releases(git_repo)

    for f in findings:
        assert "used_func" not in f.evidence


def test_find_new_symbols_in_range(git_repo):
    """Verify symbol extraction between two tags."""
    symbols = find_new_symbols_in_range(git_repo, "v2.0.0", "v1.0.0")
    names = {s["name"] for s in symbols}
    assert "used_func" in names
    assert "dead_func" in names
    # helper existed in v1.0.0 already, should not appear
    assert "helper" not in names


def test_check_callers_true(git_repo):
    """Verify check_callers returns True for a called symbol."""
    assert check_callers(git_repo, "helper", "lib.py") is True


def test_check_callers_false(git_repo):
    """Verify check_callers returns False for an uncalled symbol."""
    assert check_callers(git_repo, "dead_func", "lib.py") is False


def test_no_tags_returns_empty(tmp_path):
    """Repo with no tags should return no findings."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=str(repo), capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True
    )
    (repo / "f.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )
    findings = detect_dead_releases(str(repo))
    assert findings == []
