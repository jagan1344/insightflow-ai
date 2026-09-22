"""Configuration for InsightFlow AI. All values env-overridable."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict

try:  # optional
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def _envf(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


DEFAULT_WEIGHTS: Dict[str, float] = {
    "sql_validity":        0.20,
    "schema_match":        0.15,
    "kpi_match":           0.20,
    "context_consistency": 0.15,
    "data_completeness":   0.12,
    "evidence_strength":   0.10,
    "result_consistency":  0.08,
}


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///data/insightflow.db"))
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "offline"))
    llm_model:    str = field(default_factory=lambda: _env("LLM_MODEL", "gpt-4o-mini"))
    llm_api_key:  str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))

    threshold_high: float = field(default_factory=lambda: _envf("CONF_HIGH", 0.70))
    threshold_low:  float = field(default_factory=lambda: _envf("CONF_LOW",  0.40))

    max_rows: int = field(default_factory=lambda: _envi("MAX_ROWS", 1000))

    confidence_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


settings = Settings()
