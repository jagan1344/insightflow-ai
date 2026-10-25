"""Figures 1-4: pipeline diagrams drawn from the stages in backend/insightflow/orchestrator.py
(step numbers in labels refer to its comments). Vector output (PDF + SVG), sized for one IEEE column
(3.5 in) or two columns (7.16 in)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none"})
C = {"plan": "#dbe8f5", "sql": "#e3f1e0", "check": "#fdf0d5", "dec": "#f6dcdc", "io": "#eeeeee"}


def box(ax, x, y, w, h, text, kind, fs=6.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc=C[kind], ec="#333333", lw=0.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", lw=0.6, color="#333333"))


def save(fig, name):
    for ext in ("pdf", "svg"):
        fig.savefig(f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


# Fig 1: architecture (two-column)
fig, ax = plt.subplots(figsize=(7.16, 2.3)); ax.set_xlim(0, 14.3); ax.set_ylim(0, 4.6); ax.axis("off")
row = [("Question", "io"), ("Pre-SQL\nsafety\n[0]", "check"),
       ("Planner:\ngrounded\nIR [1-2]", "plan"), ("Adaptive\nclarify\n[2b]", "check"),
       ("Compiler\n[4]", "sql"), ("SQL\nchecks\n[5a-5d]", "check"),
       ("Read-only\nexecution\n[6]", "sql")]
for i, (t, k) in enumerate(row):
    box(ax, 0.1 + i * 2.03, 3.0, 1.8, 1.3, t, k, fs=6)
    if i: arrow(ax, 0.1 + i * 2.03 - 0.23, 3.65, 0.1 + i * 2.03, 3.65)
row2 = [("Result\nchecks\n[6b-7]", "check"), ("Confidence\n9 signals\n[10]", "dec"),
        ("Thresholds\n0.70/0.40\n[11]", "dec"), ("Vetoes:\ncoverage,\naudit,\nverifier\n[11c-d]", "check"),
        ("Semantic\nlayer\n[12b]", "check"), ("Answer +\nSQL +\nevidence,\nor clarify", "io")]
for i, (t, k) in enumerate(row2):
    x = 12.28 - i * 2.03 - 1.8 + 1.8 - 0.0
    box(ax, 12.28 - i * 2.03, 0.4, 1.8, 1.3, t, k, fs=6)
    if i: arrow(ax, 12.28 - (i - 1) * 2.03, 1.05, 12.28 - i * 2.03 + 1.8, 1.05)
arrow(ax, 13.28, 3.0, 13.28, 1.7)
ax.text(0.1, 2.25, "Schema discovery (declared + inferred FKs, abbreviations, value index) and the KPI\ncatalogue "
        "feed the planner, the checks and the semantic layer. [n] = step in orchestrator.py", fontsize=6, style="italic")
save(fig, "fig1_architecture")

# Fig 2: semantic verification workflow (one column)
fig, ax = plt.subplots(figsize=(3.5, 3.3)); ax.set_xlim(0, 6); ax.set_ylim(0, 7.4); ax.axis("off")
steps = [("Question + plan + SQL + rows + text", "io"),
         ("Typed spec: metrics (agg, grounded column,\nsemantic type), shape, dims, filters + polarity,\ndate role, joins, unresolved", "plan"),
         ("Type check (before trusting the answer):\nflag/id as quantity, shape, guessed date role,\nunsafe join, polarity, ratio, measure-noun count", "check"),
         ("Preservation: spec vs SQL vs rows vs text\n(time bounds, row shape, exclusions,\nnumbers traceable to rows)", "check"),
         ("Violation -> CLARIFY (conf <= 0.30)\nNote -> WARN with stated assumption\nException -> CLARIFY (fail closed)", "dec")]
for i, (t, k) in enumerate(steps):
    y = 6.3 - i * 1.5
    box(ax, 0.2, y, 5.6, 1.05 if i else 0.7, t, k, fs=6.2)
    if i: arrow(ax, 3.0, y + 1.5, 3.0, y + 1.05)
save(fig, "fig2_semantic_verification")

# Fig 3: decision process (one column)
fig, ax = plt.subplots(figsize=(3.5, 3.0)); ax.set_xlim(0, 6); ax.set_ylim(0, 6.6); ax.axis("off")
box(ax, 0.2, 5.6, 5.6, 0.8, "SQL invalid or execution failed -> ABSTAIN", "dec", 6)
box(ax, 0.2, 4.5, 5.6, 0.8, "Plan ambiguous, item unavailable or\nplan-SQL fidelity failed -> CLARIFY", "dec", 6)
box(ax, 0.2, 3.4, 5.6, 0.8, "Score >= 0.70 -> ANSWER;  0.40-0.70 -> WARN;\n< 0.40 -> ABSTAIN", "dec", 6)
box(ax, 0.2, 2.3, 5.6, 0.8, "Any veto (coverage, audit, verifier, semantic)\n-> CLARIFY, score capped at 0.30", "check", 6)
box(ax, 0.2, 1.2, 5.6, 0.8, "Standing caveat (inferred FK, related-table\ngrain, stated assumption) -> WARN", "check", 6)
box(ax, 0.2, 0.1, 5.6, 0.8, "The score is a weighted validity score,\nnot a calibrated probability", "io", 6)
for y in (5.6, 4.5, 3.4, 2.3):
    arrow(ax, 3.0, y, 3.0, y - 0.3)
save(fig, "fig3_decision_process")
print("ok")
