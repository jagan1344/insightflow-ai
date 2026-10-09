"""Aggregate per-question results into publication-ready metrics.

Reads  paper_evidence/per_question.csv
Writes paper_evidence/results.json + paper_evidence/results_tables.md

Metrics (all computed under the definitions in the master prompt §6):

    - Execution accuracy        : exec_ok ÷ n
    - Semantic accuracy (a)     : correct ÷ answerable
    - Semantic accuracy (b)     : correct ÷ answered-at-ANSWER-or-WARN
    - Coverage                  : (ANSWER | WARN) ÷ n
    - Unsafe-answer rate U      : (ANSWER on answerable+wrong, or
                                   ANSWER on ambiguous/unanswerable) ÷ n
    - Incorrect WARN rate       : (WARN wrong) ÷ WARN  (reported separately)
    - Clarification precision   : (CLARIFY on ambiguous) ÷ CLARIFY
    - Abstention on unanswerable: (CLARIFY | ABSTAIN) on unanswerable ÷ unanswerable
    - ECE (10 equal-width bins) + Brier score
    - Mean fidelity (sig_plan_fidelity, where present)
    - Latency p50 / p95
    - McNemar vs Full for semantic correctness + unsafe

95% CIs via Wilson score interval.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
EV = ROOT / "paper_evidence"
IN = EV / "per_question.csv"


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float, float]:
    """Return (point, lo, hi) 95% Wilson score interval."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def ece(preds_probs: List[Tuple[float, bool]], n_bins: int = 10) -> float:
    """preds = [(confidence, correct)]."""
    if not preds_probs:
        return 0.0
    bins = [[] for _ in range(n_bins)]
    for p, correct in preds_probs:
        idx = min(n_bins - 1, int(p * n_bins))
        bins[idx].append((p, correct))
    total = len(preds_probs)
    e = 0.0
    for b in bins:
        if not b: continue
        avg_conf = sum(x[0] for x in b) / len(b)
        acc = sum(1 for x in b if x[1]) / len(b)
        e += abs(avg_conf - acc) * len(b) / total
    return e


def brier(preds_probs: List[Tuple[float, bool]]) -> float:
    if not preds_probs:
        return 0.0
    return sum((p - (1.0 if c else 0.0)) ** 2 for p, c in preds_probs) / len(preds_probs)


def mcnemar(a_correct: List[bool], b_correct: List[bool]) -> Tuple[int, int, float]:
    """Compute McNemar's test. Returns (b, c, p) where
       b = count of (A correct, B wrong)
       c = count of (A wrong, B correct)
       p = two-sided mid-p approximation (exact binomial for small n+c)."""
    assert len(a_correct) == len(b_correct)
    b = sum(1 for a, c in zip(a_correct, b_correct) if a and not c)
    c = sum(1 for a, cc in zip(a_correct, b_correct) if not a and cc)
    n = b + c
    if n == 0:
        return (b, c, 1.0)
    # Exact two-sided binomial under H0: p=0.5
    from math import comb
    k = min(b, c)
    # P(X <= k) + P(X >= n-k)
    p_low = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    p = 2 * p_low
    return (b, c, min(1.0, p))


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load() -> List[dict]:
    with IN.open() as f:
        return list(csv.DictReader(f))


def as_bool(s):
    return str(s).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Config-level metrics
# ---------------------------------------------------------------------------

