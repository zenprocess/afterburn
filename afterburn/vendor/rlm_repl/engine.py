"""RLM_REPL engine — the core recursive LLM loop.

Reimplemented from arXiv:2512.24601 concepts. No vendored dependencies.
"""

import re
import sys
from dataclasses import dataclass, field

from afterburn.vendor.rlm_repl.llm_client import ClaudeCLIClient, LLMClient, _detect_backend
from afterburn.vendor.rlm_repl.sandbox import REPLSandbox


SYSTEM_PROMPT = """You are an expert data analyst with access to a Python REPL.

You have a variable called `context` loaded in the REPL. You CANNOT see it directly — it is NOT in your prompt. You must use the REPL to inspect and analyze it.

Available tools in the REPL:
- `context` — the data to analyze (already loaded)
- `llm_query(prompt)` — make a recursive LLM call on a substring/chunk. Use this to analyze portions of the data that are too large to process at once.
- `FINAL(answer)` — call this when you have your final answer (string)
- `FINAL_VAR(variable_name)` — call this to return the value of a variable as the answer

Strategy:
1. First, inspect `context` to understand its type, size, and structure
2. Design a chunking strategy if the data is large
3. Use `llm_query()` on chunks to extract focused information
4. Aggregate sub-results
5. Call FINAL() or FINAL_VAR() with your answer

Write Python code in ```repl blocks. Example:
```repl
print(type(context), len(context))
```

IMPORTANT:
- Do NOT try to print the entire context — it may be millions of characters
- Use len(), type(), slicing, and filtering to understand structure first
- Batch llm_query() calls efficiently — don't call it on every single item
- When done, you MUST call FINAL() or FINAL_VAR()
"""


def _extract_code_blocks(text: str) -> list[str]:
    """Extract ```repl code blocks from LLM response."""
    pattern = r"```(?:repl|python)\s*\n(.*?)```"
    blocks = re.findall(pattern, text, re.DOTALL)
    return blocks


@dataclass
class RLM_REPL:
    """Recursive Language Model with REPL sandbox.

    Args:
        root_model: Model for orchestration (or "auto" for vLLM auto-discover)
        recursive_model: Model for sub-calls (or "auto")
        root_api_url: API URL for root model
        recursive_api_url: API URL for recursive model (defaults to root)
        max_iterations: Maximum REPL interaction loops
        max_output_length: Max chars in accumulated output
        verbose: Print progress to stderr
    """

    root_model: str = "auto"
    recursive_model: str = "auto"
    root_api_url: str = ""
    recursive_api_url: str = ""
    max_iterations: int = 50
    max_output_length: int = 500_000
    verbose: bool = True

    _root_client: LLMClient = field(init=False, default=None)
    _recursive_client: LLMClient = field(init=False, default=None)

    def __post_init__(self):
        backend = _detect_backend()

        if backend == "claude":
            # Use Claude CLI — model names map to claude models
            root_model = self.root_model if self.root_model != "auto" else "haiku"
            rec_model = self.recursive_model if self.recursive_model != "auto" else "haiku"
            self._root_client = ClaudeCLIClient(model=root_model)
            self._recursive_client = ClaudeCLIClient(model=rec_model)
            if self.verbose:
                import sys
                print(f"  [RLM] Using Claude CLI (root={root_model}, recursive={rec_model})", file=sys.stderr)
        else:
            # Use OpenAI-compatible API
            self._root_client = LLMClient(
                api_url=self.root_api_url,
                model=self.root_model,
            )
            rec_url = self.recursive_api_url or self.root_api_url
            self._recursive_client = LLMClient(
                api_url=rec_url,
                model=self.recursive_model,
            )

    def completion(self, context, query: str, system_prompt: str = "") -> str:
        """Run RLM REPL analysis on context with the given query.

        Args:
            context: Any Python object to analyze (list, dict, str, etc.)
            query: The question to answer about the context
            system_prompt: Override the default system prompt

        Returns:
            The final answer string
        """
        sys_prompt = system_prompt or SYSTEM_PROMPT

        # Create sandbox with recursive LLM wired in
        def llm_query(prompt: str) -> str:
            messages = [
                {"role": "system", "content": "You are a helpful analyst. Answer concisely."},
                {"role": "user", "content": prompt},
            ]
            return self._recursive_client.chat(messages, max_tokens=4096)

        sandbox = REPLSandbox(llm_query_fn=llm_query)
        context_desc = sandbox.load_context(context)

        # Build initial messages
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": (
                f"Analyze the data in `context` to answer this question:\n\n{query}\n\n"
                f"Context info: {context_desc}\n\n"
                "Start by inspecting the context structure."
            )},
        ]

        for iteration in range(self.max_iterations):
            if self.verbose:
                print(f"  [RLM] iteration {iteration + 1}/{self.max_iterations}", file=sys.stderr)

            # Get LLM response
            response = self._root_client.chat(messages, max_tokens=8192)

            # Extract code blocks
            code_blocks = _extract_code_blocks(response)

            if not code_blocks:
                # Check if response contains FINAL() directly in text
                final_match = re.search(r'FINAL\(["\'](.+?)["\']\)', response, re.DOTALL)
                if final_match:
                    return final_match.group(1)

                # No code and no FINAL — ask LLM to continue
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": (
                    "Please write Python code in a ```repl block to continue analysis. "
                    "When done, call FINAL(answer) with your answer."
                )})
                continue

            # Execute each code block
            all_stdout = []
            all_stderr = []
            has_final = False

            for code in code_blocks:
                stdout, stderr, is_final = sandbox.execute(code)
                if stdout:
                    all_stdout.append(stdout)
                if stderr:
                    all_stderr.append(stderr)
                if is_final:
                    has_final = True
                    break

            # Check for final answer
            if has_final:
                answer = sandbox.get_final_answer()
                if answer:
                    return str(answer)

            # Build execution result message
            result_parts = []
            if all_stdout:
                combined_stdout = "\n".join(all_stdout)
                if len(combined_stdout) > self.max_output_length:
                    combined_stdout = combined_stdout[:self.max_output_length] + "\n[TRUNCATED]"
                result_parts.append(f"stdout:\n{combined_stdout}")
            if all_stderr:
                combined_stderr = "\n".join(all_stderr)
                if len(combined_stderr) > 10000:
                    combined_stderr = combined_stderr[:10000] + "\n[TRUNCATED]"
                result_parts.append(f"stderr:\n{combined_stderr}")

            if not result_parts:
                result_parts.append("(no output)")

            # Feed results back to LLM
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": "\n".join(result_parts)})

            # Trim message history if it's getting too long
            if len(messages) > 30:
                # Keep system + first user + last 20 messages
                messages = messages[:2] + messages[-20:]

        return "[RLM_REPL] Max iterations reached without FINAL() call"

    def cost_summary(self) -> dict:
        """Return token usage summary for both models."""
        return {
            "root": self._root_client.cost_summary(),
            "recursive": self._recursive_client.cost_summary(),
        }
