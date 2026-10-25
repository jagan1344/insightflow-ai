"""Conversation-context resolver.

Minimal, documented follow-up handling. Keeps a per-session copy of
the LAST successfully-answered plan and rewrites follow-up questions
that reference it (e.g. "now by region", "and in July 2026",
"compare it to last month") into stand-alone questions the planner
can resolve from scratch.

The resolver's rewrite rules are intentionally narrow and listed
explicitly. Anything the rules do not match passes through untouched,
and the planner handles the question fresh. We never silently reuse
state when the reference is ambiguous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationContext:
    """One snapshot per conversation (session). Only the most recent
    successfully-answered question is kept.
    """
    last_question: Optional[str] = None
    last_kpi_phrase: Optional[str] = None
    last_dim_phrase: Optional[str] = None     # e.g. "by region"
    last_time_phrase: Optional[str] = None    # e.g. "in July 2026"
    last_dataset_id: Optional[str] = None     # cross-dataset safety
    extra: dict = field(default_factory=dict)


_FOLLOWUP_PREFIXES = (
    r"^\s*(?:and|also|now|then)\s+",
    r"^\s*(?:what\s+about|how\s+about)\s+",
    r"^\s*(?:same\s+(?:thing|question)\s+but)\s+",
)

# "by region", "by category", "by month", etc.
_DIM_REWRITE_RE = re.compile(
    r"^\s*(?:and|also|now|then|what\s+about|how\s+about)\s+"
    r"(?:just\s+|only\s+)?by\s+([a-z_]+(?:\s+[a-z_]+){0,2})\b",
    re.IGNORECASE)

# "in July 2026", "for Q2 2026", "in September", "for the East region"
_FILTER_REWRITE_RE = re.compile(
    r"^\s*(?:and|also|now|then|what\s+about|how\s+about)\s+"
    r"(?:just\s+|only\s+)?(?:in|for|during)\s+([a-z0-9][a-z0-9\s-]{1,40})\b",
    re.IGNORECASE)

# "compare it to <X>", "versus <X>"
_COMPARE_REWRITE_RE = re.compile(
    r"^\s*compare\s+(?:it|that|the\s+same)\s+to\s+(.+?)\s*\??$",
    re.IGNORECASE)


def _looks_like_followup(q: str) -> bool:
    return any(re.search(p, q, re.IGNORECASE) for p in _FOLLOWUP_PREFIXES)


def resolve_followup(question: str,
                       ctx: ConversationContext,
                       active_dataset_id: Optional[str] = None,
                       ) -> str:
    """Return a rewritten stand-alone question, or the original
    question when no rule applies / context is unsafe to reuse.

    Dataset-change safety: if the active dataset differs from the one
    the context was captured against, do NOT rewrite (that would
    carry filters from a different schema into a new dataset).
    """
    if ctx.last_question is None:
        return question
    if active_dataset_id is not None and ctx.last_dataset_id is not None \
            and active_dataset_id != ctx.last_dataset_id:
        return question
    if not _looks_like_followup(question) \
            and not _COMPARE_REWRITE_RE.search(question):
        return question

    # Rewrite 1: "now by X" / "and by X" → replace dim in last question
    m = _DIM_REWRITE_RE.match(question)
    if m:
        new_dim = m.group(1).strip()
        base = ctx.last_question
        # Strip the old " by <X>" if present.
        # Only a TRAILING grouping ("... by region" optionally followed by a
        # time phrase) is replaced. A mid-sentence "by" ("taught by Prof. X",
        # "paid by students") is part of the question, not a grouping.
        base_no_dim = re.sub(
            r"\s+by\s+[a-z_]+(?:\s+[a-z_]+){0,2}"
            r"(?=(?:\s+(?:in|for|during|within)\s+[^?]*)?\s*[?.]?\s*$)",
            "", base).strip(" ?.")
        return f"{base_no_dim} by {new_dim}"

    # Rewrite 2: "in July 2026" / "for Q2" → add/replace time filter
    m = _FILTER_REWRITE_RE.match(question)
    if m:
        new_filter = m.group(1).strip(" ?.")
        base = ctx.last_question
        # Strip trailing time phrase if present ("in July 2026", "for 2026").
        base_no_time = re.sub(
            r"\s+(?:in|for|during)\s+[a-z0-9][a-z0-9\s-]{1,40}\s*\??$",
            "", base, flags=re.IGNORECASE).strip(" ?.")
        # Preserve kpi/dim verbiage from the last question.
        return f"{base_no_time} in {new_filter}"

    # Rewrite 3: "compare it to X" → "Compare <last_question_shape> to X"
    m = _COMPARE_REWRITE_RE.search(question)
    if m:
        other = m.group(1).strip(" ?.")
        base = ctx.last_question
        return f"Compare {base.rstrip(' ?.')} to {other}"

    return question


def capture_context(question: str, ctx: ConversationContext,
                     dataset_id: Optional[str] = None) -> None:
    """Record this question (presumably just answered) as the new
    context anchor."""
    ctx.last_question = question
    ctx.last_dataset_id = dataset_id
