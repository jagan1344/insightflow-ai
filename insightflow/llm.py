"""LLM client with pluggable providers. Degrades to offline on any failure."""
from __future__ import annotations

from typing import Optional

from .config import settings


class LLMClient:
    """Thin wrapper over an LLM provider.

    Attributes:
        available: True iff a real model can be called.
    Methods:
        complete(prompt, system="", temperature=0) -> str
    """

    def __init__(self, provider: Optional[str] = None,
                 model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None):
        self.provider = (provider or settings.llm_provider or "offline").lower()
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self._client = None
        self.available = False
        self._init_client()

    # ------------------------------------------------------------------
    def _init_client(self) -> None:
        if self.provider == "offline":
            return
        if self.provider not in ("openai", "local"):
            self.provider = "offline"
            return
        try:
            from openai import OpenAI  # type: ignore
        except Exception:
            self.provider = "offline"
            return
        try:
            kwargs = {}
            if self.provider == "openai":
                if not self.api_key:
                    self.provider = "offline"
                    return
                kwargs["api_key"] = self.api_key
            else:  # local
                if not self.base_url:
                    self.provider = "offline"
                    return
                kwargs["base_url"] = self.base_url
                kwargs["api_key"] = self.api_key or "not-needed"
            self._client = OpenAI(**kwargs)
            self.available = True
        except Exception:
            self._client = None
            self.provider = "offline"
            self.available = False

    # ------------------------------------------------------------------
    def complete(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        if not self.available or self._client is None:
            return self._offline_stub(prompt, system)
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            # Any failure at call time → soft-fail to offline for this call.
            return self._offline_stub(prompt, system)

    # ------------------------------------------------------------------
    @staticmethod
    def _offline_stub(prompt: str, system: str = "") -> str:
        # Deterministic placeholder used when no LLM is configured.
        return "[offline] Narration unavailable; using deterministic explanation."
