"""Analysis passes — extract findings from session JSONL data."""

import json
import re
import sys
from collections import Counter, defaultdict

from afterburn.findings import Finding, SkillCandidate
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

# Correction taxonomy — sub-classifies corrections by type
CORRECTION_TAXONOMY: dict[str, list[str]] = {
    "process": [
        r"\bwhy did you push\b",
        r"\byou should have\b",
        r"\brun .+ first\b",
        r"\bcheck before\b",
        r"\bbefore you\b.*\b(commit|push|deploy|merge)\b",
        r"\bshould.*(have|ve) (checked|tested|asked)\b",
    ],
    "accuracy": [
        r"\bthat'?s wrong\b",
        r"\bincorrect\b",
        r"\bnot right\b",
        r"\bactually it'?s\b",
        r"\bthat'?s not (true|correct|accurate)\b",
        r"\bno,?\s+it'?s\b",
    ],
    "scope": [
        r"\bjust\b",
        r"\bonly\b",
        r"\btoo much\b",
        r"\bi just wanted\b",
        r"\bthat'?s overkill\b",
        r"\bdon'?t need (all|that|this)\b",
        r"\bover.?engineer\b",
    ],
    "tooling": [
        r"\buse .+ instead\b",
        r"\bwrong command\b",
        r"\bnot found\b",
        r"\bpython3 not python\b",
        r"\bwrong tool\b",
        r"\bcommand.*(not|doesn'?t)\b",
    ],
    "missing": [
        r"\byou forgot\b",
        r"\bwhat about\b",
        r"\bis anything else\b",
        r"\bdid you check\b",
        r"\bmissing\b",
        r"\byou (missed|skipped|left out)\b",
    ],
}


def classify_correction(text: str) -> str:
    """Classify a correction message into a taxonomy type.

    Returns the taxonomy type (process, accuracy, scope, tooling, missing)
    or "unclassified" if no pattern matches.
    """
    text_lower = text.lower()
    for taxonomy_type, patterns in CORRECTION_TAXONOMY.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return taxonomy_type
    return "unclassified"


def suggest_remediation(taxonomy_counts: Counter) -> list[str]:
    """Return targeted suggestions based on correction taxonomy distribution.

    Args:
        taxonomy_counts: Counter mapping taxonomy type to count.

    Returns:
        List of actionable suggestion strings for the most frequent types.
    """
    if not taxonomy_counts:
        return []

    suggestions_map = {
        "process": "Add pre-commit hooks or workflow checklists",
        "accuracy": "Add verification steps to CLAUDE.md",
        "scope": "Add scope constraints: 'Answer in N sentences max'",
        "tooling": "Fix environment detection or add tool aliases",
        "missing": "Add completion checklists to skills",
    }

    suggestions = []
    # Sort by count descending, only include types with at least 1 occurrence
    for taxonomy_type, count in taxonomy_counts.most_common():
        if count > 0 and taxonomy_type in suggestions_map:
            suggestions.append(suggestions_map[taxonomy_type])

    return suggestions


