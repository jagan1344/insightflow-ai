"""Closure check: recompute the v7 headline figures from the committed raw output (v7_raw_first_run.json) and the
sealed set, independently of score_v7.py's summary. Reads only; writes nothing except stdout."""
import hashlib, json, math, pathlib, sqlite3, statistics, sys
from collections import Counter

V7 = pathlib.Path(__file__).resolve().parents[1] / "architecture_recovery" / "v7_provisional"
sys.path.insert(0, str(V7)); sys.path.append(str(V7.parents[2] / "evaluation" / "v3"))
import v7_set as V                                   # noqa: E402
from run_eval import score                           # noqa: E402  (row-matching rule of every earlier set)

man = {l.split("  ")[1].strip(): l.split("  ")[0] for l in (V7 / "V7_MANIFEST.sha256").read_text().splitlines() if l.strip()}
print("set sha256 matches manifest:", hashlib.sha256((V7 / "v7_set.py").read_bytes()).hexdigest() == man["v7_set.py"])
raw = json.loads((V7 / "v7_raw_first_run.json").read_text())
print("raw sha256:", hashlib.sha256((V7 / "v7_raw_first_run.json").read_bytes()).hexdigest()[:16], "commit:", raw["commit"][:7],
      "tree:", raw["backend_tree"][:8], "== manifest tree:", raw["backend_tree"] == man["backend_tree"])
meta = {q[0]: (d,) + q[1:] for d, qs in V.Q.items() for q in qs}
refs = {}
for d, b in V.BUILD.items():
    con = sqlite3.connect(b())
    for q in V.Q[d]:
        refs[q[0]] = [tuple(r) for r in con.execute(q[3]).fetchall()] if q[3] else None

def correct(rec):
    d, text, exp, ref, kind = meta[rec["id"]]
    rows = [tuple(r) for r in rec["rows"]]
    ok = score(kind, rows, refs[rec["id"]])[0]
    if not ok and kind == "rowset":
        keep = [r for r in rows if not (r[-1] is None or r[-1] == 0) or str(r[0]) in {str(e[0]) for e in refs[rec["id"]]}]
        ok = len(keep) != len(rows) and score(kind, keep, refs[rec["id"]])[0]
    return ok

res = {}
for mode in ("typed", "legacy", "typed+legacy"):
    rs = [r for r in raw["records"] if r["mode"] == mode]
    ans = lambda r: r["action"] in ("ANSWER", "WARN")
    A = [r for r in rs if meta[r["id"]][2] == "answer"]
    U = [r for r in rs if meta[r["id"]][2] in ("clarify", "unsupported")]
    E = [r for r in rs if meta[r["id"]][2] == "either"]
    cor = {r["id"] for r in A if ans(r) and correct(r)}
    wrong = sum(ans(r) and not correct(r) for r in A) + sum(ans(r) for r in U) + sum(ans(r) and not correct(r) for r in E)
    actions = Counter(r["action"] for r in rs)
    res[mode] = cor
    print(f"{mode:13s} correct {len(cor)}/{len(A)}  wrong {wrong}  unanswerable not answered {sum(not ans(r) for r in U)}/{len(U)}  "
          f"answered {sum(ans(r) for r in rs)}  median latency {statistics.median(r['latency_ms'] for r in rs):.1f} ms  actions {dict(actions)}")
b = len(res["typed"] - res["legacy"]); c = len(res["legacy"] - res["typed"])
n = b + c; k = min(b, c)
p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
print(f"answerable items: typed-only correct {b}, legacy-only correct {c}, both {len(res['typed'] & res['legacy'])}; exact McNemar (two-sided binomial) p = {p:.4f}")
