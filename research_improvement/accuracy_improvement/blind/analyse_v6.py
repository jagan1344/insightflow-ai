"""Paired ablation transitions and confidence analysis for the v6 blind runs (frozen da925ad).
Writes v6_ablation_results.csv, v6_transitions.json, v6_confidence.json."""
import csv, json, pathlib, collections, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from score_v6 import outcome, summarize
R = pathlib.Path(__file__).resolve().parent / "results"
WRONG = {"silent_wrong", "wrong_answer_to_clarify_item"}
runs = {"A0": json.load(open(R / "v6_A0_first_run.json"))["records"]}
for c in "A1 A2 A3 A4 A5 A6 A7 B1 B2 B3 B4 B5 B6".split():
    runs[c] = json.load(open(R / f"v6_{c}_ablation.json"))["records"]
for recs in runs.values():
    for r in recs: r["outcome"] = outcome(r)
cls = lambda o: "correct" if o == "correct" else "wrong" if o in WRONG else "clarify_ok" if o == "correct_clarify" else "clarify_unnecessary"
rows, trans = [], {}
for cfg, recs in runs.items():
    s = summarize([dict(r) for r in recs])
    rows.append(dict(config=cfg, correct=s["correct"], answered=s["answered_answerable"], wrong=s["silent_wrong_total"],
                     correct_clarify=s["correct_clarify"], unnecessary_clarify=s["unnecessary_clarify"],
                     p50_ms=s["latency_ms_p50"], p95_ms=s["latency_ms_p95"]))
    if cfg == "A0": continue
    ref = "A7" if cfg.startswith("B") else "A0"
    base = {r["id"]: r for r in runs[ref]}
    t, ex = collections.Counter(), collections.defaultdict(list)
    for r in recs:
        a, b = cls(base[r["id"]]["outcome"]), cls(r["outcome"])
        if a != b: t[f"{ref}:{a} -> {cfg}:{b}"] += 1; ex[f"{ref}:{a} -> {cfg}:{b}"].append(r["id"])
    trans[cfg] = dict(counts=dict(t), items=dict(ex))
with open("v6_ablation_results.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
json.dump(trans, open("v6_transitions.json", "w"), indent=1)
conf = {}
for cfg in ("A0", "A7"):
    ans = [r for r in runs[cfg] if r["action"] in ("ANSWER", "WARN")]
    cor = [r["confidence"] for r in ans if r["outcome"] == "correct"]; wr = [r["confidence"] for r in ans if r["outcome"] in WRONG]
    pairs = [(c, w) for c in cor for w in wr]
    auroc = sum(1.0 if c > w else 0.5 if c == w else 0 for c, w in pairs) / len(pairs) if pairs else None
    ece = 0.0
    for i in range(5):
        b = [r for r in ans if i / 5 <= r["confidence"] < (i + 1) / 5 or (i == 4 and r["confidence"] == 1.0)]
        if b: ece += len(b) / len(ans) * abs(sum(r["outcome"] == "correct" for r in b) / len(b) - sum(r["confidence"] for r in b) / len(b))
    conf[cfg] = dict(answered=len(ans), correct=len(cor), wrong=len(wr), min_conf_answered=min(r["confidence"] for r in ans),
                     wrong_ge_0_9=sum(c >= 0.9 for c in wr), wrong_ge_0_7=sum(c >= 0.7 for c in wr),
                     mean_conf_correct=round(sum(cor) / len(cor), 4) if cor else None, mean_conf_wrong=round(sum(wr) / len(wr), 4) if wr else None,
                     auroc=None if auroc is None else round(auroc, 3), ece_5bin=round(ece, 3))
json.dump(conf, open("v6_confidence.json", "w"), indent=1)
for r in rows: print(r)
for k, v in trans.items(): print(k, v["counts"])
print(conf)
