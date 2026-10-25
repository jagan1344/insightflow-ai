"""Figures 4-7 from saved results only (no hand-entered numbers except the protocol diagram text,
whose counts are read from the result files)."""
import csv, json, pathlib, collections, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

H = pathlib.Path(__file__).resolve().parent
E = H.parent / "eval"
sys.path.insert(0, str(E))
from score_v5 import outcome
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none"})


def save(fig, name):
    for ext in ("pdf", "svg"):
        fig.savefig(H / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


rows = list(csv.DictReader(open(H.parent / "03_ablation_results.csv")))
A0 = json.load(open(E / "results/v5_A0_first_run.json"))["records"]
for r in A0:
    r["outcome"] = outcome(r)
n = len(A0); n_ans = sum(r["kind"] != "clarify" for r in A0); n_cl = n - n_ans

# Fig 4: protocol / provenance
fig, ax = plt.subplots(figsize=(3.5, 3.6)); ax.set_xlim(0, 6); ax.set_ylim(0.3, 8.2); ax.axis("off")
steps = ["Implementation frozen: commit 38b60d1\n(backend tree 00db6e2), 526 tests pass",
         f"Separate agent authors 4 schemas, {n} questions\n({n_ans} answerable, {n_cl} clarify/unsupported),\n"
         "reference SQL + independent alt SQL; no code access",
         "Validation (ref = alt SQL), scoring rules and\nborderline list fixed; SHA-256 manifest committed",
         "First run A0 once; raw output committed\nbefore scoring",
         "Ablations A1-A7, leave-one-in B1-B6:\nsame tree, data, scorer",
         "Limitation: agent-generated, same model family,\nnot human-adjudicated"]
for i, t in enumerate(steps):
    y = 7.0 - i * 1.3
    ax.add_patch(FancyBboxPatch((0.2, y), 5.6, 1.0, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc="#f6dcdc" if i == 5 else "#eef3f8", ec="#333333", lw=0.6))
    ax.text(3.0, y + 0.5, t, ha="center", va="center", fontsize=6)
    if i:
        ax.annotate("", xy=(3.0, y + 1.0), xytext=(3.0, y + 1.3), arrowprops=dict(arrowstyle="-|>", lw=0.6))
save(fig, "fig4_evaluation_protocol")

# Fig 5: ablation bars (correct / wrong / unnecessary clarify), A0..A7 and B1, B5
keep = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "B1", "B5"]
lab = {"A0": "Full", "A1": "-semantic", "A2": "-conf. gate", "A3": "-result chk", "A4": "-fidelity",
       "A5": "-coverage\n+audit", "A6": "-verifier", "A7": "all off", "B1": "only\nsemantic", "B5": "only\ncoverage"}
R = {r["config"]: r for r in rows}
fig, ax = plt.subplots(figsize=(7.16, 2.2))
x = range(len(keep)); w = 0.27
for j, (key, name, col) in enumerate([("correct", f"correct (of {n_ans} answerable)", "#4c78a8"),
                                       ("wrong_answers", f"wrong answers (of {n})", "#e45756"),
                                       ("unnecessary_clarify", f"unnecessary clarifications (of {n_ans})", "#bab0ac")]):
    vals = [int(R[k][key]) for k in keep]
    b = ax.bar([i + (j - 1) * w for i in x], vals, w, label=name, color=col)
    for xi, v in zip(x, vals):
        ax.text(xi + (j - 1) * w, v + 0.8, str(v), ha="center", fontsize=5.5)
ax.set_xticks(list(x)); ax.set_xticklabels([lab[k] for k in keep], fontsize=6)
ax.set_ylabel("questions"); ax.legend(fontsize=6, frameon=False, ncol=3, loc="upper left")
ax.set_ylim(0, 70); ax.spines[["top", "right"]].set_visible(False)
ax.set_title("v5 provisional set (105 questions): full pipeline vs. ablations (same frozen code)", fontsize=7)
save(fig, "fig5_ablation")

# Fig 6: risk-coverage under a confidence threshold, A0 and A7
ca = json.load(open(E / "results/confidence_analysis.json"))
fig, ax = plt.subplots(figsize=(3.5, 2.4))
for cfg, col, name in (("A0", "#4c78a8", "full pipeline (A0)"), ("A7", "#e45756", "safeguards off (A7)")):
    pts = [p for p in ca[cfg]["risk_coverage"] if p["answered"]]
    xs = [p["coverage_of_answerable"] for p in pts]; ys = [p["risk"] for p in pts]
    ax.plot(xs, ys, marker="o", ms=2.5, lw=0.9, color=col, label=name)
ax.set_xlabel(f"correct answers / {n_ans} answerable (coverage)"); ax.set_ylabel("wrong / answered (risk)")
ax.set_title("Risk vs. coverage when answering only if score >= t", fontsize=7)
ax.legend(fontsize=6, frameon=False); ax.spines[["top", "right"]].set_visible(False)
save(fig, "fig6_risk_coverage")

# Fig 7: outcome by category (A0)
cats = sorted({r["category"] for r in A0})
order = ["correct", "silent_wrong", "wrong_answer_to_clarify_item", "correct_clarify", "unnecessary_clarify"]
cols = {"correct": "#4c78a8", "silent_wrong": "#e45756", "wrong_answer_to_clarify_item": "#f58518",
        "correct_clarify": "#54a24b", "unnecessary_clarify": "#bab0ac"}
names = {"correct": "correct answer", "silent_wrong": "wrong value", "wrong_answer_to_clarify_item": "answered a clarify item",
         "correct_clarify": "appropriate clarification", "unnecessary_clarify": "unnecessary clarification"}
cnt = {c: collections.Counter(r["outcome"] for r in A0 if r["category"] == c) for c in cats}
fig, ax = plt.subplots(figsize=(7.16, 2.8))
left = [0] * len(cats)
for o in order:
    v = [cnt[c][o] for c in cats]
    ax.barh(range(len(cats)), v, left=left, color=cols[o], label=names[o], height=0.7)
    left = [a + b for a, b in zip(left, v)]
ax.set_yticks(range(len(cats))); ax.set_yticklabels([c.replace("_", " ") for c in cats], fontsize=6)
ax.invert_yaxis(); ax.set_xlabel("questions"); ax.legend(fontsize=6, frameon=False, ncol=5, loc="lower center",
                                                          bbox_to_anchor=(0.45, 1.0))
ax.spines[["top", "right"]].set_visible(False)
save(fig, "fig7_outcomes_by_category")
print("ok")
