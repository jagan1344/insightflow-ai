"""InsightFlow AI — CLI end-to-end demo."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from insightflow.orchestrator import Orchestrator


DB_PATH = Path(__file__).resolve().parent / "data" / "insightflow.db"

QUESTIONS = [
    "What is the total revenue?",
    "Show revenue by region",
    "What is the revenue by month?",
    "Why did revenue decrease in July?",
    "What is the gross margin by category?",
    "Top products by revenue",
    "What is the average order value in August?",
    "What is the meaning of life?",
]


def _decision_badge(action: str) -> str:
    return {
        "ANSWER":  "[ANSWER]",
        "WARN":    "[WARN]  ",
        "CLARIFY": "[CLARIFY]",
        "ABSTAIN": "[ABSTAIN]",
    }.get(action, f"[{action}]")


def _bar(value: float, width: int = 20) -> str:
    filled = int(round(value * width))
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    if not DB_PATH.exists():
        print("Demo database not found. Seed it first with:")
        print("    python data/seed.py")
        return 2

    orch = Orchestrator()
    print("=" * 74)
    print(" InsightFlow AI — CLI demo")
    print(f" LLM provider: {orch.llm.provider}   available: {orch.llm.available}")
    print("=" * 74)

    for q in QUESTIONS:
        resp = orch.ask(q)
        print()
        print("─" * 74)
        print(f"Q: {q}")
        print(f"SQL   : {resp.sql or '(none)'}")
        print(f"Intent: {resp.intent}  |  KPI: {resp.evidence.kpi.name if resp.evidence.kpi else 'n/a'}")
        print(f"Decision: {_decision_badge(resp.decision.action)}  "
              f"confidence={resp.confidence.score:.2f}  reason: {resp.decision.reason}")
        print("Confidence signals:")
        for name, val in resp.confidence.signals.items():
            print(f"  {name:<22} {val:0.2f}  {_bar(val)}")

        if resp.decision.action in ("ANSWER", "WARN"):
            print(f"Answer: {resp.explanation}")
            if resp.recommendation:
                print(f"Recommend: {resp.recommendation}")
        else:
            print(f"Held back: {resp.explanation}")

    print()
    print("=" * 74)
    print(" Done.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
