"""Generate research figures from real results (no decorative charts).

All figures render from evaluation/results/{metrics,ablation}.json and
evaluation/results/results.json. Every value plotted is a measured value
from the actual InsightFlow orchestrator run.

Usage:
    python evaluation/scripts/generate_figures.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE.parent
RES = EVAL_DIR / "results"
FIG = EVAL_DIR / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# Palette — restrained, matches the app's decision colours.
COL = {
    "ink":     "#0B1620",
    "muted":   "#5F7A83",
    "grid":    "#D5DDE0",
    "brand":   "#14B8A6",
    "brand2":  "#0E7C6B",
    "sky":     "#38BDF8",
    "amber":   "#F59E0B",
    "answer":  "#22C55E",
    "warn":    "#F59E0B",
    "clarify": "#38BDF8",
    "abstain": "#F43F5E",
}


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.edgecolor":    COL["muted"],
        "axes.labelcolor":   COL["ink"],
        "xtick.color":       COL["muted"],
        "ytick.color":       COL["muted"],
        "axes.grid": True,
        "grid.color": COL["grid"],
        "grid.linewidth": 0.6,
        "grid.alpha": 0.8,
        "figure.dpi": 130,
        "savefig.dpi": 160,
        "figure.facecolor": "white",
    })


def _save(name: str):
    plt.tight_layout()
    out = FIG / name
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out}")


def fig1_dataset_distribution(metrics, rows):
    per_ans = Counter(r["answerability"] for r in rows)
    per_dif = Counter(r["difficulty"] for r in rows)
    fig, ax = plt.subplots(1, 2, figsize=(8, 3))

    ans_keys = ["answerable", "ambiguous", "out_of_scope"]
    ax[0].bar(ans_keys, [per_ans.get(k, 0) for k in ans_keys],
              color=[COL["answer"], COL["clarify"], COL["abstain"]])
    ax[0].set_title("By answerability")
    ax[0].set_ylabel("questions")

    dif_keys = ["simple", "moderate", "challenging"]
    ax[1].bar(dif_keys, [per_dif.get(k, 0) for k in dif_keys],
              color=[COL["brand"], COL["sky"], COL["amber"]])
    ax[1].set_title("By difficulty (BIRD-style)")

    fig.suptitle("Fig. 1 — InsightFlow Reliability Benchmark (n=27)",
                 fontsize=11, color=COL["ink"])
    _save("fig1_dataset_distribution.png")


def fig2_sql_execution_accuracy(metrics):
    keys = ["sql_validity_rate", "schema_matching_accuracy",
            "execution_accuracy", "exact_match"]
    labels = ["SQL validity", "Schema match", "Execution accuracy (EX)", "Exact match"]
    vals = [metrics["text_to_sql"][k] or 0.0 for k in keys]
    fig, ax = plt.subplots(figsize=(6.4, 3))
    ax.barh(labels[::-1], vals[::-1],
            color=[COL["brand"], COL["sky"], COL["brand2"], COL["amber"]][::-1])
    ax.set_xlim(0, 1)
    ax.set_xlabel("rate")
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=9, color=COL["ink"])
    ax.set_title("Fig. 2 — SQL text-to-SQL metrics (n=17 with gold SQL)")
    _save("fig2_sql_execution_accuracy.png")


def fig3_business_correctness(metrics):
    keys = ["answer_correctness", "kpi_matching_accuracy",
            "evidence_support_rate", "result_consistency"]
    labels = ["Answer correctness", "KPI match", "Evidence support", "Result consistency"]
    vals = [metrics["business"][k] or 0.0 for k in keys]
    fig, ax = plt.subplots(figsize=(6.4, 3))
    ax.barh(labels[::-1], vals[::-1],
            color=[COL["answer"], COL["brand"], COL["sky"], COL["brand2"]][::-1])
    ax.set_xlim(0, 1)
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=9, color=COL["ink"])
    ax.set_xlabel("rate")
    ax.set_title("Fig. 3 — Business-level correctness")
    _save("fig3_business_correctness.png")


def fig4_confidence_vs_correct(rows):
    correct = [r["overall_confidence"] for r in rows
               if r["business_correct"] is True]
    wrong   = [r["overall_confidence"] for r in rows
               if r["business_correct"] is False]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    if correct:
        ax.scatter(correct, [1] * len(correct), s=48,
                   color=COL["answer"], alpha=0.7, label=f"correct (n={len(correct)})")
    if wrong:
        ax.scatter(wrong, [0] * len(wrong), s=90, marker="X",
                   color=COL["abstain"], alpha=0.9, label=f"incorrect (n={len(wrong)})")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["incorrect", "correct"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("confidence score")
    ax.axvline(0.70, color=COL["muted"], linestyle="--", linewidth=1, label="ANSWER threshold")
    ax.axvline(0.40, color=COL["muted"], linestyle=":",  linewidth=1, label="WARN threshold")
    ax.legend(loc="center right", fontsize=8, frameon=False)
    ax.set_title("Fig. 4 — Confidence vs correctness (per question)")
    _save("fig4_confidence_vs_correct.png")


def fig5_calibration_curve(metrics):
    bins = metrics["calibration"]["bins"]
    xs, ys, sizes = [], [], []
    for b in bins:
        if b["accuracy"] is None:
            continue
        xs.append(b["avg_confidence"])
        ys.append(b["accuracy"])
        sizes.append(60 + 25 * b["n"])
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color=COL["muted"], linestyle="--", label="perfect calibration")
    ax.scatter(xs, ys, s=sizes, color=COL["brand"], edgecolor=COL["brand2"],
               linewidth=1.2, alpha=0.9, zorder=3, label="observed")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("avg confidence in bin")
    ax.set_ylabel("empirical accuracy in bin")
    ece = metrics["calibration"]["ece"]
    brier = metrics["calibration"]["brier"]
    ax.set_title(f"Fig. 5 — Calibration  (ECE {ece:.3f}, Brier {brier:.3f})")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    _save("fig5_calibration_curve.png")


def fig6_decision_distribution(metrics):
    d = metrics["decision"]["distribution"]
    keys = ["ANSWER", "WARN", "CLARIFY", "ABSTAIN"]
    vals = [d.get(k, 0) for k in keys]
    colors = [COL["answer"], COL["warn"], COL["clarify"], COL["abstain"]]
    fig, ax = plt.subplots(figsize=(5.4, 3))
    ax.bar(keys, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.3, str(v), ha="center", fontsize=10, color=COL["ink"])
    ax.set_ylabel("questions")
    ax.set_title("Fig. 6 — Decision distribution (measured)")
    _save("fig6_decision_distribution.png")


def fig7_high_confidence_error(metrics):
    total_hc = metrics["reliability"]["n_high_confidence"] or 0
    err = metrics["reliability"]["high_confidence_error_rate"] or 0.0
    correct = max(0, total_hc - round(err * total_hc))
    wrong   = total_hc - correct
    fig, ax = plt.subplots(figsize=(4.2, 3))
    ax.bar(["correct", "incorrect"], [correct, wrong],
           color=[COL["answer"], COL["abstain"]])
    ax.set_ylabel("high-confidence answers")
    ax.set_title(f"Fig. 7 — High-confidence errors  (rate {err*100:.1f}%)")
    for i, v in enumerate([correct, wrong]):
        ax.text(i, v + 0.2, str(v), ha="center", fontsize=10, color=COL["ink"])
    _save("fig7_high_confidence_error.png")


def fig8_ablation_comparison(ablation):
    cfgs = list(ablation["results"].keys())
    def pull(path):
        vals = []
        for c in cfgs:
            v = ablation["results"][c]
            for step in path:
                v = v[step] if v is not None else None
            vals.append(0.0 if v is None else v)
        return vals

    metric_paths = [
        ("EX",                          ("text_to_sql", "execution_accuracy")),
        ("Business correctness",         ("business", "answer_correctness")),
        ("Decision correctness",         ("decision", "decision_correctness")),
        ("Unsafe answer rate",           ("decision", "unsafe_answer_rate")),
        ("ECE (lower better)",           ("calibration", "ece")),
        ("Brier (lower better)",         ("calibration", "brier")),
    ]
    import numpy as np
    x = np.arange(len(metric_paths))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    colors = [COL["muted"], COL["sky"], COL["brand"]]
    for i, cfg in enumerate(cfgs):
        vals = []
        for _, path in metric_paths:
            v = ablation["results"][cfg]
            for step in path:
                v = v[step] if v is not None else None
            vals.append(0.0 if v is None else v)
        offset = (i - 1) * width
        ax.bar(x + offset, vals, width, label=cfg, color=colors[i])
        for j, v in enumerate(vals):
            ax.text(x[j] + offset, v + 0.005, f"{v:.3f}",
                    ha="center", fontsize=7, color=COL["ink"])
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for lbl, _ in metric_paths], rotation=15)
    ax.set_ylabel("value")
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.set_title("Fig. 8 — Ablation: SQL-only vs SQL+KPI vs Full InsightFlow")
    _save("fig8_ablation_comparison.png")


def main() -> int:
    _style()
    metrics = json.load((RES / "metrics.json").open())
    rows = json.load((RES / "results.json").open())
    ablation = json.load((RES / "ablation.json").open())

    fig1_dataset_distribution(metrics, rows)
    fig2_sql_execution_accuracy(metrics)
    fig3_business_correctness(metrics)
    fig4_confidence_vs_correct(rows)
    fig5_calibration_curve(metrics)
    fig6_decision_distribution(metrics)
    fig7_high_confidence_error(metrics)
    fig8_ablation_comparison(ablation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
