"""Tests for session file discovery and filtering."""

import json
import tempfile
from pathlib import Path

from afterburn.scanner import discover_sessions


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


def test_discover_finds_sessions():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "abc123", size_kb=20)
        _create_session(base, "-home-user-project", "def456", size_kb=20)

        sessions = discover_sessions(sessions_dir=base)
        assert len(sessions) == 2


def test_discover_excludes_worktrees():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "abc123", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-S-001", "wt001", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=False)
        assert len(sessions) == 1
        assert sessions[0].session_id == "abc123"


def test_discover_includes_worktrees_when_flag_set():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "abc123", size_kb=20)
        _create_session(base, "-home-user-project--claude-worktrees-S-001", "wt001", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, include_worktrees=True)
        assert len(sessions) == 2


def test_discover_excludes_small_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-project", "big", size_kb=20)
        _create_session(base, "-home-user-project", "small", size_kb=1)

        sessions = discover_sessions(sessions_dir=base)
        assert len(sessions) == 1
        assert sessions[0].session_id == "big"


def test_discover_filters_by_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        _create_session(base, "-home-user-alpha", "s1", size_kb=20)
        _create_session(base, "-home-user-beta", "s2", size_kb=20)

        sessions = discover_sessions(sessions_dir=base, project="alpha")
        assert len(sessions) == 1
        assert sessions[0].project_slug == "-home-user-alpha"