def generate_skill_candidates(taxonomy_counts: Counter) -> list[SkillCandidate]:
    """Generate targeted skill candidates from correction taxonomy distribution.

    Maps the most frequent correction types to specific skill templates:
    - High process  -> pre-commit hook skill
    - High accuracy -> verification checklist skill
    - High scope    -> scope constraint skill
    - High tooling  -> environment detection skill (no draft — env-specific)
    - High missing  -> completion checklist skill

    Args:
        taxonomy_counts: Counter mapping taxonomy type to count.

    Returns:
        List of SkillCandidate objects, one per qualifying taxonomy type
        (ordered by frequency, only types with count >= 2).
    """
    if not taxonomy_counts:
        return []

    templates: dict[str, dict] = {
        "process": {
            "name": "pre-commit-guard",
            "description": "Pre-commit hook that enforces workflow steps before committing",
            "steps": [
                "Check for uncommitted test runs",
                "Verify lint passes",
                "Confirm branch is not main/master",
            ],
            "draft_skill_md": (
                "---\n"
                "name: pre-commit-guard\n"
                "description: Enforce workflow steps before committing\n"
                "---\n\n"
                "Before committing, verify:\n"
                "1. Tests pass (`pytest` or project test command)\n"
                "2. Linter passes (`ruff check .` or project lint command)\n"
                "3. You are not on main/master branch\n"
                "4. Changed files are staged intentionally (no accidental additions)\n"
            ),
        },
        "accuracy": {
            "name": "verify-facts",
            "description": "Verification checklist — confirm claims before presenting to user",
            "steps": [
                "Cross-check file paths exist before referencing",
                "Verify function signatures match source",
                "Confirm version numbers against package metadata",
            ],
            "draft_skill_md": (
                "---\n"
                "name: verify-facts\n"
                "description: Verification checklist for factual claims\n"
                "---\n\n"
                "Before presenting information to the user, verify:\n"
                "1. File paths exist on disk\n"
                "2. Function/class names match actual source code\n"
                "3. Version numbers match package.json / pyproject.toml\n"
                "4. API endpoints match route definitions\n"
                "5. CLI flags match argparse/typer definitions\n"
            ),
        },
        "scope": {
            "name": "scope-guard",
            "description": "Scope constraints — do only what was asked, nothing more",
            "steps": [
                "Parse the user request for explicit scope boundaries",
                "List files that are in-scope vs out-of-scope",
                "After completing work, verify no out-of-scope changes",
            ],
            "draft_skill_md": (
                "---\n"
                "name: scope-guard\n"
                "description: Prevent over-engineering and scope creep\n"
                "---\n\n"
                "Before starting work:\n"
                "1. Identify exactly what was requested\n"
                "2. List files that should be touched (and only those)\n"
                "3. If tempted to refactor adjacent code, STOP and ask first\n\n"
                "After completing work:\n"
                "4. Run `git diff --stat` and verify only expected files changed\n"
                "5. If extra files changed, revert them and explain why\n"
            ),
        },
        "tooling": {
            "name": "tool-check",
            "description": "Environment detection — verify tools exist before using them",
            "steps": [
                "Check which runtime is available (python3 vs python)",
                "Detect package manager (npm, yarn, pnpm)",
                "Verify CLI tools exist before invoking",
            ],
            "draft_skill_md": "",  # Environment-specific, no generic draft
        },
        "missing": {
            "name": "completion-checklist",
            "description": "Completion checklist — ensure nothing is forgotten",
            "steps": [
                "Check all imports are added for new references",
                "Verify error handling is present",
                "Confirm edge cases are covered",
                "Ensure documentation is updated if public API changed",
            ],
            "draft_skill_md": (
                "---\n"
                "name: completion-checklist\n"
                "description: Ensure nothing is forgotten before declaring done\n"
                "---\n\n"
                "Before marking work complete, check:\n"
                "1. All new imports are added\n"
                "2. Error handling covers failure cases\n"
                "3. Edge cases are tested or documented\n"
                "4. Public API changes have updated docstrings\n"
                "5. Related tests are updated or added\n"
                "6. No TODO/FIXME left without an issue reference\n"
            ),
        },
    }

    candidates = []
    for taxonomy_type, count in taxonomy_counts.most_common():
        if count < 2:
            continue
        if taxonomy_type not in templates:
            continue
        tmpl = templates[taxonomy_type]
        candidates.append(
            SkillCandidate(
                name=tmpl["name"],
                description=tmpl["description"],
                steps=tmpl["steps"],
                evidence_sessions=[],  # Populated by caller if needed
                draft_skill_md=tmpl["draft_skill_md"],
            )
        )

    return candidates


def extract_taxonomy_from_findings(findings: list[Finding]) -> Counter:
    """Extract correction taxonomy counts from a list of findings.

    Looks for the taxonomy summary finding (theme='correction:summary')
    and parses the breakdown from its evidence field.

    Returns a Counter of taxonomy_type -> count.
    """
    counts: Counter = Counter()
    for f in findings:
        if f.theme == "correction:summary" and f.evidence:
            # Parse "Breakdown: process: 5, accuracy: 3. Remediations: ..."
            import re

            breakdown_match = re.search(
                r"Breakdown:\s*(.+?)\.(?:\s*Remediations:|$)", f.evidence
            )
            if breakdown_match:
                pairs = breakdown_match.group(1).split(",")
                for pair in pairs:
                    pair = pair.strip()
                    parts = pair.rsplit(":", 1)
                    if len(parts) == 2:
                        taxonomy_type = parts[0].strip()
                        try:
                            count = int(parts[1].strip())
                            counts[taxonomy_type] = count
                        except ValueError:
                            pass
    return counts


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
                    if (
                        record.get("type") in ("user", "assistant")
                        and "message" in record
                    ):
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
                                            text_parts.append(
                                                f"[TOOL_ERROR: {block.get('content', '')[:200]}]"
                                            )
                                elif isinstance(block, str):
                                    text_parts.append(block)
                            content = "\n".join(text_parts)
                        messages.append(
                            {
                                "role": msg.get("role", record["type"]),
                                "content": content[:5000],  # Cap per-message size
                                "type": record["type"],
                                "raw_content": msg.get("content"),
                            }
                        )
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
                if (
                    block.get("is_error")
                    and "denied" in str(block.get("content", "")).lower()
                ):
                    denials.append(
                        {
                            "index": i,
                            "tool": block.get("tool_use_id", "unknown"),
                            "reason": str(block.get("content", ""))[:200],
                        }
                    )
    return denials


