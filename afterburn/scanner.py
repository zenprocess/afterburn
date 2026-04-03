"""Session file discovery and filtering."""

import json
import os
import re
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


# Pattern that matches worktree suffixes in project slugs.
# Claude Code worktree slugs look like:
#   -home-user-project--claude-worktrees-agent-abc123
#   -home-user-project--claude-worktrees-S-001
_WORKTREE_SUFFIX_RE = re.compile(r"(--claude-worktrees?-.+)$")


def _extract_parent_slug(slug: str) -> str | None:
    """Extract the parent project slug from a worktree slug.

    Returns the parent slug if this is a worktree slug, else None.
    """
    m = _WORKTREE_SUFFIX_RE.search(slug)
    if m:
        return slug[: m.start()]
    return None


def default_sessions_dir() -> Path:
    """Return the default Claude Code sessions directory."""
    return Path.home() / ".claude" / "projects"


def _expand_project_group(sessions_dir: Path, project_group: str) -> list[str]:
    """Expand a directory path to all project slugs whose path starts with it.

    The project_group is a filesystem path prefix (e.g. /home/user/repos).
    Project slugs encode paths with dashes, so /home/user/repos becomes
    -home-user-repos.  We match any slug that starts with that prefix.
    """
    # Convert path to slug prefix: /home/user/repos -> -home-user-repos
    normalised = project_group.rstrip("/")
    slug_prefix = normalised.replace("/", "-")

    if not sessions_dir.exists():
        return []

    matches = []
    for entry in sorted(sessions_dir.iterdir()):
        if entry.is_dir() and entry.name.startswith(slug_prefix):
            matches.append(entry.name)
    return matches


def discover_sessions(
    sessions_dir: Path | None = None,
    project: str | None = None,
    projects: list[str] | None = None,
    project_group: str | None = None,
    since: str | None = None,
    include_worktrees: bool = False,
    min_size_bytes: int = 10 * 1024,
) -> list[SessionInfo]:
    """Discover session JSONL files matching the given filters.

    Parameters
    ----------
    project : str | None
        Single project slug substring filter (legacy).
    projects : list[str] | None
        List of project slug substrings — a session matches if its slug
        contains any of these.
    project_group : str | None
        A directory path; all project slugs whose encoded path starts with
        this prefix are included.
    """
    base_dir = sessions_dir or default_sessions_dir()
    if not base_dir.exists():
        return []

    # Build the effective project filter list
    project_filters: list[str] | None = None
    if projects or project_group or project:
        project_filters = []
        if project:
            project_filters.append(project)
        if projects:
            project_filters.extend(projects)
        if project_group:
            expanded = _expand_project_group(base_dir, project_group)
            project_filters.extend(expanded)

    sessions: list[SessionInfo] = []

    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue
        slug = entry.name
        if slug == "memory":
            continue
        if not include_worktrees and "worktree" in slug:
            continue
        if project_filters and not any(pf in slug for pf in project_filters):
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


def group_sessions_by_parent(
    sessions: list[SessionInfo],
) -> dict[str, dict[str, list[SessionInfo]]]:
    """Group sessions by parent project slug.

    Worktree sessions are matched to their parent slug.  Non-worktree
    sessions become the "parent_sessions" list for their own slug.

    Returns
    -------
    dict mapping parent_slug -> {
        "parent_sessions": [SessionInfo, ...],
        "child_sessions":  [SessionInfo, ...],
    }
    """
    groups: dict[str, dict[str, list[SessionInfo]]] = {}

    for session in sessions:
        parent_slug = _extract_parent_slug(session.project_slug)

        if parent_slug is not None:
            # This is a worktree / child session
            bucket = groups.setdefault(parent_slug, {"parent_sessions": [], "child_sessions": []})
            bucket["child_sessions"].append(session)
        else:
            # This is a parent (non-worktree) session
            bucket = groups.setdefault(session.project_slug, {"parent_sessions": [], "child_sessions": []})
            bucket["parent_sessions"].append(session)

    return groups


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