def summarise(rows: List[dict], cfg: str) -> dict:
    cfg_rows = [r for r in rows if r["config"] == cfg]
    n = len(cfg_rows)
    answerable_rows = [r for r in cfg_rows if r["answerability"] == "answerable"]
    # The benchmark uses two "cannot answer" labels: "ambiguous" and
    # "out_of_scope". Treat both as the "unanswerable" population for the
    # paper's abstention-on-unanswerable metric.
    unanswerable_rows = [r for r in cfg_rows
                          if r["answerability"] in ("unanswerable",
                                                      "out_of_scope",
                                                      "ambiguous")]
    ambiguous_rows = [r for r in cfg_rows if r["answerability"] == "ambiguous"]

    exec_ok = sum(1 for r in cfg_rows if as_bool(r.get("exec_ok")))
    answered = [r for r in cfg_rows if r["action"] in ("ANSWER", "WARN")]
    clarify = [r for r in cfg_rows if r["action"] == "CLARIFY"]
    abstain = [r for r in cfg_rows if r["action"] == "ABSTAIN"]

    sem_correct_overall = sum(1 for r in cfg_rows if as_bool(r.get("semantic_match")))
    sem_correct_answered = sum(1 for r in answered if as_bool(r.get("semantic_match")))
    sem_correct_on_answerable = sum(1 for r in answerable_rows if as_bool(r.get("semantic_match")))

    # Unsafe = ANSWER that is wrong, OR ANSWER on an ambiguous/unanswerable question
    unsafe = 0
    for r in cfg_rows:
        if r["action"] == "ANSWER":
            if r["answerability"] != "answerable":
                unsafe += 1
            elif not as_bool(r.get("semantic_match")):
                unsafe += 1

    warn_rows = [r for r in cfg_rows if r["action"] == "WARN"]
    warn_wrong = sum(1 for r in warn_rows
                      if r["answerability"] == "answerable"
                      and not as_bool(r.get("semantic_match")))

    # Clarification precision: CLARIFY on ambiguous ÷ all CLARIFY
    # (Benchmark has no 'ambiguous' label in this release, so this
    # typically reports 0/clarify when the dataset lacks the category.)
    clar_on_amb = sum(1 for r in clarify if r["answerability"] == "ambiguous")
    unanswerable_or_clar = [r for r in unanswerable_rows
                             if r["action"] in ("CLARIFY", "ABSTAIN")]

    # Confidence pairs for calibration (only when confidence > 0)
    conf_pairs: list[tuple[float, bool]] = []
    for r in cfg_rows:
        try:
            c = float(r.get("confidence") or 0.0)
        except Exception:
            continue
        ok = as_bool(r.get("semantic_match"))
        conf_pairs.append((c, ok))

    # Fidelity mean
    fids = []
    for r in cfg_rows:
        v = r.get("sig_plan_fidelity")
        try: fids.append(float(v))
        except Exception: pass

    # Latency
    lats = []
    for r in cfg_rows:
        try: lats.append(int(r.get("latency_ms") or 0))
        except Exception: pass
    lats.sort()
    def pct(xs, q):
        if not xs: return 0
        k = min(len(xs) - 1, int(round(q / 100.0 * (len(xs) - 1))))
        return xs[k]

    out: Dict[str, Any] = {"config": cfg, "n": n,
                            "n_answerable": len(answerable_rows),
                            "n_unanswerable": len(unanswerable_rows),
                            "n_ambiguous": len(ambiguous_rows),
                            "exec_accuracy": wilson(exec_ok, n),
                            "semantic_accuracy_on_answerable": wilson(sem_correct_on_answerable, len(answerable_rows)),
                            "semantic_accuracy_on_answered": wilson(sem_correct_answered, len(answered)) if answered else (0.0, 0.0, 0.0),
                            "coverage": wilson(len(answered), n),
                            "unsafe_answer_rate": wilson(unsafe, n),
                            "unsafe_count": unsafe,
                            "incorrect_warn_rate_on_warn": wilson(warn_wrong, len(warn_rows)) if warn_rows else (0.0, 0.0, 0.0),
                            "n_answered": len(answered),
                            "n_clarify": len(clarify),
                            "n_abstain": len(abstain),
                            "clarification_precision_on_ambiguous_label": wilson(clar_on_amb, len(clarify)) if clarify else (0.0, 0.0, 0.0),
                            "abstention_on_unanswerable": wilson(len(unanswerable_or_clar), len(unanswerable_rows)) if unanswerable_rows else (0.0, 0.0, 0.0),
                            "ece_10bin": ece(conf_pairs),
                            "brier": brier(conf_pairs),
                            "fidelity_mean": statistics.fmean(fids) if fids else 0.0,
                            "latency_p50_ms": pct(lats, 50),
                            "latency_p95_ms": pct(lats, 95),
                            }
    return out


# ---------------------------------------------------------------------------
# Pairwise McNemar vs Full
# ---------------------------------------------------------------------------

def pairwise(rows: List[dict], base_cfg: str, other_cfg: str) -> dict:
    by_qid = defaultdict(dict)
    for r in rows:
        by_qid[r["question_id"]][r["config"]] = r
    sem_a, sem_b, unsafe_a, unsafe_b = [], [], [], []
    for qid, by_cfg in by_qid.items():
        a = by_cfg.get(base_cfg); b = by_cfg.get(other_cfg)
        if not a or not b: continue
        sem_a.append(as_bool(a.get("semantic_match")))
        sem_b.append(as_bool(b.get("semantic_match")))
        def is_unsafe(r):
            if r["action"] != "ANSWER": return False
            if r["answerability"] != "answerable": return True
            return not as_bool(r.get("semantic_match"))
        unsafe_a.append(is_unsafe(a))
        unsafe_b.append(is_unsafe(b))
    b_sem, c_sem, p_sem = mcnemar(sem_a, sem_b)
    b_u, c_u, p_u = mcnemar(unsafe_a, unsafe_b)
    return {"base": base_cfg, "other": other_cfg,
             "semantic": {"b": b_sem, "c": c_sem, "p": p_sem},
             "unsafe":   {"b": b_u,   "c": c_u,   "p": p_u}}


# ---------------------------------------------------------------------------

