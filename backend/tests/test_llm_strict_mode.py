import pytest

from insightflow.llm import LLMClient


def test_strict_mode_rejects_offline_provider(monkeypatch):
    monkeypatch.setenv("LLM_STRICT_MODE", "true")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER=offline"):
        LLMClient(provider="offline")


def test_strict_mode_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_STRICT_MODE", "true")
    with pytest.raises(RuntimeError, match="Unsupported LLM_PROVIDER"):
        LLMClient(provider="made-up-provider")


def test_normal_offline_mode_remains_available_for_development(monkeypatch):
    monkeypatch.setenv("LLM_STRICT_MODE", "false")
    client = LLMClient(provider="offline")
    assert client.available is False
    assert client.complete("hello").startswith("[offline]")
