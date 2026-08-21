import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.llm.providers import ClaudeProvider, OpenAIProvider, VLLMProvider, build_provider
from src.core.llm.runtime_config import resolve_provider_selection


def test_resolve_provider_selection_uses_default_ollama():
    provider, cfg = resolve_provider_selection(None, None)
    assert provider == "ollama"
    assert isinstance(cfg, dict)
    assert "model" in cfg


def test_resolve_provider_selection_supports_explicit_none():
    provider, cfg = resolve_provider_selection("none", None)
    assert provider is None
    assert cfg == {}


def test_resolve_provider_selection_overrides_model():
    provider, cfg = resolve_provider_selection("vllm", "meta-llama/Llama-2-7b-chat-hf")
    assert provider == "vllm"
    assert cfg["model"] == "meta-llama/Llama-2-7b-chat-hf"


def test_build_provider_supports_vllm():
    p = build_provider("vllm", {"base_url": "http://localhost:8000/v1", "model": "mistral"})
    assert isinstance(p, VLLMProvider)


def test_resolve_provider_selection_uses_override_instead_of_disk_config():
    override = {
        "default_provider": "claude",
        "providers": {"claude": {"model": "claude-3-5-sonnet-20241022", "api_key": "sk-ant-inline"}},
    }
    provider, cfg = resolve_provider_selection(None, None, override)
    assert provider == "claude"
    assert cfg == {"model": "claude-3-5-sonnet-20241022", "api_key": "sk-ant-inline"}


def test_resolve_provider_selection_none_override_falls_back_to_disk_config():
    provider, cfg = resolve_provider_selection(None, None, None)
    assert provider == "ollama"
    assert "model" in cfg


def test_resolve_provider_selection_explicit_provider_wins_over_override_default():
    override = {"default_provider": "claude", "providers": {"openai": {"model": "gpt-4o-mini"}}}
    provider, cfg = resolve_provider_selection("openai", None, override)
    assert provider == "openai"
    assert cfg["model"] == "gpt-4o-mini"


def test_openai_provider_uses_inline_api_key_over_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    p = OpenAIProvider(model="gpt-4o-mini", api_key="sk-inline")
    assert p._api_key == "sk-inline"


def test_openai_provider_falls_back_to_env_when_no_inline_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    p = OpenAIProvider(model="gpt-4o-mini")
    assert p._api_key == "sk-from-env"


def test_claude_provider_uses_inline_api_key_over_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    p = ClaudeProvider(model="claude-3-haiku-20240307", api_key="sk-ant-inline")
    assert p._api_key == "sk-ant-inline"


def test_build_provider_passes_inline_api_key_through():
    p = build_provider("openai", {"model": "gpt-4o-mini", "api_key": "sk-inline"})
    assert isinstance(p, OpenAIProvider)
    assert p._api_key == "sk-inline"
