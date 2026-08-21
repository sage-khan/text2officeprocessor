"""
Concrete LLM provider implementations.

Each provider reads its configuration from environment variables or a config dict.
API keys must NEVER be hardcoded here — use environment variables or secrets manager.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from src.core.exceptions import LLMUnavailableError
from src.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def _load_env_file() -> None:
    """
    Load key/value pairs from a local .env file into os.environ.

    Existing environment variables are never overwritten.
    """
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
        except Exception as exc:
            logger.debug("Could not load .env from %s: %s", env_path, exc)


_load_env_file()


class OllamaProvider(LLMProvider):
    """Local Ollama LLM provider (default for offline use)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "mistral",
        timeout_seconds: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = int(timeout_seconds)

    def generate(self, prompt: str) -> str:
        try:
            import requests  # type: ignore

            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as exc:
            raise LLMUnavailableError(f"Ollama unavailable: {exc}") from exc


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-3.5 / GPT-4 family)."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMUnavailableError("OPENAI_API_KEY environment variable not set.")
        try:
            import openai  # type: ignore

            client = openai.OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(f"OpenAI unavailable: {exc}") from exc


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = "claude-3-haiku-20240307", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMUnavailableError("ANTHROPIC_API_KEY environment variable not set.")
        try:
            import anthropic  # type: ignore

            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as exc:
            raise LLMUnavailableError(f"Claude unavailable: {exc}") from exc


class OpenRouterProvider(LLMProvider):
    """OpenRouter API provider (multi-model gateway)."""

    def __init__(self, model: str = "mistralai/mistral-7b-instruct", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = "https://openrouter.ai/api/v1"

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMUnavailableError("OPENROUTER_API_KEY environment variable not set.")
        try:
            import requests  # type: ignore

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMUnavailableError(f"OpenRouter unavailable: {exc}") from exc


class GroqProvider(LLMProvider):
    """Groq cloud LLM provider (fast inference)."""

    def __init__(self, model: str = "llama3-8b-8192", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("GROQ_API_KEY", "")

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise LLMUnavailableError("GROQ_API_KEY environment variable not set.")
        try:
            from groq import Groq  # type: ignore

            client = Groq(api_key=self._api_key)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
            )
            return chat_completion.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(f"Groq unavailable: {exc}") from exc


class VLLMProvider(LLMProvider):
    """Local/remote vLLM provider (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model: str = "mistralai/Mistral-7B-Instruct-v0.2",
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or os.environ.get("VLLM_API_KEY", "EMPTY")

    def generate(self, prompt: str) -> str:
        try:
            import requests  # type: ignore

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMUnavailableError(f"vLLM unavailable: {exc}") from exc


def build_provider(provider_name: str, config: dict[str, Any] | None = None) -> LLMProvider:
    """
    Factory function — build an LLM provider by name.

    Args:
        provider_name: One of 'ollama', 'vllm', 'openai', 'claude', 'openrouter', 'groq'.
        config: Optional dict with provider-specific settings (model, base_url, etc.).

    Returns:
        An LLMProvider instance.

    Raises:
        ValueError: If provider_name is unknown.
    """
    config = config or {}
    registry: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "vllm": VLLMProvider,
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "openrouter": OpenRouterProvider,
        "groq": GroqProvider,
    }
    if provider_name not in registry:
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. Choose from: {list(registry.keys())}"
        )
    provider_class = registry[provider_name]
    return provider_class(**{k: v for k, v in config.items() if k != "provider"})