def _extract_tool_errors(messages: list[dict]) -> list[dict]:
    """Find tool calls that produced errors."""
    errors = []
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if "[TOOL_ERROR:" in content:
            errors.append(
                {
                    "index": i,
                    "error": content[:300],
                }
            )
    return errors


def run_friction_pass(
    sessions: list[SessionInfo], max_sessions: int = 200
) -> list[Finding]:
    """Extract friction signals from sessions."""
    correction_themes: dict[str, list] = defaultdict(list)
    correction_taxonomy_counts: Counter = Counter()
    tool_denial_counts: Counter = Counter()
    error_patterns: Counter = Counter()
    total_analyzed = 0

    # Sort by size descending — analyze biggest (richest) sessions first
    sorted_sessions = sorted(sessions, key=lambda s: s.size_bytes, reverse=True)

    # Split into direct-parse (<10MB) and RLM-required (>=10MB)
    direct = [s for s in sorted_sessions if s.size_bytes < 10 * 1024 * 1024][
        :max_sessions
    ]
    large = [s for s in sorted_sessions if s.size_bytes >= 10 * 1024 * 1024]

    # Analyze large sessions via RLM REPL
    rlm_findings: list[Finding] = []
    if large:
        rlm_findings = _rlm_friction_analysis(large)
        if rlm_findings:
            print(
                f"  RLM analyzed {len(large)} large sessions → {len(rlm_findings)} findings",
                file=sys.stderr,
            )

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
            if any(
                marker in text
                for marker in [
                    "<command-message>",
                    "<command-name>",
                    "Base directory for this skill:",
                    "# /",
                    "## Steps",
                    "## Usage",
                    "---\nname:",
                    "SKILL.md",
                    "<system-reminder>",
                    "system-reminder",
                ]
            ):
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

                    # Sub-classify the correction by taxonomy
                    taxonomy = classify_correction(text)
                    correction_taxonomy_counts[taxonomy] += 1

                    correction_themes[theme].append(
                        {
                            "session_id": session.session_id,
                            "text": text[:500],
                            "context": context,
                            "project": session.project_slug,
                            "taxonomy": taxonomy,
                        }
                    )
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
        # Determine dominant taxonomy for this theme
        theme_taxonomies = Counter(e.get("taxonomy", "unclassified") for e in events)
        dominant_taxonomy = theme_taxonomies.most_common(1)[0][0]
        taxonomy_theme = (
            f"correction:{dominant_taxonomy}"
            if dominant_taxonomy != "unclassified"
            else theme
        )
        findings.append(
            Finding(
                type="friction",
                description=f"User correction: {theme.replace('_', ' ')}",
                confidence=min(1.0, len(events) / total_analyzed)
                if total_analyzed > 0
                else 0,
                frequency=len(events),
                sessions=unique_sessions[:20],
                evidence=f'Example: "{example["text"][:300]}"',
                verification=None,
                theme=taxonomy_theme,
            )
        )

    # Store taxonomy counts and remediation on the findings list as metadata
    # by adding a summary finding when there are classified corrections
    classified = {
        k: v for k, v in correction_taxonomy_counts.items() if k != "unclassified"
    }
    if classified:
        taxonomy_summary = ", ".join(
            f"{t}: {c}" for t, c in sorted(classified.items(), key=lambda x: -x[1])
        )
        remediations = suggest_remediation(correction_taxonomy_counts)
        remediation_text = "; ".join(remediations) if remediations else "None"
        findings.append(
            Finding(
                type="friction",
                description="Correction taxonomy breakdown",
                confidence=1.0,
                frequency=sum(classified.values()),
                sessions=[],
                evidence=f"Breakdown: {taxonomy_summary}. Remediations: {remediation_text}",
                theme="correction:summary",
            )
        )

    # Convert tool denials to findings
    for reason, count in tool_denial_counts.most_common(10):
        if count < 2:
            continue
        findings.append(
            Finding(
                type="friction",
                description=f"Tool denial: {reason[:100]}",
                confidence=min(1.0, count / total_analyzed)
                if total_analyzed > 0
                else 0,
                frequency=count,
                sessions=[],
                evidence=f"Denied {count} times across sessions",
                theme="tool_denial",
            )
        )

    # Convert error patterns to findings
    for error_type, count in error_patterns.most_common(10):
        if count < 3:
            continue
        findings.append(
            Finding(
                type="friction",
                description=f"Recurring error: {error_type}",
                confidence=min(1.0, count / total_analyzed)
                if total_analyzed > 0
                else 0,
                frequency=count,
                sessions=[],
                evidence=f"Occurred {count} times",
                theme="tool_error",
            )
        )

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
    rlm = RLM_REPL(verbose=True)

    for session in large_sessions:
        print(
            f"  [RLM] Analyzing large session {session.session_id[:12]}... ({session.size_bytes / 1024 / 1024:.1f}MB)",
            file=sys.stderr,
        )

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
                        if (
                            record.get("type") in ("user", "assistant")
                            and "message" in record
                        ):
                            msg = record["message"]
                            content = msg.get("content", "")
                            if isinstance(content, list):
                                text_parts = []
                                for block in content:
                                    if (
                                        isinstance(block, dict)
                                        and block.get("type") == "text"
                                    ):
                                        text_parts.append(block.get("text", "")[:2000])
                                content = "\n".join(text_parts)
                            elif isinstance(content, str):
                                content = content[:2000]
                            messages.append(
                                {
                                    "role": msg.get("role", "unknown"),
                                    "content": content,
                                    "index": len(messages),
                                }
                            )
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
                        findings.append(
                            Finding(
                                type="friction",
                                description=item.get("correction", "")[:200],
                                confidence=0.8,
                                frequency=1,
                                sessions=[session.session_id],
                                evidence=item.get("what_went_wrong", "")[:300],
                                theme=item.get("theme", "rlm_detected"),
                            )
                        )
                except json.JSONDecodeError:
                    pass
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        findings.append(
                            Finding(
                                type="friction",
                                description=str(item.get("correction", ""))[:200],
                                confidence=0.8,
                                frequency=1,
                                sessions=[session.session_id],
                                evidence=str(item.get("what_went_wrong", ""))[:300],
                                theme=str(item.get("theme", "rlm_detected")),
                            )
                        )

        except Exception as e:
            print(
                f"  [RLM] Error on session {session.session_id[:12]}: {e}",
                file=sys.stderr,
            )
            continue

    return findings


