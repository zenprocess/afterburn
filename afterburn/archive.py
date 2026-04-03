"""Archive old sessions to .tgz and clean history."""

import json
import os
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

from afterburn.scanner import default_sessions_dir


def _current_project_slug(cwd: str | None = None) -> str | None:
    """Derive the Claude Code project slug from a working directory path.

    Claude Code encodes the project path as the folder name by replacing
    '/' with '-'. For example:
      /home/user/myproject → -home-user-myproject
    """
    path = cwd or os.getcwd()
    return path.replace("/", "-")


def _find_stale_sessions(
    project_dir: Path,
    max_age_days: int = 7,
) -> list[Path]:
    """Find JSONL session files older than max_age_days."""
    cutoff = time.time() - (max_age_days * 86400)
    stale: list[Path] = []

    for f in sorted(project_dir.glob("*.jsonl")):
        if f.stat().st_mtime < cutoff:
            stale.append(f)

    return stale


def _archive_sessions(
    sessions: list[Path],
    project_dir: Path,
    output_dir: Path | None = None,
) -> Path:
    """Compress sessions into a .tgz archive."""
    dest = output_dir or project_dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_name = f"sessions-archive-{timestamp}.tgz"
    archive_path = dest / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        for session_file in sessions:
            tar.add(session_file, arcname=session_file.name)

    return archive_path


def _clean_history(session_ids: set[str], history_path: Path) -> int:
    """Remove entries for archived sessions from history.jsonl."""
    if not history_path.exists():
        return 0

    kept_lines: list[str] = []
    removed = 0

    with open(history_path) as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                entry = json.loads(line_stripped)
                if entry.get("sessionId") in session_ids:
                    removed += 1
                    continue
            except json.JSONDecodeError:
                pass
            kept_lines.append(line)

    if removed > 0:
        with open(history_path, "w") as f:
            f.writelines(kept_lines)

    return removed


def _clean_session_metadata_dirs(session_ids: set[str], project_dir: Path) -> int:
    """Remove session metadata directories (UUID-named folders) for archived sessions."""
    import shutil

    removed = 0
    for entry in project_dir.iterdir():
        if entry.is_dir() and entry.name in session_ids:
            shutil.rmtree(entry)
            removed += 1
    return removed


def run_archive(args) -> None:
    """Archive old sessions and clean history."""
    cwd = args.cwd if hasattr(args, "cwd") and args.cwd else os.getcwd()
    slug = _current_project_slug(cwd)
    sessions_base = Path(args.sessions_dir) if hasattr(args, "sessions_dir") and args.sessions_dir else default_sessions_dir()
    project_dir = sessions_base / slug

    if not project_dir.exists():
        # Try without leading dash
        if slug and slug.startswith("-"):
            alt_slug = slug
        else:
            alt_slug = f"-{slug}" if slug else None

        if alt_slug:
            project_dir = sessions_base / alt_slug

        if not project_dir.exists():
            print(f"No session directory found for {cwd}")
            print(f"  Looked in: {sessions_base / slug}")
            sys.exit(1)

    max_age = args.days if hasattr(args, "days") and args.days else 7
    stale = _find_stale_sessions(project_dir, max_age_days=max_age)

    if not stale:
        print(f"No sessions older than {max_age} days found in {project_dir}")
        sys.exit(0)

    total_size = sum(f.stat().st_size for f in stale)
    print(f"Found {len(stale)} sessions older than {max_age} days ({total_size / 1024 / 1024:.1f}MB)")

    if args.dry_run:
        print("\n[dry-run] Would archive:")
        for f in stale:
            age_days = (time.time() - f.stat().st_mtime) / 86400
            print(f"  {f.name} ({f.stat().st_size / 1024:.0f}KB, {age_days:.0f} days old)")
        return

    # Archive
    archive_path = _archive_sessions(stale, project_dir)
    archive_size = archive_path.stat().st_size
    print(f"\nArchived to: {archive_path}")
    print(f"  {total_size / 1024 / 1024:.1f}MB → {archive_size / 1024 / 1024:.1f}MB ({archive_size / total_size * 100:.0f}%)")

    # Collect session IDs before deleting
    session_ids = {f.stem for f in stale}

    # Delete archived JSONL files
    for f in stale:
        f.unlink()
    print(f"  Removed {len(stale)} JSONL files")

    # Clean session metadata directories
    dirs_removed = _clean_session_metadata_dirs(session_ids, project_dir)
    if dirs_removed:
        print(f"  Removed {dirs_removed} session metadata directories")

    # Clean history.jsonl
    history_path = Path.home() / ".claude" / "history.jsonl"
    history_cleaned = _clean_history(session_ids, history_path)
    if history_cleaned:
        print(f"  Cleaned {history_cleaned} history entries")

    print(f"\nDone. {len(stale)} sessions archived, history cleaned.")
