"""Tests for cross-repo session correlation (issue #1)."""

import json
import tempfile
from pathlib import Path

from afterburn.scanner import (
    _extract_parent_slug,
    discover_sessions,
    group_sessions_by_parent,
)


def _create_session(base_dir: Path, slug: str, session_id: str, size_kb: int = 20) -> Path:
    """Create a fake session JSONL file."""
    project_dir = base_dir / slug
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / f"{session_id}.jsonl"
    content = json.dumps({"type": "user", "message": {"role": "user", "content": "test"}})
    # Pad to desired size
    lines = [content] * max(1, (size_kb * 1024) // len(content))
    session_file.write_text("\n".join(lines))
    return session_file


# --- _extract_parent_slug ---


def test_extract_parent_slug_worktree():
    slug = "-home-user-project--claude-worktrees-agent-abc123"
    assert _extract_parent_slug(slug) == "-home-user-project"


def test_extract_parent_slug_worktree_short_suffix():
    slug = "-home-user-myapp--claude-worktrees-S-001"
    assert _extract_parent_slug(slug) == "-home-user-myapp"


def test_extract_parent_slug_non_worktree():
    slug = "-home-user-project"
    assert _extract_parent_slug(slug) is None


def test_extract_parent_slug_worktree_in_middle():
    """A slug with 'worktree' that does NOT match the suffix pattern should return None."""
    slug = "-home-user-worktree-project"
    assert _extract_parent_slug(slug) is None


# --- group_sessions_by_parent ---


def test_group_sessions_parent_and_children():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "parent1", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-agent-aaa", "child1", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-agent-bbb", "child2", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=True)
        groups = group_sessions_by_parent(sessions)

        assert "-home-user-project" in groups
        grp = groups["-home-user-project"]
        assert len(grp["parent_sessions"]) == 1
        assert len(grp["child_sessions"]) == 2
        assert grp["parent_sessions"][0].session_id == "parent1"
        child_ids = sorted(s.session_id for s in grp["child_sessions"])
        assert child_ids == ["child1", "child2"]


def test_group_sessions_orphan_children():
    """Worktree sessions whose parent has no sessions still form a group."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-proj--claude-worktrees-agent-x", "orphan1", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=True)
        groups = group_sessions_by_parent(sessions)

        assert "-home-user-proj" in groups
        grp = groups["-home-user-proj"]
        assert len(grp["parent_sessions"]) == 0
        assert len(grp["child_sessions"]) == 1


def test_group_sessions_no_worktrees():
    """Non-worktree sessions each become their own parent group."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-alpha", "s1", size_kb=20)
        _create_session(base, "-home-user-beta", "s2", size_kb=20)

        sessions = discover_sessions(sessions_dir=base)
        groups = group_sessions_by_parent(sessions)

        assert len(groups) == 2
        assert len(groups["-home-user-alpha"]["parent_sessions"]) == 1
        assert len(groups["-home-user-alpha"]["child_sessions"]) == 0


def test_group_sessions_multiple_parents():
    """Multiple parent projects with their own worktree children."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-alpha", "a1", size_kb=20)
        _create_session(base, "-home-user-alpha--claude-worktrees-S-001", "ac1", size_kb=20)
        _create_session(base, "-home-user-beta", "b1", size_kb=20)
        _create_session(base, "-home-user-beta--claude-worktrees-S-002", "bc1", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=True)
        groups = group_sessions_by_parent(sessions)

        assert len(groups) == 2
        assert len(groups["-home-user-alpha"]["parent_sessions"]) == 1
        assert len(groups["-home-user-alpha"]["child_sessions"]) == 1
        assert len(groups["-home-user-beta"]["parent_sessions"]) == 1
        assert len(groups["-home-user-beta"]["child_sessions"]) == 1


# --- Multi-project discovery ---


def test_discover_with_projects_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-alpha", "s1", size_kb=20)
        _create_session(base, "-home-user-beta", "s2", size_kb=20)
        _create_session(base, "-home-user-gamma", "s3", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, projects=["alpha", "gamma"])
        slugs = sorted(s.project_slug for s in sessions)
        assert slugs == ["-home-user-alpha", "-home-user-gamma"]


def test_discover_with_project_group():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-repos-alpha", "s1", size_kb=20)
        _create_session(base, "-home-user-repos-beta", "s2", size_kb=20)
        _create_session(base, "-home-user-other", "s3", size_kb=20)

        sessions = discover_sessions(
            sessions_dir=base,
            project_group="/home/user/repos",
        )
        slugs = sorted(s.project_slug for s in sessions)
        assert slugs == ["-home-user-repos-alpha", "-home-user-repos-beta"]


def test_discover_projects_and_project_combined():
    """--project and --projects can be used together (union)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-alpha", "s1", size_kb=20)
        _create_session(base, "-home-user-beta", "s2", size_kb=20)
        _create_session(base, "-home-user-gamma", "s3", size_kb=20)

        sessions = discover_sessions(
            sessions_dir=base,
            project="alpha",
            projects=["gamma"],
        )
        slugs = sorted(s.project_slug for s in sessions)
        assert slugs == ["-home-user-alpha", "-home-user-gamma"]


# --- Worktree identification ---


def test_worktree_sessions_identified_as_children():
    """Sessions from worktree slugs are identified as children in the group."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "orchestrator", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-agent-abc", "agent1", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-agent-def", "agent2", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=True)
        groups = group_sessions_by_parent(sessions)

        parent_group = groups["-home-user-project"]

        # Parent sessions are orchestrators
        for s in parent_group["parent_sessions"]:
            assert "worktree" not in s.project_slug

        # Child sessions are from worktree slugs
        for s in parent_group["child_sessions"]:
            assert "worktree" in s.project_slug