def run_patterns_pass(
    sessions: list[SessionInfo], max_sessions: int = 200
) -> list[Finding]:
    """Extract successful patterns from sessions."""
    confirmations: dict[str, list] = defaultdict(list)
    total_analyzed = 0

    CONFIRM_PATTERNS = [
        (
            r"\b(yes|yeah|yep|exactly|perfect|great|awesome|nice)\b[.!]*$",
            "explicit_confirmation",
        ),
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

                    confirmations[theme].append(
                        {
                            "session_id": session.session_id,
                            "text": text[:200],
                            "context": context,
                        }
                    )
                    break

    findings: list[Finding] = []
    for theme, events in sorted(confirmations.items(), key=lambda x: -len(x[1])):
        if len(events) < 3:
            continue
        unique_sessions = list(set(e["session_id"] for e in events))
        findings.append(
            Finding(
                type="pattern",
                description=f"Confirmed approach: {theme.replace('_', ' ')}",
                confidence=len(unique_sessions) / total_analyzed
                if total_analyzed > 0
                else 0,
                frequency=len(events),
                sessions=unique_sessions[:20],
                evidence=f'Example confirmation: "{events[0]["text"][:200]}" after: "{events[0]["context"][:200]}"',
                theme=theme,
            )
        )

    return findings


def run_gaps_pass(
    sessions: list[SessionInfo], max_sessions: int = 100
) -> list[Finding]:
    """Detect repeated manual workflows that could be skills."""
    # For gaps, we look for command-message patterns (slash command invocations)
    # and repeated multi-step bash sequences
    skill_invocations: Counter = Counter()
    Counter()

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
        findings.append(
            Finding(
                type="gap",
                description="Skill usage frequency distribution",
                confidence=1.0,
                frequency=sum(skill_invocations.values()),
                sessions=[],
                evidence=f"Top skills: {skills_summary}",
                theme="skill_usage",
            )
        )

    return findings
