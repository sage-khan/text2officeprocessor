import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.llm.providers import VLLMProvider, build_provider
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
