"""Paired per-question transitions A0 -> Ak (k=1..7). Reads raw run files + scorer; writes
../03_ablation_results.csv and ablation_transitions.json."""
import csv, json, pathlib, collections
from score_v5 import outcome, summarize

R = pathlib.Path(__file__).resolve().parent / "results"
NAMES = {"A0": "full pipeline", "A1": "semantic layer off", "A2": "confidence threshold gate off",
         "A3": "result-consistency checks off", "A4": "plan-SQL fidelity gate off",
         "A5": "mention-coverage vetoes + wording audit off", "A6": "answer verifier off",
         "A7": "all six safeguards off",
         "B1": "only semantic layer on", "B2": "only confidence gate on", "B3": "only result consistency on",
         "B4": "only plan fidelity on", "B5": "only mention coverage + wording audit on", "B6": "only answer verifier on"}
runs = {"A0": json.load(open(R / "v5_A0_first_run.json"))["records"]}
for k in "1234567":
    runs[f"A{k}"] = json.load(open(R / f"v5_A{k}_ablation.json"))["records"]
for k in "123456":
    runs[f"B{k}"] = json.load(open(R / f"v5_B{k}_leave_one_in.json"))["records"]
for recs in runs.values():
    for r in recs:
        r["outcome"] = outcome(r)
GOOD = {"correct", "correct_clarify"}
WRONG = {"silent_wrong", "wrong_answer_to_clarify_item"}


def cls(o):
    return "correct" if o == "correct" else "wrong" if o in WRONG else "clarify_ok" if o == "correct_clarify" else "clarify_unnecessary" if o == "unnecessary_clarify" else o


rows, trans = [], {}
for cfg, recs in runs.items():
    s = summarize([dict(r) for r in recs])
    lat = sorted(r["latency_ms"] for r in recs)
    rows.append(dict(config=cfg, description=NAMES[cfg], n=s["n"], answerable=s["answerable"], correct=s["correct"],
                     answered_answerable=s["answered_answerable"], wrong_answers=s["silent_wrong_total"],
                     wrong_on_answerable=s["silent_wrong_answerable"], answered_clarify_items=s["answered_clarify_items"],
                     correct_clarify=s["correct_clarify"], clarify_items=s["clarify_or_unsupported"],
                     unnecessary_clarify=s["unnecessary_clarify"], coverage=s["coverage"],
                     accuracy_when_answered=s["accuracy_when_answered"], latency_p50_ms=s["latency_ms_p50"],
                     latency_p95_ms=s["latency_ms_p95"],
                     mean_conf_correct=round(sum(r["confidence"] for r in recs if r["outcome"] == "correct") /
                                             max(1, sum(r["outcome"] == "correct" for r in recs)), 3),
                     mean_conf_wrong=round(sum(r["confidence"] for r in recs if r["outcome"] in WRONG) /
                                           max(1, sum(r["outcome"] in WRONG for r in recs)), 3)))
    if cfg == "A0":
        continue
    ref_cfg = "A7" if cfg.startswith("B") else "A0"
    base = {r["id"]: r for r in runs[ref_cfg]}
    t = collections.Counter(); items = collections.defaultdict(list)
    for r in recs:
        a, b = cls(base[r["id"]]["outcome"]), cls(r["outcome"])
        key = f"{ref_cfg}:{a} -> {cfg}:{b}" if a != b else "no change"
        t[key] += 1
        if a != b:
            items[key].append(r["id"])
    trans[cfg] = dict(counts=dict(t), items=dict(items))
with open(pathlib.Path(__file__).resolve().parents[1] / "03_ablation_results.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
json.dump(trans, open(R / "ablation_transitions.json", "w"), indent=1)
for cfg, d in trans.items():
    print(cfg, NAMES[cfg]); [print("   ", k, v, d["items"].get(k, "")) for k, v in sorted(d["counts"].items())]
