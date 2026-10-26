"""Question-by-question comparison of a post-hoc dev run with the frozen first run (A0)."""
import json, sys, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))
from score_v5 import outcome, summarize
base = json.load(open(pathlib.Path(__file__).resolve().parents[1] / "eval/results/v5_A0_first_run.json"))["records"]
new = json.load(open(sys.argv[1]))["records"]
s = summarize([dict(r) for r in new])
print({k: s[k] for k in ("correct", "answerable", "answered_answerable", "silent_wrong_answerable", "answered_clarify_items",
                         "silent_wrong_total", "correct_clarify", "unnecessary_clarify")})
b = {r["id"]: outcome(r) for r in base}; t = collections.Counter(); ex = collections.defaultdict(list)
for r in new:
    o = outcome(r); k = f"{b[r['id']]} -> {o}"
    if b[r["id"]] != o:
        t[k] += 1; ex[k].append(r["id"])
for k, v in sorted(t.items()): print(f"  {v:3} {k}: {' '.join(ex[k])}")
