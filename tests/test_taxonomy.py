"""Tests for correction taxonomy classification, remediation, and skill generation."""

import tempfile
from collections import Counter
from pathlib import Path

import pytest

from afterburn.findings import Finding, SkillCandidate, write_skill_candidates
from afterburn.passes import (
    classify_correction,
    extract_taxonomy_from_findings,
    generate_skill_candidates,
    suggest_remediation,
)


class TestClassifyCorrection:
    """Test that sample correction messages map to the right taxonomy type."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("why did you push to main without asking?", "process"),
            ("you should have run the tests first", "process"),
            ("run lint first before committing", "process"),
            ("check before you deploy", "process"),
            ("you should have checked the tests before merging", "process"),
            ("that's wrong, the port is 8080", "accuracy"),
            ("incorrect, the API returns a list", "accuracy"),
            ("that's not right", "accuracy"),
            ("actually it's called fetchUsers", "accuracy"),
            ("no, it's python3 not python2", "accuracy"),
            ("I just wanted the function name", "scope"),
            ("that's overkill for a simple fix", "scope"),
            ("too much, I only needed the header", "scope"),
            ("just fix the typo, nothing else", "scope"),
            ("only update the tests", "scope"),
            ("use pytest instead of unittest", "tooling"),
            ("wrong command, it should be npm run build", "tooling"),
            ("python3 not python", "tooling"),
            ("command not found, try npx", "tooling"),
            ("you forgot to add the import", "missing"),
            ("what about error handling?", "missing"),
            ("did you check the edge cases?", "missing"),
            ("you missed the return type", "missing"),
            ("you skipped the validation step", "missing"),
        ],
    )
    def test_classification(self, text: str, expected: str) -> None:
        result = classify_correction(text)
        assert result == expected, f"Expected {expected!r} for {text!r}, got {result!r}"

    def test_unclassified_fallback(self) -> None:
        """Messages that don't match any taxonomy pattern return 'unclassified'."""
        result = classify_correction("hello world")
        assert result == "unclassified"

    def test_empty_string(self) -> None:
        result = classify_correction("")
        assert result == "unclassified"


class TestSuggestRemediation:
    """Test that suggest_remediation returns appropriate suggestions."""

    def test_high_process(self) -> None:
        counts = Counter({"process": 10, "accuracy": 1})
        suggestions = suggest_remediation(counts)
        assert any("pre-commit hooks" in s for s in suggestions)

    def test_high_accuracy(self) -> None:
        counts = Counter({"accuracy": 8})
        suggestions = suggest_remediation(counts)
        assert any("verification steps" in s for s in suggestions)

    def test_high_scope(self) -> None:
        counts = Counter({"scope": 5})
        suggestions = suggest_remediation(counts)
        assert any("scope constraints" in s for s in suggestions)

    def test_high_tooling(self) -> None:
        counts = Counter({"tooling": 7})
        suggestions = suggest_remediation(counts)
        assert any("environment detection" in s for s in suggestions)

    def test_high_missing(self) -> None:
        counts = Counter({"missing": 6})
        suggestions = suggest_remediation(counts)
        assert any("completion checklists" in s for s in suggestions)

    def test_empty_counter(self) -> None:
        suggestions = suggest_remediation(Counter())
        assert suggestions == []

    def test_ordering_by_count(self) -> None:
        """Suggestions should be ordered by frequency (most common first)."""
        counts = Counter({"missing": 10, "process": 2, "scope": 5})
        suggestions = suggest_remediation(counts)
        assert len(suggestions) == 3
        # First suggestion should be for "missing" (highest count)
        assert "completion checklists" in suggestions[0]
        # Second should be "scope"
        assert "scope constraints" in suggestions[1]
        # Third should be "process"
        assert "pre-commit hooks" in suggestions[2]

    def test_unclassified_ignored(self) -> None:
        """Unclassified entries should not produce suggestions."""
        counts = Counter({"unclassified": 20})
        suggestions = suggest_remediation(counts)
        assert suggestions == []

    def test_mixed_with_unclassified(self) -> None:
        """Unclassified entries are skipped but classified ones still produce suggestions."""
        counts = Counter({"unclassified": 20, "accuracy": 3})
        suggestions = suggest_remediation(counts)
        assert len(suggestions) == 1
        assert "verification steps" in suggestions[0]


