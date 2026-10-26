"""Held-out check: `run` saves raw engine output (no scoring); `score` scores a saved raw file (never modifies it).
usage (from backend/):  PYTHONPATH=. python ../research_improvement/architecture_recovery/devsets/run_heldout.py run <raw.json>
                        PYTHONPATH=. python ../research_improvement/architecture_recovery/devsets/run_heldout.py score <raw.json>"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[2] / "evaluation" / "v3"))

import dev_schemas as D  # noqa: E402
import heldout as H  # noqa: E402


def dbs():
    p = D.build_all("abbr")
    p["library"] = H.build_library()
    p["clinic"] = H.build_clinic()
    return {k: str(v) for k, v in p.items()}


def run(out: str) -> None:
    from insightflow.engine.engine import answer
    paths = dbs()
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()
    recs = []
    for dom, items in H.Q.items():
        for qid, text, expect, _ref, _kind in items:
            r = answer(text, paths[dom], H.ANCHOR[dom])
            recs.append(dict(id=qid, domain=dom, question=text, status=r.status, message=r.message, sql=r.display_sql,
                             rows=[list(x) for x in r.rows[:200]], ms=r.ms, trace=r.trace()))
    pathlib.Path(out).write_text(json.dumps(dict(commit=sha, records=recs), indent=1, default=str))
    print(f"saved {len(recs)} raw records at commit {sha}")


def score_file(raw: str) -> dict:
    from run_dev import judge, summary

    class R:  # minimal stand-in for EngineResult
        def __init__(self, d):
            self.status, self.rows = d["status"], [tuple(x) for x in d["rows"]]

    data = json.loads(pathlib.Path(raw).read_text())
    paths = dbs()
    meta = {qid: (dom, e, ref, k) for dom, items in H.Q.items() for qid, _t, e, ref, k in items}
    recs = []
    for d in data["records"]:
        dom, expect, ref, kind = meta[d["id"]]
        ref_rows = None
        if ref:
            con = sqlite3.connect(paths[dom]); ref_rows = [tuple(x) for x in con.execute(ref).fetchall()]; con.close()
        recs.append(dict(d, expect=expect, kind=kind, outcome=judge(expect, kind, ref_rows, R(d))))
    s = summary(recs)
    s["new_schemas"] = summary([r for r in recs if r["domain"] in ("library", "clinic")])
    s["dev_schemas_new_phrasing"] = summary([r for r in recs if r["domain"] not in ("library", "clinic")])
    print(json.dumps(s, indent=1))
    for r in recs:
        if r["outcome"] not in ("correct", "abstain_ok"):
            print(f"{r['id']} {r['outcome']:22s} {r['question']}\n    -> {r['status']}: {r['message'][:170]}\n    {r['sql'][:260]}")
    return dict(summary=s, records=recs)


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        score_file(sys.argv[2])
