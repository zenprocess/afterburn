"""Tests for finding data structures."""

import json
import tempfile
from pathlib import Path

from afterburn.findings import Finding, write_findings


def test_finding_to_json():
    f = Finding(
        type="friction",
        description="Agent adds console.log",
        confidence=0.85,
        frequency=12,
        sessions=["abc", "def"],
        evidence="User said 'remove the console.log'",
        verification="grep -r 'console.log' src/",
        theme="code_quality",
    )
    data = json.loads(f.to_json())
    assert data["type"] == "friction"
    assert data["frequency"] == 12


def test_finding_to_markdown():
    f = Finding(
        type="pattern",
        description="Always run tests before commit",
        confidence=0.92,
        frequency=8,
        sessions=["a", "b", "c"],
        theme="workflow",
    )
    md = f.to_markdown()
    assert "### Always run tests before commit" in md
    assert "0.92" in md


def test_write_findings_markdown():
    with tempfile.TemporaryDirectory() as tmpdir:
        findings = [
            Finding(type="friction", description="test1", confidence=0.5, frequency=3),
            Finding(type="pattern", description="test2", confidence=0.8, frequency=5),
        ]
        write_findings(findings, Path(tmpdir), fmt="markdown")
        assert (Path(tmpdir) / "fix-list.md").exists()
        assert (Path(tmpdir) / "pattern-catalog.md").exists()


def test_write_findings_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        findings = [
            Finding(type="friction", description="test1", confidence=0.5, frequency=3),
        ]
        write_findings(findings, Path(tmpdir), fmt="json")
        path = Path(tmpdir) / "fix-list.jsonl"
        assert path.exists()
        data = json.loads(path.read_text().strip())
        assert data["type"] == "friction"
