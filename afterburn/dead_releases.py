"""Detect dead code releases — flag version tags on commits with unwired infrastructure."""

import json
import re
import subprocess
import sys
from pathlib import Path

from afterburn.findings import Finding
from afterburn.scanner import SessionInfo

# Patterns for new symbol definitions in diffs (added lines)
PYTHON_DEF_PATTERN = re.compile(r"^\+\s*(?:def|class)\s+(\w+)")
TS_DEF_PATTERN = re.compile(
    r"^\+\s*(?:export\s+)?(?:function|class|const|let|var)\s+(\w+)"
)

# Version tag pattern
VERSION_TAG_PATTERN = re.compile(r"v?\d+\.\d+(?:\.\d+)?")

# Tag-related patterns in session messages
TAG_SESSION_PATTERNS = [
    re.compile(r"git\s+tag\b", re.IGNORECASE),
    re.compile(r"\btagged\b", re.IGNORECASE),
    re.compile(r"v\d+\.\d+(?:\.\d+)?"),
]


def _run_git(repo_path: str, *args: str) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def find_tags_in_sessions(sessions: list[SessionInfo]) -> list[str]:
    """Scan session JSONL files for git tag creation events.

    Look for messages containing "git tag", "tagged", version patterns,
    or tool_use blocks with git tag commands.
    """
    tags_found: set[str] = set()

    for session in sessions:
        try:
            with open(session.file_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = record.get("message", {})
                    content = msg.get("content", "")

                    # Flatten content blocks
                    if isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                                elif block.get("type") == "tool_use":
                                    # Check tool input for git tag commands
                                    inp = block.get("input", {})
                                    cmd = inp.get("command", "")
                                    if "git tag" in cmd:
                                        # Extract tag name from command
                                        match = re.search(r"git\s+tag\s+(\S+)", cmd)
                                        if match:
                                            tags_found.add(match.group(1))
                            elif isinstance(block, str):
                                text_parts.append(block)
                        content = "\n".join(text_parts)

                    if not isinstance(content, str):
                        continue

                    # Check for tag-related patterns
                    for pattern in TAG_SESSION_PATTERNS:
                        if pattern.search(content):
                            # Try to extract version tags
                            for m in VERSION_TAG_PATTERN.finditer(content):
                                tags_found.add(m.group(0))
                            break

        except (OSError, PermissionError):
            continue

    return sorted(tags_found)


def find_new_symbols_in_range(
    repo_path: str, tag: str, previous_tag: str | None = None
) -> list[dict]:
    """Use git diff to find new function/class definitions added between two tags.

    Returns a list of dicts with keys: name, file, kind (function/class).
    """
    if previous_tag:
        diff_output = _run_git(repo_path, "diff", f"{previous_tag}..{tag}", "--unified=0")
    else:
        # First tag — diff against empty tree
        diff_output = _run_git(
            repo_path, "diff", "4b825dc642cb6eb9a060e54bf899d15f7b422b10", tag, "--unified=0"
        )

    if not diff_output:
        return []

    symbols: list[dict] = []
    current_file: str | None = None

    for line in diff_output.splitlines():
        # Track which file we're in
        if line.startswith("diff --git"):
            match = re.search(r"b/(.+)$", line)
            if match:
                current_file = match.group(1)
            continue

        if not current_file:
            continue

        # Only look at added lines
        if not line.startswith("+"):
            continue

        # Python patterns
        if current_file.endswith(".py"):
            m = PYTHON_DEF_PATTERN.match(line)
            if m:
                name = m.group(1)
                # Skip private/dunder
                if name.startswith("_"):
                    continue
                kind = "class" if line.strip().startswith("+class") or line.strip().startswith("+ class") else "function"
                symbols.append({"name": name, "file": current_file, "kind": kind})

        # TypeScript/JavaScript patterns
        elif current_file.endswith((".ts", ".tsx", ".js", ".jsx")):
            m = TS_DEF_PATTERN.match(line)
            if m:
                name = m.group(1)
                if name in ("if", "else", "for", "while", "return", "switch", "case", "try", "catch"):
                    continue
                kind = "class" if "class " in line else "function"
                symbols.append({"name": name, "file": current_file, "kind": kind})

    return symbols


def check_callers(repo_path: str, symbol_name: str, definition_file: str) -> bool:
    """Grep the codebase for invocations of a symbol.

    Returns True if the symbol has at least one caller outside its own definition file.
    """
    # Use git grep to search tracked files only
    output = _run_git(repo_path, "grep", "-l", "--fixed-strings", symbol_name)
    if not output:
        return False

    for file_path in output.strip().splitlines():
        file_path = file_path.strip()
        if file_path and file_path != definition_file:
            return True

    return False


def detect_dead_releases(repo_path: str) -> list[Finding]:
    """Orchestrate dead release detection.

    Find recent tags, find new symbols per tag, check callers,
    return Findings for any dead code at release time.
    """
    # Get all version tags sorted by creation date
    tag_output = _run_git(
        repo_path, "tag", "--list", "--sort=-version:refname"
    )
    if not tag_output:
        return []

    all_tags = [t.strip() for t in tag_output.strip().splitlines() if t.strip()]
    # Filter to version-like tags
    version_tags = [t for t in all_tags if VERSION_TAG_PATTERN.match(t)]

    if not version_tags:
        return []

    # Limit to recent tags (last 20)
    version_tags = version_tags[:20]

    findings: list[Finding] = []

    for i, tag in enumerate(version_tags):
        previous_tag = version_tags[i + 1] if i + 1 < len(version_tags) else None

        symbols = find_new_symbols_in_range(repo_path, tag, previous_tag)
        if not symbols:
            continue

        dead_symbols: list[dict] = []
        for sym in symbols:
            if not check_callers(repo_path, sym["name"], sym["file"]):
                dead_symbols.append(sym)

        if dead_symbols:
            names = [f"{s['name']} ({s['kind']} in {s['file']})" for s in dead_symbols]
            findings.append(Finding(
                type="friction",
                description=f"Dead code shipped in {tag}: {len(dead_symbols)} unwired symbol(s)",
                confidence=min(1.0, len(dead_symbols) / max(len(symbols), 1)),
                frequency=len(dead_symbols),
                sessions=[],
                evidence=f"Symbols with zero callers at release: {', '.join(names[:10])}",
                verification=f"git diff {previous_tag + '..' + tag if previous_tag else tag} --stat",
                theme="dead_release",
            ))

    return findings
