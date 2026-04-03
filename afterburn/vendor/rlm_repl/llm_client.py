"""LLM client using raw requests — no openai SDK dependency."""

import json
import os
from dataclasses import dataclass, field

import requests


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
            resp = requests.get(
                f"{self.api_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
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

        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=300,
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
