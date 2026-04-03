"""Session scanning and 3-pass analysis."""

import json
import sys
from pathlib import Path

from afterburn.findings import Finding, write_findings
from afterburn.scanner import SessionInfo, discover_sessions


def run_discover(args) -> None:
    """Run discovery analysis on session history."""
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else None
    sessions = discover_sessions(
        sessions_dir=sessions_dir,
        project=args.project,
        since=args.since,
        include_worktrees=args.include_worktrees,
    )

    if not sessions:
        print("No sessions found matching filters.")
        sys.exit(0)

    total_size = sum(s.size_bytes for s in sessions)
    print(f"Found {len(sessions)} sessions ({total_size / 1024 / 1024:.1f}MB)")

    output_dir = Path(".afterburn")
    passes = [args.analysis_pass] if args.analysis_pass else ["friction", "patterns", "gaps"]
    all_findings: list[Finding] = []

    for pass_name in passes:
        print(f"\nRunning {pass_name} pass...")
        findings = _run_pass(pass_name, sessions, max_calls=args.max_calls)
        all_findings.extend(findings)
        print(f"  Found {len(findings)} {pass_name} findings")

    write_findings(all_findings, output_dir, fmt=args.format)
    _write_provenance(output_dir, sessions, passes)

    print(f"\nResults written to {output_dir}/")


def _run_pass(pass_name: str, sessions: list[SessionInfo], max_calls: int = 1000) -> list[Finding]:
    """Run a single analysis pass. Placeholder for RLM REPL integration."""
    # TODO: Integrate RLM REPL engine for actual analysis
    # This is the integration point where vendored rlm_repl processes sessions
    print(f"  [stub] {pass_name} pass not yet implemented — requires RLM REPL integration")
    return []


def _write_provenance(output_dir: Path, sessions: list[SessionInfo], passes: list[str]) -> None:
    """Write provenance metadata."""
    from datetime import datetime, timezone

    provenance = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "sessions_count": len(sessions),
        "total_bytes": sum(s.size_bytes for s in sessions),
        "passes": passes,
        "session_ids": [s.session_id for s in sessions],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)


def show_status() -> None:
    """Show last run summary."""
    provenance_path = Path(".afterburn/provenance.json")
    if not provenance_path.exists():
        print("No previous afterburn run found.")
        return

    with open(provenance_path) as f:
        prov = json.load(f)

    print(f"Last run: {prov['analyzed_at']}")
    print(f"Sessions: {prov['sessions_count']} ({prov['total_bytes'] / 1024 / 1024:.1f}MB)")
    print(f"Passes: {', '.join(prov['passes'])}")

    for name in ["fix-list.md", "pattern-catalog.md", "skill-gaps.md"]:
        path = Path(f".afterburn/{name}")
        if path.exists():
            print(f"  {name}: {path.stat().st_size} bytes")
