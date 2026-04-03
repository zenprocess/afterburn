"""LLM client — supports OpenAI-compatible API or Claude CLI."""

import json
import os
import subprocess
from dataclasses import dataclass, field

import requests


def _detect_backend() -> str:
    """Detect the best available LLM backend.

    Priority: AFTERBURN_API_URL env → claude CLI → localhost vLLM
    """
    if os.environ.get("AFTERBURN_API_URL"):
        return "api"
    # Check if claude CLI is available
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return "claude"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "api"


@dataclass
class ClaudeCLIClient:
    """LLM client using `claude -p` (Claude Code CLI in pipe mode)."""

    model: str = "haiku"
    total_calls: int = 0

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> str:
        """Send prompt to Claude CLI via pipe mode."""
        # Flatten messages into a single prompt
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System instruction]: {content}")
            elif role == "assistant":
                parts.append(f"[Previous response]: {content}")
            else:
                parts.append(content)

        prompt = "\n\n".join(parts)

        cmd = ["claude", "-p", "--model", self.model]

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.total_calls += 1
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return f"[claude CLI error: {result.stderr[:200]}]"
        except subprocess.TimeoutExpired:
            return "[claude CLI timeout]"
        except FileNotFoundError:
            return "[claude CLI not found]"

    def cost_summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "backend": "claude-cli",
        }


@dataclass
class LLMClient:
    """OpenAI-compatible chat completion client using requests."""

    api_url: str = ""
    model: str = "auto"
    api_key: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0

    def __post_init__(self):
        if not self.api_url:
            self.api_url = os.environ.get(
                "AFTERBURN_API_URL",
                os.environ.get("RLM_API_URL", "http://localhost:8080/v1"),
            )
        if not self.api_key:
            self.api_key = os.environ.get(
                "ANTHROPIC_API_KEY",
                os.environ.get("OPENAI_API_KEY", "not-needed"),
            )
        if self.model == "auto":
            self.model = self._discover_model()

    def _discover_model(self) -> str:
        """Auto-discover model from /models endpoint."""
        try:
            verify_ssl = not os.environ.get("AFTERBURN_NO_SSL_VERIFY", "")
            resp = requests.get(
                f"{self.api_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
                verify=verify_ssl,
            )
            if resp.ok:
                data = resp.json()
                models = data.get("data", [])
                if models:
                    return models[0].get("id", "default")
        except (requests.RequestException, KeyError, IndexError):
            pass
        return "default"

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> str:
        """Send a chat completion request, return the response text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Disable SSL verification for self-signed certs (common with local vLLM)
        verify_ssl = not os.environ.get("AFTERBURN_NO_SSL_VERIFY", "")
        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=300,
            verify=verify_ssl,
        )
        resp.raise_for_status()
        data = resp.json()

        # Track tokens
        usage = data.get("usage", {})
        self.total_input_tokens += usage.get("prompt_tokens", 0)
        self.total_output_tokens += usage.get("completion_tokens", 0)
        self.total_calls += 1

        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    def cost_summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }
