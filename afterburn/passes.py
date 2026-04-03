"""Analysis passes — extract findings from session JSONL data."""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from afterburn.findings import Finding
from afterburn.scanner import SessionInfo

# Correction signal patterns — high precision, not exhaustive
# These identify clear corrections, not ambiguous phrases
CORRECTION_PATTERNS = [
    (r"\bno[,.]?\s+(don'?t|not|stop|that'?s wrong|that'?s not)", "explicit_correction"),
    (r"\bstop\b.*\b(doing|that|this)\b", "stop_command"),
    (r"\bthat'?s (wrong|incorrect|not right|not what)", "explicit_rejection"),
    (r"\bundo\b|\brevert\b|\broll\s*back\b", "undo_request"),
    (r"\bwhy did you\b.*\b(delete|remove|change|add|modify)\b", "challenge"),
    (r"\bi (said|asked|meant|wanted)\b", "clarification"),
    (r"\bnever\b.*\b(do that|again|use)\b", "strong_prohibition"),
    (r"\bwrong (file|function|approach|direction)\b", "wrong_target"),
]

# Phrases that look like corrections but aren't
FALSE_POSITIVE_PATTERNS = [
    r"\bno\s+(problem|worries|rush|issue|need)\b",
    r"\bdon'?t\s+(worry|bother|need to)\b",
    r"\bstop\s*[-—]\s",  # stop used as pause in thought
    r"\bthat'?s\s+(fine|good|great|perfect|correct)\b",
]


