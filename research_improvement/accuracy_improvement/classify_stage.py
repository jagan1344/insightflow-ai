"""For each answerable v5 question: did the pipeline produce SQL, and does that SQL's result match the
reference (independently of the final decision)? Splits 'veto was over-strict' from 'veto caught wrong SQL'."""
import json, sqlite3, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))
from score_v5 import _match
V5 = pathlib.Path(__file__).resolve().parents[2] / "evaluation" / "v5_provisional"
qs = {q["id"]: q for q in __import__("importlib").import_module("questions_v5").V5} if False else None
sys.path.insert(0, str(V5)); from questions_v5 import V5 as QS
Q = {q["id"]: q for q in QS}
ref = json.load(open(V5 / "reference_results.json"))
rows = [json.loads(l) for l in open(sys.argv[1])]
out = []
for r in rows:
    q = Q[r["id"]]
    if q["kind"] == "clarify":
        continue
    sql_ok = None
    if r["sql"]:
        db = V5 / "data" / (q["db"].split("@")[0] + ".db")
        try:
            got = [list(x) for x in sqlite3.connect(str(db)).execute(r["sql"]).fetchall()]
            sql_ok = _match(dict(id=q["id"], kind=q["kind"], rows=got, expected=ref[q["id"]]))
        except Exception as e:
            sql_ok = f"error {e}"
    out.append(dict(id=r["id"], action=r["action"], sql_matches_reference=sql_ok, reason=r["reason"][:140]))
json.dump(out, open(sys.argv[2], "w"), indent=1)
import collections
c = collections.Counter((o["action"] in ("ANSWER", "WARN"), o["sql_matches_reference"]) for o in out)
for k, v in sorted(c.items(), key=str): print(v, "answered" if k[0] else "refused", "| SQL matches ref:", k[1])
