"""Narrative session report — enhanced insights with timeframe and project filtering."""

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from afterburn.passes import (
    _extract_messages,
    classify_correction,
    suggest_remediation,
)
from afterburn.scanner import SessionInfo, discover_sessions


def _extract_facets(session: SessionInfo) -> dict:
    """Extract structured facets from a single session without LLM calls.

    Returns metadata about the session: message counts, tool usage,
    user sentiment signals, skill invocations, errors, and timing.
    """
    messages = _extract_messages(session)
    if len(messages) < 2:
        return {}

    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    # Tool usage from assistant messages
    tool_calls = Counter()
    tool_errors = 0
    for msg in messages:
        raw = msg.get("raw_content")
        if isinstance(raw, list):
            for block in raw:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_calls[block.get("name", "unknown")] += 1
                    elif block.get("type") == "tool_result" and block.get("is_error"):
                        tool_errors += 1

    # Skill invocations
    skills_used = []
    for msg in user_msgs:
        text = msg.get("content", "")
        if "<command-message>" in text:
            import re

            match = re.search(r"<command-message>(\w+)</command-message>", text)
            if match:
                skills_used.append(match.group(1))

    # Corrections, confirmations, and correction taxonomy
    import re

    corrections = 0
    confirmations = 0
    correction_taxonomy = Counter()
    for msg in user_msgs:
        text = msg.get("content", "").lower().strip()
        if len(text) > 1000 or not text:
            continue
        # Skip system injections
        if (
            "<command-message>" in text
            or "base directory for this skill" in text.lower()
        ):
            continue
        if any(w in text for w in ["no ", "stop", "wrong", "don't", "undo", "revert"]):
            if not any(
                w in text
                for w in ["no problem", "no worries", "don't worry", "no need"]
            ):
                corrections += 1
                taxonomy = classify_correction(text)
                correction_taxonomy[taxonomy] += 1
        if any(
            w in text for w in ["yes", "perfect", "great", "exactly", "awesome", "nice"]
        ):
            if len(text) < 200:
                confirmations += 1

    # First user prompt (the intent)
    first_prompt = ""
    for msg in user_msgs:
        text = msg.get("content", "").strip()
        if text and "<command-message>" not in text and len(text) > 5:
            first_prompt = text[:300]
            break

    # Detect orchestrator vs agent role
    is_worktree = "worktree" in session.project_slug
    is_orchestrator = not is_worktree

    # Count agent dispatches (orchestrator spawning child agents)
    agents_dispatched = 0
    agents_succeeded = 0
    if is_orchestrator:
        for msg in messages:
            text = msg.get("content", "")
            # Detect dispatch/swarm patterns in orchestrator sessions
            if any(
                kw in text.lower()
                for kw in [
                    "dispatching agent",
                    "agent completed",
                    "/dispatch",
                    "/swarm",
                ]
            ):
                if "dispatch" in text.lower():
                    agents_dispatched += 1
                if any(
                    kw in text.lower()
                    for kw in ["agent completed", "succeeded", "completed successfully"]
                ):
                    agents_succeeded += 1

    return {
        "session_id": session.session_id,
        "project_slug": session.project_slug,
        "size_bytes": session.size_bytes,
        "message_count": len(messages),
        "user_messages": len(user_msgs),
        "assistant_messages": len(assistant_msgs),
        "tool_calls": dict(tool_calls.most_common(10)),
        "total_tool_calls": sum(tool_calls.values()),
        "tool_errors": tool_errors,
        "skills_used": skills_used,
        "corrections": corrections,
        "confirmations": confirmations,
        "correction_taxonomy": dict(correction_taxonomy),
        "first_prompt": first_prompt,
        "is_orchestrator": is_orchestrator,
        "is_agent": is_worktree,
        "agents_dispatched": agents_dispatched,
        "agents_succeeded": agents_succeeded,
    }