class TestGenerateSkillCandidates:
    """Test skill candidate generation from taxonomy counts."""

    def test_high_process_generates_pre_commit(self) -> None:
        counts = Counter({"process": 5})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 1
        assert candidates[0].name == "pre-commit-guard"
        assert "pre-commit" in candidates[0].draft_skill_md.lower()

    def test_high_accuracy_generates_verify(self) -> None:
        counts = Counter({"accuracy": 3})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 1
        assert candidates[0].name == "verify-facts"

    def test_high_scope_generates_scope_guard(self) -> None:
        counts = Counter({"scope": 4})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 1
        assert candidates[0].name == "scope-guard"

    def test_high_missing_generates_checklist(self) -> None:
        counts = Counter({"missing": 6})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 1
        assert candidates[0].name == "completion-checklist"
        assert "forgotten" in candidates[0].draft_skill_md.lower()

    def test_high_tooling_generates_tool_check(self) -> None:
        counts = Counter({"tooling": 3})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 1
        assert candidates[0].name == "tool-check"
        # Tooling has no generic draft
        assert candidates[0].draft_skill_md == ""

    def test_empty_counter(self) -> None:
        candidates = generate_skill_candidates(Counter())
        assert candidates == []

    def test_below_threshold_excluded(self) -> None:
        """Types with count < 2 should not generate candidates."""
        counts = Counter({"process": 1, "accuracy": 1})
        candidates = generate_skill_candidates(counts)
        assert candidates == []

    def test_unclassified_excluded(self) -> None:
        counts = Counter({"unclassified": 10})
        candidates = generate_skill_candidates(counts)
        assert candidates == []

    def test_multiple_types_ordered_by_frequency(self) -> None:
        counts = Counter({"missing": 8, "process": 3, "scope": 5})
        candidates = generate_skill_candidates(counts)
        assert len(candidates) == 3
        assert candidates[0].name == "completion-checklist"
        assert candidates[1].name == "scope-guard"
        assert candidates[2].name == "pre-commit-guard"

    def test_candidates_have_steps(self) -> None:
        counts = Counter({"accuracy": 4})
        candidates = generate_skill_candidates(counts)
        assert len(candidates[0].steps) > 0


class TestExtractTaxonomyFromFindings:
    """Test extracting taxonomy counts from Finding objects."""

    def test_extracts_from_summary_finding(self) -> None:
        findings = [
            Finding(
                type="friction",
                description="Correction taxonomy breakdown",
                confidence=1.0,
                frequency=10,
                sessions=[],
                evidence="Breakdown: process: 5, accuracy: 3, scope: 2. Remediations: Add pre-commit hooks",
                theme="correction:summary",
            ),
        ]
        counts = extract_taxonomy_from_findings(findings)
        assert counts["process"] == 5
        assert counts["accuracy"] == 3
        assert counts["scope"] == 2

    def test_ignores_non_summary_findings(self) -> None:
        findings = [
            Finding(
                type="friction",
                description="User correction: explicit correction",
                confidence=0.5,
                frequency=3,
                sessions=[],
                evidence="Example: ...",
                theme="correction:process",
            ),
        ]
        counts = extract_taxonomy_from_findings(findings)
        assert len(counts) == 0

    def test_empty_findings(self) -> None:
        counts = extract_taxonomy_from_findings([])
        assert len(counts) == 0

    def test_malformed_evidence(self) -> None:
        findings = [
            Finding(
                type="friction",
                description="Correction taxonomy breakdown",
                confidence=1.0,
                frequency=0,
                sessions=[],
                evidence="Breakdown: garbage data. Remediations: None",
                theme="correction:summary",
            ),
        ]
        counts = extract_taxonomy_from_findings(findings)
        assert len(counts) == 0


class TestWriteSkillCandidates:
    """Test writing skill candidates to disk."""

    def test_writes_summary_and_drafts(self) -> None:
        candidates = [
            SkillCandidate(
                name="pre-commit-guard",
                description="Pre-commit hook skill",
                steps=["Run tests", "Check branch"],
                draft_skill_md="---\nname: pre-commit-guard\n---\n\nDraft content.",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            write_skill_candidates(candidates, Path(tmpdir))
            summary = Path(tmpdir) / "skill-candidates.md"
            assert summary.exists()
            assert "pre-commit-guard" in summary.read_text()
            draft = Path(tmpdir) / "skills" / "pre-commit-guard.md"
            assert draft.exists()
            assert "Draft content" in draft.read_text()

    def test_no_candidates_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            write_skill_candidates([], Path(tmpdir))
            assert not (Path(tmpdir) / "skill-candidates.md").exists()

    def test_empty_draft_not_written(self) -> None:
        """Candidates with empty draft_skill_md should not write a skill file."""
        candidates = [
            SkillCandidate(
                name="tool-check",
                description="Tool check",
                steps=["Check tools"],
                draft_skill_md="",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            write_skill_candidates(candidates, Path(tmpdir))
            assert (Path(tmpdir) / "skill-candidates.md").exists()
            assert not (Path(tmpdir) / "skills" / "tool-check.md").exists()
