"""Diagnostic (read-only): for a recorded run, split answerable questions by whether SQL was produced and whether
that SQL's result matches the reference, independent of the final decision."""
import json, sqlite3, sys, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))
from score_v5 import _match
run, data = sys.argv[1], pathlib.Path(sys.argv[2])
recs = json.load(open(run))["records"]
c = collections.Counter(); ex = collections.defaultdict(list)
for r in recs:
    if r["kind"] == "clarify":
        continue
    ok = None
    if r["sql"]:
        try:
            rows = [list(x) for x in sqlite3.connect(str(data / (r["db"].split("@")[0] + ".db"))).execute(r["sql"]).fetchall()]
            ok = _match(dict(id=r["id"], kind=r["kind"], rows=rows, expected=r["expected"]))
        except Exception:
            ok = "error"
    k = ("answered" if r["action"] in ("ANSWER", "WARN") else "refused", "no SQL" if ok is None else "SQL correct" if ok is True else "SQL wrong")
    c[k] += 1; ex[k].append(r["id"])
for k, v in sorted(c.items()): print(v, k, " ".join(ex[k][:40]))
