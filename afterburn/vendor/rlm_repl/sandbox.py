"""REPL sandbox — executes Python code with injected tools.

SECURITY: the code executed here is model-authored, and the model is
analyzing untrusted session-transcript content (see
afterburn.passes._rlm_friction_analysis). A transcript can contain an
adversarial payload (e.g. a fake ```repl block) that the analyzing LLM
faithfully reproduces, so this sandbox must not grant unrestricted access
to the interpreter. Two layers of defense are applied:

1. A minimal `__builtins__` allowlist — no `__import__`, `open`, `eval`,
   `exec`, `compile`, `input`, or introspection builtins (`globals`,
   `locals`, `vars`, `dir`, `getattr`, `setattr`, `delattr`) that could be
   used to reach `os`/`sys`.
2. A static AST check that rejects `import` statements, dunder attribute
   access (blocks the classic `().__class__.__bases__[0].__subclasses__()`
   escape idiom), and direct references to forbidden names.

This is defense-in-depth, not a formally complete sandbox — CPython has no
fully-safe `exec()` mode. Combined, the two layers block the well-known
escape idioms while preserving the benign analysis subset (arithmetic,
string/list/dict operations, comprehensions, etc).
"""

import ast
import builtins as _builtins_module
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout

# Builtins explicitly allowed inside the sandbox. Anything not listed here
# is unreachable via plain name lookup.
_SAFE_BUILTIN_NAMES = frozenset(
    {
        "abs", "all", "any", "bool", "bytearray", "bytes", "callable", "chr",
        "complex", "dict", "divmod", "enumerate", "filter", "float", "format",
        "frozenset", "hasattr", "hash", "hex", "int", "isinstance",
        "issubclass", "iter",
        "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
        "print", "range", "repr", "reversed", "round", "set", "slice",
        "sorted", "str", "sum", "tuple", "type", "zip",
        "True", "False", "None", "NotImplemented",
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "StopIteration", "StopAsyncIteration",
        "RuntimeError", "ZeroDivisionError", "ArithmeticError",
        "OverflowError", "NotImplementedError", "LookupError",
        "AssertionError", "GeneratorExit", "UnicodeError", "UnicodeDecodeError",
        "UnicodeEncodeError",
    }
)

# Names that must never be reachable, even indirectly, because they grant
# filesystem, process, or interpreter escape hatches. Removing them from
# __builtins__ (below) already makes plain lookups fail with NameError;
# the AST check additionally rejects source code that even *names* them,
# so the failure is an explicit SandboxViolation instead of a confusing
# NameError deep inside model-authored code.
_FORBIDDEN_NAMES = frozenset(
    {
        "__import__", "eval", "exec", "compile", "open", "input", "exit",
        "quit", "breakpoint", "globals", "locals", "vars", "dir", "getattr",
        "setattr", "delattr", "help", "copyright", "credits", "license",
        "memoryview", "__loader__", "__build_class__", "__debug__",
    }
)


class SandboxViolation(Exception):
    """Raised when sandboxed code attempts a forbidden operation."""


def _build_safe_builtins() -> dict:
    """Construct a minimal __builtins__ mapping with dangerous names removed."""
    return {
        name: getattr(_builtins_module, name)
        for name in _SAFE_BUILTIN_NAMES
        if hasattr(_builtins_module, name)
    }


def _check_ast_safety(code: str) -> None:
    """Static check: reject imports, dunder attribute access, forbidden names.

    Blocks the classic Python sandbox-escape idiom
    (`().__class__.__bases__[0].__subclasses__()` and friends) and explicit
    `import os` / `__import__('os')` statements before the code is ever
    compiled or executed.
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxViolation(f"code does not parse: {exc}") from None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxViolation(
                "import statements are not allowed in the sandbox"
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise SandboxViolation(
                f"dunder attribute access is not allowed: .{node.attr}"
            )
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxViolation(
                f"name is not allowed in the sandbox: {node.id}"
            )


class REPLSandbox:
    """Python REPL environment with injected context and tools.

    The sandbox provides:
    - `context`: the data to analyze (loaded externally)
    - `llm_query(prompt)`: make a recursive sub-LLM call
    - `FINAL(answer)`: signal completion with a string answer
    - `FINAL_VAR(name)`: signal completion, return a variable's value

    All state persists across exec() calls within the same sandbox.
    Execution is restricted per the module docstring (safe builtins + AST
    checks) — see SandboxViolation.
    """

    def __init__(self, llm_query_fn=None):
        self._final_answer = None
        self._final_var_name = None
        self._globals: dict = {
            "__builtins__": _build_safe_builtins(),
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
            _check_ast_safety(code)
        except SandboxViolation as exc:
            stderr_buf.write(f"SandboxViolation: {exc}\n")
            return stdout_buf.getvalue(), stderr_buf.getvalue(), False

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
        val = self._globals.get(
            variable_name, f"[variable '{variable_name}' not found]"
        )
        self._final_answer = val
        return val

    @property
    def locals(self) -> dict:
        """Get current sandbox variables (excluding builtins and tools)."""
        skip = {"__builtins__", "llm_query", "FINAL", "FINAL_VAR", "context"}
        return {
            k: v
            for k, v in self._globals.items()
            if k not in skip and not k.startswith("_")
        }
