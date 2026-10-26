"""Run the new engine on the development questions under both naming schemes and score against the reference SQL.
usage (from backend/):  PYTHONPATH=. python ../research_improvement/architecture_recovery/devsets/run_dev.py [out.json]
Development data written by the developer: results are diagnostic, never independent evidence."""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[2] / "evaluation" / "v3"))

import dev_schemas as D  # noqa: E402
from dev_questions import ANCHOR, Q  # noqa: E402
from run_eval import score  # noqa: E402  (same row-matching rule as earlier sealed sets)

from insightflow.engine.engine import answer  # noqa: E402


def to_full(sql: str, dom: str) -> str:
    for a, b in sorted(D.RENAME[dom].items(), key=lambda kv: -len(kv[0])):
        sql = re.sub(rf"\b{a}\b", b, sql)
    return sql


def judge(expect, kind, ref_rows, res):
    if res.status != "answer":
        return "abstain_ok" if expect in ("clarify", "unsupported", "either") else "abstain"
    if expect in ("clarify", "unsupported"):
        return "answered_unanswerable"
    ok, _ = score(kind, [tuple(r) for r in res.rows], ref_rows)
    if not ok and kind == "rowset":      # groups present in the lookup with no facts (0/NULL) are allowed
        keep = [r for r in res.rows if not (r[-1] is None or r[-1] == 0) or str(r[0]) in {str(e[0]) for e in ref_rows}]
        ok = score(kind, keep, ref_rows)[0] if len(keep) != len(res.rows) else False
    return "correct" if ok else "wrong"


def run(scheme: str, engine=answer):
    paths = D.build_all(scheme)
    out = []
    for dom, items in Q.items():
        db = str(paths[dom])
        for qid, text, expect, ref, kind in items:
            ref_rows = None
            if ref:
                sql = ref if scheme == "abbr" else to_full(ref, dom)
                con = sqlite3.connect(db)
                ref_rows = [tuple(r) for r in con.execute(sql).fetchall()]
                con.close()
            res = engine(text, db, ANCHOR[dom])
            out.append(dict(id=qid, domain=dom, scheme=scheme, question=text, expect=expect, kind=kind,
                            outcome=judge(expect, kind, ref_rows, res), status=res.status, message=res.message,
                            sql=res.display_sql, rows=[list(r) for r in res.rows[:50]], ms=res.ms,
                            reliability=res.reliability))
    return out


def summary(recs):
    from collections import Counter
    c = Counter(r["outcome"] for r in recs)
    ans = [r for r in recs if r["expect"] == "answer"]
    una = [r for r in recs if r["expect"] in ("clarify", "unsupported")]
    eit = [r for r in recs if r["expect"] == "either"]
    answered = [r for r in recs if r["status"] == "answer"]
    wrong = [r for r in answered if r["outcome"] in ("wrong", "answered_unanswerable")]
    return dict(n=len(recs), answerable=len(ans), correct=sum(r["outcome"] == "correct" for r in ans),
                wrong=sum(r["outcome"] == "wrong" for r in ans), abstain=sum(r["outcome"] == "abstain" for r in ans),
                unanswerable=len(una), unanswerable_abstained=sum(r["outcome"] == "abstain_ok" for r in una),
                either=len(eit), either_correct=sum(r["outcome"] == "correct" for r in eit),
                either_wrong=sum(r["outcome"] == "wrong" for r in eit),
                answered=len(answered), wrong_among_answered=len(wrong), counts=dict(c),
                median_ms=sorted(r["ms"] for r in recs)[len(recs) // 2])


def main():
    out = {s: run(s) for s in ("abbr", "full")}
    a = {r["id"]: r for r in out["abbr"]}
    agree = sum(1 for r in out["full"] if r["status"] == a[r["id"]]["status"] and r["rows"] == a[r["id"]]["rows"])
    rep = {s: summary(v) for s, v in out.items()}
    rep["metamorphic_agreement"] = f"{agree}/{len(out['full'])}"
    print(json.dumps(rep, indent=1))
    for s, recs in out.items():
        for r in recs:
            if r["outcome"] not in ("correct", "abstain_ok"):
                print(f"[{s}] {r['id']} {r['outcome']:22s} {r['question']}\n      -> {r['status']}: {r['message'][:160]}\n      {r['sql'][:240]}")
    if len(sys.argv) > 1:
        pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(summary=rep, records=out), indent=1, default=str))


if __name__ == "__main__":
    main()