def _generate_narrative_llm(
    facets: list[dict], timeframe: str, project: str | None
) -> str:
    """Use LLM to generate the narrative report from facets."""
    from afterburn.vendor.rlm_repl.llm_client import (
        ClaudeCLIClient,
        LLMClient,
        _detect_backend,
    )

    backend = _detect_backend()
    if backend == "claude":
        client = ClaudeCLIClient(model="haiku")
    else:
        client = LLMClient()

    # Aggregate stats
    total_sessions = len(facets)
    total_messages = sum(f.get("message_count", 0) for f in facets)
    total_tools = sum(f.get("total_tool_calls", 0) for f in facets)
    total_errors = sum(f.get("tool_errors", 0) for f in facets)
    total_corrections = sum(f.get("corrections", 0) for f in facets)
    total_confirmations = sum(f.get("confirmations", 0) for f in facets)

    # Tool usage across all sessions
    all_tools = Counter()
    for f in facets:
        all_tools.update(f.get("tool_calls", {}))

    # Skills used
    all_skills = Counter()
    for f in facets:
        all_skills.update(f.get("skills_used", []))

    # Session intents
    intents = [f["first_prompt"] for f in facets if f.get("first_prompt")]

    # Aggregate correction taxonomy counts across all sessions
    all_taxonomy = Counter()
    for f in facets:
        all_taxonomy.update(f.get("correction_taxonomy", {}))

    # Build correction breakdown section
    classified_taxonomy = {k: v for k, v in all_taxonomy.items() if k != "unclassified"}
    if classified_taxonomy:
        taxonomy_lines = "\n".join(
            f"- {t}: {c}"
            for t, c in sorted(classified_taxonomy.items(), key=lambda x: -x[1])
        )
        unclassified_count = all_taxonomy.get("unclassified", 0)
        if unclassified_count:
            taxonomy_lines += f"\n- unclassified: {unclassified_count}"
    else:
        taxonomy_lines = "- (no classified corrections)"

    # Generate remediation suggestions
    remediations = suggest_remediation(all_taxonomy)
    remediation_lines = (
        "\n".join(f"- {s}" for s in remediations) if remediations else "- (none)"
    )

    stats_block = f"""## Session Statistics
- Sessions: {total_sessions}
- Total messages: {total_messages}
- Tool calls: {total_tools}
- Tool errors: {total_errors} ({total_errors / max(total_tools, 1) * 100:.1f}% error rate)
- User corrections: {total_corrections}
- User confirmations: {total_confirmations}
- Satisfaction signal: {total_confirmations / max(total_corrections + total_confirmations, 1) * 100:.0f}% positive

## Correction Breakdown
{taxonomy_lines}

## Top Tools
{chr(10).join(f"- {name}: {count}x" for name, count in all_tools.most_common(10))}

## Skills Used
{chr(10).join(f"- /{name}: {count}x" for name, count in all_skills.most_common(10)) if all_skills else "- (none detected)"}

## Remediation Suggestions
{remediation_lines}
"""

    prompt = f"""You are writing a development activity narrative report. Write in second person ("you").
The timeframe is: {timeframe}
{f"Project: {project}" if project else "All projects"}

Here are the aggregated statistics:

{stats_block}

Here are the first prompts from each session (what the user wanted to do):
{chr(10).join(f'- "{intent[:200]}"' for intent in intents[:30])}

Write a concise narrative report with these sections:
1. **What You Worked On** — summarize the main themes/goals from the session intents (3-5 bullet points)
2. **What Went Well** — based on confirmations vs corrections ratio, tool success rate, and completed work
3. **What Didn't** — based on corrections, tool errors, and friction signals. Include a breakdown of correction types if available.
4. **Patterns** — any recurring themes in what you did or how you worked
5. **Suggestions** — incorporate the remediation suggestions from the data, plus 1-2 additional actionable improvements

Keep it under 500 words. Be specific, reference actual numbers. No fluff."""

    messages = [
        {
            "role": "system",
            "content": "You write concise, data-driven development reports. Second person. No emojis.",
        },
        {"role": "user", "content": prompt},
    ]

    response = client.chat(messages, max_tokens=4096)
    return f"{stats_block}\n---\n\n{response}"


def run_narrative(args) -> None:
    """Generate a narrative session report."""
    sessions_dir = (
        Path(args.sessions_dir)
        if hasattr(args, "sessions_dir") and args.sessions_dir
        else None
    )
    project = args.project if hasattr(args, "project") else None

    # Multi-project support
    projects_list = None
    if hasattr(args, "projects") and args.projects:
        projects_list = [p.strip() for p in args.projects.split(",") if p.strip()]
    project_group = getattr(args, "project_group", None)

    # Determine timeframe
    since = None
    timeframe_label = "all time"
    if hasattr(args, "today") and args.today:
        since = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        timeframe_label = f"today ({since})"
    elif hasattr(args, "week") and args.week:
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        timeframe_label = f"last 7 days (since {since})"
    elif hasattr(args, "month") and args.month:
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        timeframe_label = f"last 30 days (since {since})"
    elif hasattr(args, "since") and args.since:
        since = args.since
        timeframe_label = f"since {since}"

    # Always include worktrees when doing cross-repo correlation
    include_wt = bool(projects_list or project_group)

    sessions = discover_sessions(
        sessions_dir=sessions_dir,
        project=project,
        projects=projects_list,
        project_group=project_group,
        since=since,
        include_worktrees=include_wt,
    )

    if not sessions:
        print(f"No sessions found for {timeframe_label}.")
        sys.exit(0)

    total_size = sum(s.size_bytes for s in sessions)
    print(
        f"Analyzing {len(sessions)} sessions ({total_size / 1024 / 1024:.1f}MB) — {timeframe_label}"
    )

    # Extract facets from all sessions (no LLM needed for this phase)
    facets = []
    for i, session in enumerate(sessions):
        if i % 20 == 0 and i > 0:
            print(f"  Extracting facets: {i}/{len(sessions)}...", file=sys.stderr)
        facet = _extract_facets(session)
        if facet:
            facets.append(facet)

    if not facets:
        print("No analyzable sessions found.")
        sys.exit(0)

    print(f"Extracted facets from {len(facets)} sessions")

    # Generate narrative
    if hasattr(args, "no_llm") and args.no_llm:
        # Stats-only mode
        report = _stats_only_report(facets, timeframe_label, project)
    else:
        print("Generating narrative...", file=sys.stderr)
        report = _generate_narrative_llm(facets, timeframe_label, project)

    # Output
    output_dir = Path(".afterburn")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "narrative.md"

    header = f"# Development Narrative — {timeframe_label}\n\n"
    if project:
        header += f"**Project**: {project}\n\n"
    header += f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"

    full_report = header + report
    report_path.write_text(full_report)
    print(f"\nReport written to {report_path}")
    print("\n" + full_report)


