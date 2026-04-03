"""Tests for correction taxonomy classification and remediation suggestions."""

from collections import Counter

import pytest

from afterburn.passes import classify_correction, suggest_remediation


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
