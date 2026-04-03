"""Tests for session archiving and history cleanup."""

import json
import os
import tarfile
import tempfile
import time
from pathlib import Path

from afterburn.archive import (
    _archive_sessions,
    _clean_history,
    _current_project_slug,
    _find_stale_sessions,
)


def test_current_project_slug():
    assert _current_project_slug("/home/user/myproject") == "-home-user-myproject"
    assert _current_project_slug("/home/dev/webapp") == "-home-dev-webapp"


def test_find_stale_sessions():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create a "stale" file (backdate mtime by 10 days)
        stale = project_dir / "old-session.jsonl"
        stale.write_text('{"type":"user"}\n')
        os.utime(stale, (time.time() - 86400 * 10, time.time() - 86400 * 10))

        # Create a "fresh" file
        fresh = project_dir / "new-session.jsonl"
        fresh.write_text('{"type":"user"}\n')

        found = _find_stale_sessions(project_dir, max_age_days=7)
        assert len(found) == 1
        assert found[0].name == "old-session.jsonl"


def test_archive_sessions():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        s1 = project_dir / "session1.jsonl"
        s2 = project_dir / "session2.jsonl"
        s1.write_text('{"type":"user","message":{"role":"user","content":"hello"}}\n' * 100)
        s2.write_text('{"type":"assistant","message":{"role":"assistant","content":"hi"}}\n' * 50)

        archive_path = _archive_sessions([s1, s2], project_dir)
        assert archive_path.exists()
        assert archive_path.suffix == ".tgz"

        # Verify contents
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
            assert "session1.jsonl" in names
            assert "session2.jsonl" in names


def test_clean_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "history.jsonl"
        entries = [
            json.dumps({"display": "hello", "sessionId": "keep-me"}),
            json.dumps({"display": "test", "sessionId": "remove-me"}),
            json.dumps({"display": "world", "sessionId": "keep-me-too"}),
            json.dumps({"display": "bye", "sessionId": "remove-me"}),
        ]
        history_path.write_text("\n".join(entries) + "\n")

        removed = _clean_history({"remove-me"}, history_path)
        assert removed == 2

        remaining = history_path.read_text().strip().split("\n")
        assert len(remaining) == 2
        assert all("remove-me" not in line for line in remaining)


def test_find_stale_sessions_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        found = _find_stale_sessions(Path(tmpdir), max_age_days=7)
        assert found == []