def _stats_only_report(facets: list[dict], timeframe: str, project: str | None) -> str:
    """Generate a stats-only report without LLM calls."""
    total_sessions = len(facets)
    total_messages = sum(f.get("message_count", 0) for f in facets)
    total_tools = sum(f.get("total_tool_calls", 0) for f in facets)
    total_errors = sum(f.get("tool_errors", 0) for f in facets)
    sum(f.get("corrections", 0) for f in facets)
    total_confirmations = sum(f.get("confirmations", 0) for f in facets)

    # Orchestrator / agent breakdown
    orchestrator_facets = [f for f in facets if f.get("is_orchestrator")]
    agent_facets = [f for f in facets if f.get("is_agent")]
    total_dispatched = sum(f.get("agents_dispatched", 0) for f in orchestrator_facets)
    total_succeeded = sum(f.get("agents_succeeded", 0) for f in orchestrator_facets)

    # Only attribute corrections to orchestrator sessions
    orchestrator_corrections = sum(f.get("corrections", 0) for f in orchestrator_facets)

    all_tools = Counter()
    for f in facets:
        all_tools.update(f.get("tool_calls", {}))

    all_skills = Counter()
    for f in facets:
        all_skills.update(f.get("skills_used", []))

    lines = [
        "## Summary",
        f"- **Sessions**: {total_sessions}",
        f"  - Orchestrator sessions: {len(orchestrator_facets)}",
        f"  - Agent sessions: {len(agent_facets)}",
        f"- **Messages**: {total_messages}",
        f"- **Tool calls**: {total_tools} ({total_errors} errors, {total_errors / max(total_tools, 1) * 100:.1f}%)",
        f"- **Corrections** (orchestrator only): {orchestrator_corrections}",
        f"- **Confirmations**: {total_confirmations}",
        f"- **Satisfaction**: {total_confirmations / max(orchestrator_corrections + total_confirmations, 1) * 100:.0f}% positive",
    ]

    if total_dispatched > 0:
        lines.append("")
        lines.append("## Agent Dispatch")
        lines.append(f"- Agents dispatched: {total_dispatched}")
        lines.append(f"- Agents succeeded: {total_succeeded}")
        lines.append(f"- Success rate: {total_succeeded / total_dispatched * 100:.0f}%")

    # Correction taxonomy breakdown
    all_taxonomy = Counter()
    for f in facets:
        all_taxonomy.update(f.get("correction_taxonomy", {}))

    classified_taxonomy = {k: v for k, v in all_taxonomy.items() if k != "unclassified"}
    if classified_taxonomy:
        lines.append("")
        lines.append("## Correction Breakdown")
        for t, c in sorted(classified_taxonomy.items(), key=lambda x: -x[1]):
            lines.append(f"- {t}: {c}")
        unclassified_count = all_taxonomy.get("unclassified", 0)
        if unclassified_count:
            lines.append(f"- unclassified: {unclassified_count}")

    # Remediation suggestions
    remediations = suggest_remediation(all_taxonomy)
    if remediations:
        lines.append("")
        lines.append("## Remediation Suggestions")
        for s in remediations:
            lines.append(f"- {s}")

    lines.append("")
    lines.append("## Top Tools")
    for name, count in all_tools.most_common(10):
        lines.append(f"- {name}: {count}x")

    if all_skills:
        lines.append("")
        lines.append("## Skills Used")
        for name, count in all_skills.most_common(10):
            lines.append(f"- /{name}: {count}x")

    lines.append("")
    lines.append("## Session Intents")
    for f in facets[:20]:
        if f.get("first_prompt"):
            lines.append(f'- "{f["first_prompt"][:150]}"')

    return "\n".join(lines)
