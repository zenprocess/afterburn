"""Tests for the RLM REPL sandbox — blocks RCE payloads, preserves benign use.

Covers the two defense-in-depth layers in afterburn.vendor.rlm_repl.sandbox:
1. A minimal __builtins__ allowlist (no __import__, open, eval, exec, compile).
2. A static AST check rejecting import statements and dunder attribute access
   (the `().__class__.__bases__[0].__subclasses__()` escape idiom).

Also covers the opt-in gate in afterburn.passes._rlm_friction_analysis: the
exec path must be disabled by default and only run when
AFTERBURN_ENABLE_RLM_EXEC is set to a truthy value.
"""

import pytest

from afterburn.passes import _rlm_exec_enabled, _rlm_friction_analysis
from afterburn.vendor.rlm_repl.sandbox import REPLSandbox


class TestSandboxBlocksMaliciousPayloads:
    """A transcript-planted payload must never actually execute."""

    def test_blocks_import_os(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute(
            "import os\nprint(os.system('id'))"
        )
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_dunder_import(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute(
            "os_mod = __import__('os')\nprint(os_mod.system('id'))"
        )
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_open(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute(
            "print(open('/etc/passwd').read())"
        )
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_class_hierarchy_escape(self) -> None:
        """The classic no-import RCE idiom: climb from () to os via __class__."""
        sandbox = REPLSandbox()
        payload = (
            "base = ().__class__.__bases__[0]\n"
            "for sub in base.__subclasses__():\n"
            "    pass\n"
        )
        stdout, stderr, _ = sandbox.execute(payload)
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_eval(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute("eval('__import__(\"os\").system(\"id\")')")
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_exec_builtin(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute("exec('import os')")
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_blocks_globals_introspection(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute("print(globals())")
        assert "SandboxViolation" in stderr
        assert stdout == ""

    def test_state_not_corrupted_after_blocked_payload(self) -> None:
        """A blocked payload must not leave __builtins__ or globals tampered."""
        sandbox = REPLSandbox()
        sandbox.execute("import os\nprint(os.system('id'))")
        # Sandbox should still be usable and safe afterward.
        stdout, stderr, has_final = sandbox.execute("FINAL(1 + 1)")
        assert stderr == ""
        assert has_final
        assert sandbox.get_final_answer() == "2"


class TestSandboxAllowsBenignAnalysis:
    """Legitimate analysis code (arithmetic, list/dict/str ops) still works."""

    def test_arithmetic_and_print(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, _ = sandbox.execute("print(1 + 2 * 3)")
        assert stderr == ""
        assert stdout.strip() == "7"

    def test_list_and_string_ops(self) -> None:
        sandbox = REPLSandbox()
        code = (
            "data = ['a', 'bb', 'ccc']\n"
            "lengths = [len(x) for x in data]\n"
            "print(sum(lengths), sorted(lengths), max(lengths))\n"
        )
        stdout, stderr, _ = sandbox.execute(code)
        assert stderr == ""
        assert stdout.strip() == "6 [1, 2, 3] 3"

    def test_context_inspection(self) -> None:
        """Matches the pattern from engine.SYSTEM_PROMPT's own example."""
        sandbox = REPLSandbox()
        sandbox.load_context([{"role": "user", "content": "hi"}] * 5)
        stdout, stderr, _ = sandbox.execute("print(type(context), len(context))")
        assert stderr == ""
        assert "5" in stdout

    def test_final_var(self) -> None:
        sandbox = REPLSandbox()
        stdout, stderr, has_final = sandbox.execute(
            "findings = [{'theme': 'x'}]\nFINAL_VAR('findings')"
        )
        assert stderr == ""
        assert has_final
        assert sandbox.get_final_answer() == "[{'theme': 'x'}]"

    def test_dict_and_counter_style_aggregation(self) -> None:
        sandbox = REPLSandbox()
        code = (
            "counts = {}\n"
            "for word in ['a', 'b', 'a', 'c', 'b', 'a']:\n"
            "    counts[word] = counts.get(word, 0) + 1\n"
            "print(sorted(counts.items()))\n"
        )
        stdout, stderr, _ = sandbox.execute(code)
        assert stderr == ""
        assert stdout.strip() == "[('a', 3), ('b', 2), ('c', 1)]"


class TestRLMExecOptInGate:
    """The exec path must default to disabled and require explicit opt-in."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AFTERBURN_ENABLE_RLM_EXEC", raising=False)
        assert _rlm_exec_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_enabled_by_truthy_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("AFTERBURN_ENABLE_RLM_EXEC", value)
        assert _rlm_exec_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "", "no"])
    def test_not_enabled_by_falsy_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("AFTERBURN_ENABLE_RLM_EXEC", value)
        assert _rlm_exec_enabled() is False

    def test_friction_analysis_skips_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """discover MUST NOT silently exec by default: no sessions, no exec."""
        monkeypatch.delenv("AFTERBURN_ENABLE_RLM_EXEC", raising=False)

        class _FakeSession:
            session_id = "fake"
            size_bytes = 20 * 1024 * 1024
            file_path = "/nonexistent/path.jsonl"
            project_slug = "fake"

        result = _rlm_friction_analysis([_FakeSession()])
        assert result == []