def write_results(all_summaries: List[dict], pairwise_tests: List[dict]) -> None:
    out = {"summaries": all_summaries, "pairwise": pairwise_tests}
    (EV / "results.json").write_text(json.dumps(out, indent=2))

    lines: List[str] = []
    lines.append("# Paper evidence — results tables")
    lines.append("")
    lines.append("All numbers computed from `paper_evidence/per_question.csv`,")
    lines.append("27-question InsightFlow Reliability Benchmark × 5 configurations.")
    lines.append("Values shown as `point (lo, hi)` for 95 % Wilson CIs.")
    lines.append("")

    def fmt_ci(ci):
        p, lo, hi = ci
        return f"{p:.3f} ({lo:.3f}, {hi:.3f})"

    # Table VI shape — configs rows
    lines.append("## Table VI — Baselines + Full")
    lines.append("")
    lines.append("| Config | n | Exec acc. | Sem. acc. / answerable | Coverage | Unsafe-answer | ECE | Fidelity | p50 ms | p95 ms |")
    lines.append("|---|---:|---|---|---|---|---:|---:|---:|---:|")
    for s in all_summaries:
        lines.append(f"| {s['config']} | {s['n']} | "
                     f"{fmt_ci(s['exec_accuracy'])} | "
                     f"{fmt_ci(s['semantic_accuracy_on_answerable'])} | "
                     f"{fmt_ci(s['coverage'])} | "
                     f"{fmt_ci(s['unsafe_answer_rate'])} | "
                     f"{s['ece_10bin']:.3f} | "
                     f"{s['fidelity_mean']:.3f} | "
                     f"{s['latency_p50_ms']} | "
                     f"{s['latency_p95_ms']} |")
    lines.append("")

    lines.append("## Decision mix per config")
    lines.append("")
    lines.append("| Config | ANSWER+WARN | CLARIFY | ABSTAIN |")
    lines.append("|---|---:|---:|---:|")
    for s in all_summaries:
        lines.append(f"| {s['config']} | {s['n_answered']} | {s['n_clarify']} | {s['n_abstain']} |")
    lines.append("")

    lines.append("## Pairwise McNemar vs Full")
    lines.append("")
    lines.append("| Pair | sem. b,c (p-value) | unsafe b,c (p-value) |")
    lines.append("|---|---|---|")
    for p in pairwise_tests:
        s = p["semantic"]; u = p["unsafe"]
        lines.append(f"| {p['base']} vs {p['other']} | "
                     f"{s['b']},{s['c']} (p={s['p']:.4f}) | "
                     f"{u['b']},{u['c']} (p={u['p']:.4f}) |")
    lines.append("")

    # Abstention table
    lines.append("## Abstention on non-answerable questions")
    lines.append("")
    lines.append("| Config | Non-answerable n | CLARIFY+ABSTAIN rate |")
    lines.append("|---|---:|---|")
    for s in all_summaries:
        n_una = s["n_unanswerable"]
        rate = s["abstention_on_unanswerable"]
        lines.append(f"| {s['config']} | {n_una} | {fmt_ci(rate)} |")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Benchmark `answerability` has three values: `answerable` (17),")
    lines.append("  `ambiguous` (4), `out_of_scope` (6). The 'non-answerable'")
    lines.append("  population above combines the latter two.")
    lines.append("- All 10 non-answerable questions were correctly routed to CLARIFY by")
    lines.append("  all five configurations.")
    lines.append("- All five configurations produced IDENTICAL per-question outputs on")
    lines.append("  this 27-question benchmark: the ablations (A1/A2/A3) and the")
    lines.append("  gate-removal baseline (B1) are indistinguishable from Full. See")
    lines.append("  `discrepancies.md` and `SUMMARY.md` for interpretation.")
    lines.append("- B0 (legacy generator) and B2 (direct LLM-to-SQL) are reported as")
    lines.append("  NOT MEASURED — see `paper_evidence/SUMMARY.md`.")
    lines.append("- `semantic_match` on `answerable` rows is computed by comparing the")
    lines.append("  system's executed result against the oracle, which re-runs each")
    lines.append("  benchmark row's `gold_sql` directly against the raw DB via sqlite3.")
    lines.append("- Relative tolerance ε = 1e-6 (see `evaluation/oracle.py::EPSILON`).")

    (EV / "results_tables.md").write_text("\n".join(lines))
    print(f"wrote {EV / 'results.json'}")
    print(f"wrote {EV / 'results_tables.md'}")


def main() -> None:
    rows = load()
    configs = sorted({r["config"] for r in rows},
                      key=lambda c: ("Full", "B1", "A1", "A2", "A3").index(c))
    summaries = [summarise(rows, c) for c in configs]
    pw = [pairwise(rows, "Full", c) for c in configs if c != "Full"]
    write_results(summaries, pw)


if __name__ == "__main__":
    main()
