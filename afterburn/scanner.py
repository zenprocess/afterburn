"""Session file discovery and filtering."""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SessionInfo:
    """Metadata about a discovered session file."""

    session_id: str
    project_slug: str
    file_path: Path
    size_bytes: int
    mtime: float
    first_timestamp: str | None = None
    message_count: int = 0


def default_sessions_dir() -> Path:
    """Return the default Claude Code sessions directory."""
    return Path.home() / ".claude" / "projects"


def discover_sessions(
    sessions_dir: Path | None = None,
    project: str | None = None,
    since: str | None = None,
    include_worktrees: bool = False,
    min_size_bytes: int = 10 * 1024,
) -> list[SessionInfo]:
    """Discover session JSONL files matching the given filters."""
    base_dir = sessions_dir or default_sessions_dir()
    if not base_dir.exists():
        return []

    sessions: list[SessionInfo] = []

    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue
        slug = entry.name
        if slug == "memory":
            continue
        if not include_worktrees and "worktree" in slug:
            continue
        if project and project not in slug:
            continue

        for jsonl_file in sorted(entry.glob("*.jsonl")):
            if jsonl_file.stat().st_size < min_size_bytes:
                continue

            session_id = jsonl_file.stem
            stat = jsonl_file.stat()

            if since:
                since_dt = datetime.fromisoformat(since)
                file_dt = datetime.fromtimestamp(stat.st_mtime)
                if file_dt < since_dt:
                    continue

            info = SessionInfo(
                session_id=session_id,
                project_slug=slug,
                file_path=jsonl_file,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
            )
            sessions.append(info)

    return sessions


def read_session_metadata(session: SessionInfo) -> SessionInfo:
    """Read the first few lines of a session to extract metadata."""
    try:
        count = 0
        first_ts = None
        with open(session.file_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    count += 1
                    if first_ts is None and "message" in record:
                        # Try to extract timestamp from snapshot or sessionId
                        if "snapshot" in record and "timestamp" in record["snapshot"]:
                            first_ts = record["snapshot"]["timestamp"]
                except json.JSONDecodeError:
                    continue
        session.message_count = count
        session.first_timestamp = first_ts
    except (OSError, PermissionError):
        pass
    return session