def _extract_messages(session: SessionInfo) -> list[dict]:
    """Extract user and assistant messages from a session JSONL."""
    messages = []
    try:
        with open(session.file_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("type") in ("user", "assistant") and "message" in record:
                        msg = record["message"]
                        content = msg.get("content", "")
                        # Flatten content blocks to text
                        if isinstance(content, list):
                            text_parts = []
                            for block in content:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        text_parts.append(block.get("text", ""))
                                    elif block.get("type") == "tool_result":
                                        # Check for errors in tool results
                                        if block.get("is_error"):
                                            text_parts.append(f"[TOOL_ERROR: {block.get('content', '')[:200]}]")
                                elif isinstance(block, str):
                                    text_parts.append(block)
                            content = "\n".join(text_parts)
                        messages.append({
                            "role": msg.get("role", record["type"]),
                            "content": content[:5000],  # Cap per-message size
                            "type": record["type"],
                            "raw_content": msg.get("content"),
                        })
                except json.JSONDecodeError:
                    continue
    except (OSError, PermissionError):
        pass
    return messages


def _is_false_positive(text: str) -> bool:
    """Check if text matches a false positive pattern."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in FALSE_POSITIVE_PATTERNS)


def _extract_tool_denials(messages: list[dict]) -> list[dict]:
    """Find tool calls that were denied (user rejected)."""
    denials = []
    for i, msg in enumerate(messages):
        if msg["role"] != "user":
            continue
        raw = msg.get("raw_content")
        if not isinstance(raw, list):
            continue
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("is_error") and "denied" in str(block.get("content", "")).lower():
                    denials.append({
                        "index": i,
                        "tool": block.get("tool_use_id", "unknown"),
                        "reason": str(block.get("content", ""))[:200],
                    })
    return denials


def _extract_tool_errors(messages: list[dict]) -> list[dict]:
    """Find tool calls that produced errors."""
    errors = []
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if "[TOOL_ERROR:" in content:
            errors.append({
                "index": i,
                "error": content[:300],
            })
    return errors


def run_friction_pass(sessions: list[SessionInfo], max_sessions: int = 200) -> list[Finding]:
    """Extract friction signals from sessions."""
    correction_themes: dict[str, list] = defaultdict(list)
    tool_denial_counts: Counter = Counter()
    error_patterns: Counter = Counter()
    total_analyzed = 0

    # Sort by size descending — analyze biggest (richest) sessions first
    sorted_sessions = sorted(sessions, key=lambda s: s.size_bytes, reverse=True)

    # Split into direct-parse (<10MB) and RLM-required (>=10MB)
    direct = [s for s in sorted_sessions if s.size_bytes < 10 * 1024 * 1024][:max_sessions]
    large = [s for s in sorted_sessions if s.size_bytes >= 10 * 1024 * 1024]

    # Analyze large sessions via RLM REPL
    rlm_findings: list[Finding] = []
    if large:
        rlm_findings = _rlm_friction_analysis(large)
        if rlm_findings:
            print(f"  RLM analyzed {len(large)} large sessions → {len(rlm_findings)} findings", file=sys.stderr)

    analyzable = direct

    for i, session in enumerate(analyzable):
        if i % 20 == 0:
            print(f"  Scanning session {i + 1}/{len(analyzable)}...", file=sys.stderr)

        messages = _extract_messages(session)
        if len(messages) < 4:
            continue
        total_analyzed += 1

        # Find corrections
        for j, msg in enumerate(messages):
            if msg["role"] != "user":
                continue
            text = msg["content"]
            if not text or len(text) < 3:
                continue
            text_lower = text.lower()

            if _is_false_positive(text):
                continue

            # Skip system injections, skill content, and command messages
            if any(marker in text for marker in [
                "<command-message>", "<command-name>", "Base directory for this skill:",
                "# /", "## Steps", "## Usage", "---\nname:", "SKILL.md",
                "<system-reminder>", "system-reminder",
            ]):
                continue

            # Skip very long messages (>1000 chars) — likely pasted content, not corrections
            if len(text) > 1000:
                continue

            for pattern, theme in CORRECTION_PATTERNS:
                if re.search(pattern, text_lower):
                    # Get context (previous assistant message)
                    context = ""
                    if j > 0:
                        prev = messages[j - 1]["content"]
                        context = prev[:300] if prev else ""

                    correction_themes[theme].append({
                        "session_id": session.session_id,
                        "text": text[:500],
                        "context": context,
                        "project": session.project_slug,
                    })
                    break  # One match per message

        # Find tool denials
        denials = _extract_tool_denials(messages)
        for d in denials:
            tool_denial_counts[d.get("reason", "unknown")[:100]] += 1

        # Find error patterns
        errors = _extract_tool_errors(messages)
        for e in errors:
            # Extract error type
            err_text = e["error"]
            # Normalize common error patterns
            if "exit code" in err_text.lower():
                error_patterns["Command failed (non-zero exit)"] += 1
            elif "permission" in err_text.lower():
                error_patterns["Permission denied"] += 1
            elif "not found" in err_text.lower():
                error_patterns["File/command not found"] += 1
            elif "timeout" in err_text.lower():
                error_patterns["Timeout"] += 1
            else:
                error_patterns["Other tool error"] += 1

    findings: list[Finding] = []

    # Convert correction themes to findings
    for theme, events in sorted(correction_themes.items(), key=lambda x: -len(x[1])):
        if len(events) < 2:
            continue  # Skip one-offs
        unique_sessions = list(set(e["session_id"] for e in events))
        # Pick the most recent/representative example
        example = events[0]
        findings.append(Finding(
            type="friction",
            description=f"User correction: {theme.replace('_', ' ')}",
            confidence=min(1.0, len(events) / total_analyzed) if total_analyzed > 0 else 0,
            frequency=len(events),
            sessions=unique_sessions[:20],
            evidence=f"Example: \"{example['text'][:300]}\"",
            verification=None,
            theme=theme,
        ))

    # Convert tool denials to findings
    for reason, count in tool_denial_counts.most_common(10):
        if count < 2:
            continue
        findings.append(Finding(
            type="friction",
            description=f"Tool denial: {reason[:100]}",
            confidence=min(1.0, count / total_analyzed) if total_analyzed > 0 else 0,
            frequency=count,
            sessions=[],
            evidence=f"Denied {count} times across sessions",
            theme="tool_denial",
        ))

    # Convert error patterns to findings
    for error_type, count in error_patterns.most_common(10):
        if count < 3:
            continue
        findings.append(Finding(
            type="friction",
            description=f"Recurring error: {error_type}",
            confidence=min(1.0, count / total_analyzed) if total_analyzed > 0 else 0,
            frequency=count,
            sessions=[],
            evidence=f"Occurred {count} times",
            theme="tool_error",
        ))

    # Merge RLM findings for large sessions
    if rlm_findings:
        findings.extend(rlm_findings)

    return findings


def _rlm_friction_analysis(large_sessions: list[SessionInfo]) -> list[Finding]:
    """Use RLM REPL to analyze sessions too large for direct parsing."""
    try:
        from afterburn.vendor.rlm_repl import RLM_REPL
    except ImportError as e:
        print(f"  [warn] RLM REPL not available: {e}", file=sys.stderr)
        return []

    findings: list[Finding] = []
    rlm = RLM_REPL(max_iterations=15, verbose=True)

    for session in large_sessions:
        print(f"  [RLM] Analyzing large session {session.session_id[:12]}... ({session.size_bytes / 1024 / 1024:.1f}MB)", file=sys.stderr)

        # Load session as list of message dicts
        messages = []
        try:
            with open(session.file_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("type") in ("user", "assistant") and "message" in record:
                            msg = record["message"]
                            content = msg.get("content", "")
                            if isinstance(content, list):
                                text_parts = []
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text_parts.append(block.get("text", "")[:2000])
                                content = "\n".join(text_parts)
                            elif isinstance(content, str):
                                content = content[:2000]
                            messages.append({
                                "role": msg.get("role", "unknown"),
                                "content": content,
                                "index": len(messages),
                            })
                    except json.JSONDecodeError:
                        continue
        except (OSError, PermissionError):
            continue

        if len(messages) < 10:
            continue

        try:
            result = rlm.completion(
                context=messages,
                query=(
                    "Analyze these conversation messages between a user and an AI assistant. "
                    "Find ALL instances where the user corrected, redirected, or expressed "
                    "frustration with the assistant. For each, extract:\n"
                    "1. What the user said (the correction)\n"
                    "2. What the assistant did wrong (from context)\n"
                    "3. A theme (wrong_approach, scope_creep, wrong_file, ignored_instruction, etc.)\n\n"
                    "Return a Python list of dicts with keys: correction, what_went_wrong, theme\n"
                    "Call FINAL_VAR('findings') when done."
                ),
            )

            # Try to parse the result
            if isinstance(result, str) and result.startswith("["):
                try:
                    parsed = json.loads(result)
                    for item in parsed:
                        findings.append(Finding(
                            type="friction",
                            description=item.get("correction", "")[:200],
                            confidence=0.8,
                            frequency=1,
                            sessions=[session.session_id],
                            evidence=item.get("what_went_wrong", "")[:300],
                            theme=item.get("theme", "rlm_detected"),
                        ))
                except json.JSONDecodeError:
                    pass
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        findings.append(Finding(
                            type="friction",
                            description=str(item.get("correction", ""))[:200],
                            confidence=0.8,
                            frequency=1,
                            sessions=[session.session_id],
                            evidence=str(item.get("what_went_wrong", ""))[:300],
                            theme=str(item.get("theme", "rlm_detected")),
                        ))

        except Exception as e:
            print(f"  [RLM] Error on session {session.session_id[:12]}: {e}", file=sys.stderr)
            continue

    return findings


def run_patterns_pass(sessions: list[SessionInfo], max_sessions: int = 200) -> list[Finding]:
    """Extract successful patterns from sessions."""
    confirmations: dict[str, list] = defaultdict(list)
    total_analyzed = 0

    CONFIRM_PATTERNS = [
        (r"\b(yes|yeah|yep|exactly|perfect|great|awesome|nice)\b[.!]*$", "explicit_confirmation"),
        (r"\bthat'?s (right|correct|it|what i wanted)\b", "explicit_confirmation"),
        (r"\bgood (job|work|call|approach)\b", "praise"),
        (r"\bkeep (doing|going|that)\b", "continuation"),
        (r"\blgtm\b|\bship it\b", "approval"),
    ]

    analyzable = [s for s in sessions if s.size_bytes < 50 * 1024 * 1024][:max_sessions]

    for i, session in enumerate(analyzable):
        if i % 20 == 0:
            print(f"  Scanning session {i + 1}/{len(analyzable)}...", file=sys.stderr)

        messages = _extract_messages(session)
        if len(messages) < 4:
            continue
        total_analyzed += 1

        for j, msg in enumerate(messages):
            if msg["role"] != "user":
                continue
            text = msg["content"]
            if not text or len(text) < 2:
                continue
            text_lower = text.lower().strip()

            # Only match short confirmations (< 200 chars) — long messages are task prompts
            if len(text_lower) > 200:
                continue

            for pattern, theme in CONFIRM_PATTERNS:
                if re.search(pattern, text_lower):
                    # Get what was confirmed (previous assistant message)
                    context = ""
                    if j > 0 and messages[j - 1]["role"] == "assistant":
                        context = messages[j - 1]["content"][:500]

                    confirmations[theme].append({
                        "session_id": session.session_id,
                        "text": text[:200],
                        "context": context,
                    })
                    break

    findings: list[Finding] = []
    for theme, events in sorted(confirmations.items(), key=lambda x: -len(x[1])):
        if len(events) < 3:
            continue
        unique_sessions = list(set(e["session_id"] for e in events))
        findings.append(Finding(
            type="pattern",
            description=f"Confirmed approach: {theme.replace('_', ' ')}",
            confidence=len(unique_sessions) / total_analyzed if total_analyzed > 0 else 0,
            frequency=len(events),
            sessions=unique_sessions[:20],
            evidence=f"Example confirmation: \"{events[0]['text'][:200]}\" after: \"{events[0]['context'][:200]}\"",
            theme=theme,
        ))

    return findings


def run_gaps_pass(sessions: list[SessionInfo], max_sessions: int = 100) -> list[Finding]:
    """Detect repeated manual workflows that could be skills."""
    # For gaps, we look for command-message patterns (slash command invocations)
    # and repeated multi-step bash sequences
    skill_invocations: Counter = Counter()
    command_sequences: Counter = Counter()

    analyzable = [s for s in sessions if s.size_bytes < 50 * 1024 * 1024][:max_sessions]

    for i, session in enumerate(analyzable):
        if i % 20 == 0:
            print(f"  Scanning session {i + 1}/{len(analyzable)}...", file=sys.stderr)

        messages = _extract_messages(session)
        if len(messages) < 4:
            continue

        for msg in messages:
            if msg["role"] != "user":
                continue
            text = msg["content"].strip()

            # Detect slash command usage
            if text.startswith("/") or "<command-message>" in text:
                cmd_match = re.search(r"<command-message>(\w+)</command-message>", text)
                if cmd_match:
                    skill_invocations[cmd_match.group(1)] += 1
                elif text.startswith("/"):
                    cmd = text.split()[0]
                    skill_invocations[cmd] += 1

    findings: list[Finding] = []

    # Report most-used skills (useful for understanding workflow)
    if skill_invocations:
        top_skills = skill_invocations.most_common(20)
        skills_summary = ", ".join(f"{name} ({count}x)" for name, count in top_skills)
        findings.append(Finding(
            type="gap",
            description="Skill usage frequency distribution",
            confidence=1.0,
            frequency=sum(skill_invocations.values()),
            sessions=[],
            evidence=f"Top skills: {skills_summary}",
            theme="skill_usage",
        ))

    return findings
