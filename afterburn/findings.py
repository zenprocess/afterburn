"""Finding data structures and serialization."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 with 'Z' suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Finding:
    """An extracted insight from session analysis."""

    type: str  # friction | pattern | gap
    description: str
    confidence: float
    frequency: int
    sessions: list[str] = field(default_factory=list)
    evidence: str = ""
    verification: str | None = None
    theme: str = ""
    # Optional provenance — populated by callers that know the project context
    # (e.g. a worker that reconstructs sessions per-project). None = unknown,
    # which preserves backward compatibility with existing fixtures and tests.
    project_slug: str | None = None
    # ISO-8601 UTC timestamp recorded when the finding object was created.
    # Lets downstream consumers (dashboards, retention sweeps) reason about
    # "findings produced in the most recent run" without bookkeeping outside
    # the dataclass.
    created_at: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_markdown(self) -> str:
        lines = [f"### {self.description}"]
        lines.append("")
        lines.append(f"**Type**: {self.type} | **Confidence**: {self.confidence:.2f} | **Frequency**: {self.frequency}")
        lines.append(f"**Theme**: {self.theme}")
        lines.append(f"**Sessions**: {len(self.sessions)} sessions")
        if self.evidence:
            lines.append("")
            lines.append(f"> {self.evidence[:500]}")
        if self.verification:
            lines.append("")
            lines.append(f"**Verify**: `{self.verification}`")
        lines.append("")
        return "\n".join(lines)


@dataclass
class SkillCandidate:
    """A proposed new skill identified from session analysis."""

    name: str
    description: str
    steps: list[str] = field(default_factory=list)
    evidence_sessions: list[str] = field(default_factory=list)
    draft_skill_md: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def write_skill_candidates(candidates: list["SkillCandidate"], output_dir: Path) -> None:
    """Write skill candidates to output directory.

    Generates a markdown summary and individual skill drafts.
    """
    if not candidates:
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write summary
    summary_path = output_dir / "skill-candidates.md"
    lines = [
        "# Skill Candidates\n",
        f"*{len(candidates)} skills proposed from correction taxonomy analysis*\n",
    ]
    for i, c in enumerate(candidates, 1):
        lines.append(f"## {i}. {c.name}\n")
        lines.append(f"**{c.description}**\n")
        if c.steps:
            lines.append("Steps:")
            for step in c.steps:
                lines.append(f"- {step}")
            lines.append("")
        if c.draft_skill_md:
            lines.append(f"Draft skill written to `skills/{c.name}.md`\n")
        lines.append("")

    summary_path.write_text("\n".join(lines))

    # Write individual skill drafts
    skills_dir = output_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for c in candidates:
        if c.draft_skill_md:
            skill_path = skills_dir / f"{c.name}.md"
            skill_path.write_text(c.draft_skill_md)


def write_findings(findings: list[Finding], output_dir: Path, fmt: str = "markdown") -> None:
    """Write findings to output files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, list[Finding]] = {}
    for f in findings:
        by_type.setdefault(f.type, []).append(f)

    filenames = {
        "friction": "fix-list",
        "pattern": "pattern-catalog",
        "gap": "skill-gaps",
    }

    for finding_type, items in by_type.items():
        basename = filenames.get(finding_type, finding_type)
        if fmt == "json":
            path = output_dir / f"{basename}.jsonl"
            with open(path, "w") as fh:
                for item in items:
                    fh.write(item.to_json() + "\n")
        else:
            path = output_dir / f"{basename}.md"
            with open(path, "w") as fh:
                fh.write(f"# {finding_type.title()} Findings\n\n")
                fh.write(f"*{len(items)} findings across {len(set(s for i in items for s in i.sessions))} sessions*\n\n")
                for item in sorted(items, key=lambda x: x.frequency, reverse=True):
                    fh.write(item.to_markdown())
                    fh.write("---\n\n")
