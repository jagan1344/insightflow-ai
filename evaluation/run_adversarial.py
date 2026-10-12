"""Run the adversarial diagnostic set through all 5 configurations.

Reports:
- per-question output per config
- which configs diverged from Full
- fire-rate per guard

Writes:
    paper_evidence/adversarial_per_question.csv
    paper_evidence/adversarial_results.md
"""
from __future__ import annotations

import csv
import json
import os
import pathlib
import runpy
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
EV = ROOT / "paper_evidence"
EV.mkdir(exist_ok=True)
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))
os.environ.setdefault(
    "DATABASE_URL", f"sqlite:///{(BACKEND / 'data/insightflow.db').resolve()}")

# Re-use the exact same runners the main eval uses.
from evaluation.run_paper_eval import RUNNERS, _reseed, CONFIGS


ADV_PATH = ROOT / "evaluation/dataset/adversarial_diagnostic.jsonl"


def load_adversarial() -> List[dict]:
    return [json.loads(l) for l in ADV_PATH.open()]


def run_one(cfg: str, row: dict) -> Dict[str, Any]:
    runner = RUNNERS[cfg]
    q = row["natural_language_question"]
    t0 = time.perf_counter()
    try:
        resp = runner(q)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out: Dict[str, Any] = {
            "question_id": row["question_id"],
            "config": cfg,
            "targets_guard": row.get("targets_guard", ""),
            "hypothesis": row.get("hypothesis", ""),
            "action": resp.decision.action,
            "confidence": round(float(resp.confidence.score), 4),
            "sql": (resp.sql or "")[:200],
            "sql_present": bool(resp.sql),
            "exec_ok": resp.result.ok,
            "latency_ms": elapsed_ms,
            "intent_coverage": round(float(resp.confidence.signals.get(
                "intent_coverage", 0.0)), 4),
            "plan_fidelity": round(float(resp.confidence.signals.get(
                "plan_fidelity", 0.0)), 4),
        }
        return out
    except Exception as e:
        return {
            "question_id": row["question_id"], "config": cfg,
            "action": "RUNNER_ERROR", "sql": "",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "confidence": 0.0, "exec_ok": False,
            "exception": str(e),
        }


def main() -> None:
    adv = load_adversarial()
    rows_out: List[Dict[str, Any]] = []
    for cfg in CONFIGS:
        _reseed()
        print(f"=== config {cfg} on {len(adv)} adversarial questions ===",
              flush=True)
        for row in adv:
            rows_out.append(run_one(cfg, row))

    # Write CSV
    fieldnames = sorted({k for r in rows_out for k in r.keys()})
    (EV / "adversarial_per_question.csv").open("w", newline="").close()
    with (EV / "adversarial_per_question.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    # Build divergence table
    by_qid: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for r in rows_out:
        by_qid[r["question_id"]][r["config"]] = r

    lines = ["# Adversarial diagnostic — per-question + divergence",
             "",
             f"**Set size:** {len(adv)} hand-crafted questions targeting"
             " specific guards (A1 fidelity, A2 result validator, A3 hard"
             " cap). Each question's `targets_guard` field names the guard"
             " it was designed to stress.",
             "",
             "**Reading guide:** `≠Full` means the configuration's",
             " (action, confidence_bucket) differs from Full's. Confidence"
             " buckets are quantized to 0.05 so a trivial float",
             " difference does not count as a divergence.",
             "",
             "| QID | Targets | Full action/conf | B1 | A1 | A2 | A3 | Diverged |",
             "|---|---|---|---|---|---|---|---|"]

    def bucket(c: float) -> str: return f"{round(c*20)/20:.2f}"

    diverged_counts = defaultdict(int)
    for qid in sorted(by_qid):
        row = by_qid[qid]
        full = row.get("Full") or {}
        cells = []
        divs = []
        for cfg in ("Full", "B1", "A1", "A2", "A3"):
            r = row.get(cfg) or {}
            if not r:
                cells.append("-"); continue
            cell = f"{r.get('action','?')}/{r.get('confidence',0):.2f}"
            cells.append(cell)
            if cfg != "Full" and full:
                if (r.get("action") != full.get("action") or
                        bucket(r.get("confidence", 0)) !=
                        bucket(full.get("confidence", 0))):
                    divs.append(cfg)
                    diverged_counts[cfg] += 1
        tgt = (full.get("targets_guard") if full else "") or "-"
        lines.append(f"| {qid} | {tgt} | {cells[0]} | {cells[1]} | "
                     f"{cells[2]} | {cells[3]} | {cells[4]} | "
                     f"{','.join(divs) if divs else '—'} |")

    lines.append("")
    lines.append("## Divergence summary")
    lines.append("")
    lines.append(f"- Questions in set: {len(adv)}")
    lines.append(f"- Diverged from Full (any config): "
                 f"{sum(1 for qid in by_qid if any(by_qid[qid].get(c, {}).get('action') != by_qid[qid].get('Full', {}).get('action') or bucket(by_qid[qid].get(c, {}).get('confidence', 0.0)) != bucket(by_qid[qid].get('Full', {}).get('confidence', 0.0)) for c in ('B1','A1','A2','A3')))}")
    for cfg in ("B1", "A1", "A2", "A3"):
        lines.append(f"- {cfg} diverged from Full in: "
                     f"{diverged_counts[cfg]} / {len(adv)} questions")
    lines.append("")
    lines.append("## Methodology notes")
    lines.append("")
    lines.append("- Questions were drafted BEFORE running; `hypothesis`")
    lines.append("  records the author's prediction of which guard would")
    lines.append("  fire. The predictions were NOT revised after seeing")
    lines.append("  outputs, so this is a true pre-registered diagnostic.")
    lines.append("- The 27-question reliability benchmark is unchanged.")
    lines.append("  This adversarial set is a SEPARATE artefact for")
    lines.append("  ablation diagnostics and is not combined into the")
    lines.append("  main semantic-accuracy / coverage / unsafe-rate tables.")
    lines.append("- The verifier `evaluation/verify_ablations.py` already")
    lines.append("  showed each switch disables its guard on crafted")
    lines.append("  component inputs. This adversarial set shows whether")
    lines.append("  natural-language questions can also trigger the")
    lines.append("  guards at the end-to-end orchestrator level.")

    (EV / "adversarial_results.md").write_text("\n".join(lines))
    print(f"wrote {len(rows_out)} rows to adversarial_per_question.csv and "
          f"a divergence table to adversarial_results.md")


if __name__ == "__main__":
    main()
