"""REPL sandbox — executes Python code with injected tools."""

import io
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout


class REPLSandbox:
    """Python REPL environment with injected context and tools.

    The sandbox provides:
    - `context`: the data to analyze (loaded externally)
    - `llm_query(prompt)`: make a recursive sub-LLM call
    - `FINAL(answer)`: signal completion with a string answer
    - `FINAL_VAR(name)`: signal completion, return a variable's value

    All state persists across exec() calls within the same sandbox.
    """

    def __init__(self, llm_query_fn=None):
        self._final_answer = None
        self._final_var_name = None
        self._globals: dict = {
            "__builtins__": __builtins__,
            "llm_query": llm_query_fn or (lambda p: "[no LLM configured]"),
            "FINAL": self._handle_final,
            "FINAL_VAR": self._handle_final_var,
        }

    def load_context(self, context) -> str:
        """Load context data into the sandbox and return a description."""
        self._globals["context"] = context
        ctx_type = type(context).__name__
        if isinstance(context, list):
            return f"context is a list with {len(context)} items"
        elif isinstance(context, dict):
            return f"context is a dict with keys: {list(context.keys())[:10]}"
        elif isinstance(context, str):
            return f"context is a string with {len(context)} characters"
        else:
            return f"context is {ctx_type}"

    def execute(self, code: str, timeout_chars: int = 500_000) -> tuple[str, str, bool]:
        """Execute Python code in the sandbox.

        Returns (stdout, stderr, has_final_answer).
        """
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(code, self._globals)
        except Exception:
            stderr_buf.write(traceback.format_exc())

        stdout = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()

        # Truncate to avoid blowing up context
        if len(stdout) > timeout_chars:
            stdout = stdout[:timeout_chars] + f"\n[TRUNCATED at {timeout_chars} chars]"
        if len(stderr) > timeout_chars:
            stderr = stderr[:timeout_chars] + f"\n[TRUNCATED at {timeout_chars} chars]"

        has_final = self._final_answer is not None or self._final_var_name is not None
        return stdout, stderr, has_final

    def get_final_answer(self) -> str | None:
        """Get the final answer if FINAL() or FINAL_VAR() was called."""
        if self._final_answer is not None:
            return str(self._final_answer)
        if self._final_var_name is not None:
            val = self._globals.get(self._final_var_name)
            return str(val) if val is not None else None
        return None

    def _handle_final(self, answer):
        self._final_answer = answer
        return answer

    def _handle_final_var(self, variable_name: str):
        self._final_var_name = variable_name
        val = self._globals.get(variable_name, f"[variable '{variable_name}' not found]")
        self._final_answer = val
        return val

    @property
    def locals(self) -> dict:
        """Get current sandbox variables (excluding builtins and tools)."""
        skip = {"__builtins__", "llm_query", "FINAL", "FINAL_VAR", "context"}
        return {k: v for k, v in self._globals.items() if k not in skip and not k.startswith("_")}
