"""Confidence analysis on v5 runs A0 (full) and A7 (all post-generation safeguards off).
Writes results/confidence_analysis.json; figures are made by ../figures/make_result_figures.py."""
import json, pathlib
from score_v5 import outcome

R = pathlib.Path(__file__).resolve().parent / "results"
WRONG = {"silent_wrong", "wrong_answer_to_clarify_item"}
out = {}
for cfg, f in (("A0", "v5_A0_first_run.json"), ("A7", "v5_A7_ablation.json")):
    recs = json.load(open(R / f))["records"]
    for r in recs:
        r["outcome"] = outcome(r)
    ans = [r for r in recs if r["action"] in ("ANSWER", "WARN")]
    cor = [r["confidence"] for r in ans if r["outcome"] == "correct"]
    wr = [r["confidence"] for r in ans if r["outcome"] in WRONG]
    ref = [r["confidence"] for r in recs if r["action"] not in ("ANSWER", "WARN")]
    # ECE over answered items, 5 equal-width bins on [0,1], "correct" = outcome correct
    bins = []
    ece = 0.0
    for i in range(5):
        lo, hi = i / 5, (i + 1) / 5
        b = [r for r in ans if lo <= r["confidence"] < hi or (i == 4 and r["confidence"] == 1.0)]
        if b:
            acc = sum(r["outcome"] == "correct" for r in b) / len(b)
            mc = sum(r["confidence"] for r in b) / len(b)
            ece += len(b) / len(ans) * abs(acc - mc)
            bins.append(dict(lo=lo, hi=hi, n=len(b), accuracy=round(acc, 3), mean_conf=round(mc, 3)))
    # risk-coverage: answer only when conf >= t (among items the system answered); denominators stated
    grid = sorted({0.0, 0.4, 0.7, 0.9, 0.95, 0.97, 0.98, 0.985, 0.99, 0.995, 1.0} | {r["confidence"] for r in ans})
    rc = []
    n_answerable = sum(r["kind"] != "clarify" for r in recs)
    for t in grid:
        kept = [r for r in ans if r["confidence"] >= t]
        rc.append(dict(threshold=t, answered=len(kept), correct=sum(r["outcome"] == "correct" for r in kept),
                       wrong=sum(r["outcome"] in WRONG for r in kept),
                       coverage_of_answerable=round(sum(r["outcome"] == "correct" for r in kept) / n_answerable, 3),
                       risk=round(sum(r["outcome"] in WRONG for r in kept) / len(kept), 3) if kept else None))
    def q(xs):
        xs = sorted(xs)
        return dict(n=len(xs), min=xs[0], median=xs[len(xs) // 2], max=xs[-1], mean=round(sum(xs) / len(xs), 4)) if xs else dict(n=0)
    # AUROC of confidence for correct vs wrong among answered
    pairs = [(c, w) for c in cor for w in wr]
    auroc = (sum(1.0 if c > w else 0.5 if c == w else 0.0 for c, w in pairs) / len(pairs)) if pairs else None
    out[cfg] = dict(answered=len(ans), conf_correct=q(cor), conf_wrong=q(wr), conf_refused=q(ref),
                    high_conf_errors_ge_0_9=sum(c >= 0.9 for c in wr), high_conf_errors_ge_0_7=sum(c >= 0.7 for c in wr),
                    ece_5bin=round(ece, 3), reliability_bins=bins, auroc_correct_vs_wrong=None if auroc is None else round(auroc, 3),
                    risk_coverage=rc)
json.dump(out, open(R / "confidence_analysis.json", "w"), indent=1)
for k, v in out.items():
    print(k, {x: v[x] for x in ("answered", "conf_correct", "conf_wrong", "high_conf_errors_ge_0_9", "ece_5bin", "auroc_correct_vs_wrong")})
    print("   bins", v["reliability_bins"])
    print("   rc", [(round(x["threshold"], 4), x["answered"], x["correct"], x["wrong"]) for x in v["risk_coverage"]][-8:])
