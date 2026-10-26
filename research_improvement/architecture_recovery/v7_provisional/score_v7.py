"""Score the saved v7 raw output (never modifies it). Same row-matching rule as every earlier set.
usage (from backend/): PYTHONPATH=. python ../research_improvement/architecture_recovery/v7_provisional/score_v7.py"""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "devsets"))
sys.path.append(str(HERE.parents[2] / "evaluation" / "v3"))

import v7_set as V  # noqa: E402
from run_dev import judge  # noqa: E402


class _R:
    def __init__(self, status, rows):
        self.status, self.rows = status, [tuple(x) for x in rows]


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - w, 3), round(c + w, 3))


def main():
    raw = json.loads((HERE / "v7_raw_first_run.json").read_text())
    meta = {qid: (dom, e, ref, k) for dom, items in V.Q.items() for qid, _t, e, ref, k in items}
    refs = {}
    for dom, build in V.BUILD.items():
        con = sqlite3.connect(build())
        for qid, _t, _e, ref, _k in V.Q[dom]:
            refs[qid] = [tuple(x) for x in con.execute(ref).fetchall()] if ref else None
        con.close()
    out = []
    for r in raw["records"]:
        dom, e, ref, k = meta[r["id"]]
        st = "answer" if r["action"] in ("ANSWER", "WARN") else "error" if r["action"] == "ERROR" else "abstain"
        out.append(dict(r, expect=e, kind=k, outcome=judge(e, k, refs[r["id"]], _R(st, r["rows"]))))
    summary = {}
    for mode in ("typed", "legacy", "typed+legacy"):
        rs = [x for x in out if x["mode"] == mode]
        A = [x for x in rs if x["expect"] == "answer"]
        cor = sum(x["outcome"] == "correct" for x in A)
        wrong_a = sum(x["outcome"] == "wrong" for x in A)
        wrong_u = sum(x["outcome"] == "answered_unanswerable" for x in rs)
        wrong_e = sum(x["outcome"] == "wrong" for x in rs if x["expect"] == "either")
        answered = sum(x["action"] in ("ANSWER", "WARN") for x in rs)
        lat = sorted(x["latency_ms"] for x in rs)
        summary[mode] = dict(n=len(rs), answerable=len(A), correct=cor, correct_ci95=wilson(cor, len(A)),
                             wrong_answerable=wrong_a, answered_unanswerable=wrong_u, either_wrong=wrong_e,
                             wrong_total=wrong_a + wrong_u + wrong_e, answered=answered,
                             wrong_rate_among_answered=round((wrong_a + wrong_u + wrong_e) / answered, 3) if answered else None,
                             wrong_among_answered_ci95=wilson(wrong_a + wrong_u + wrong_e, answered),
                             unanswerable_refused=f"{sum(x['outcome'] == 'abstain_ok' for x in rs if x['expect'] in ('clarify', 'unsupported'))}/"
                                                  f"{sum(x['expect'] in ('clarify', 'unsupported') for x in rs)}",
                             either_correct=sum(x["outcome"] == "correct" for x in rs if x["expect"] == "either"),
                             errors=sum(x["action"] == "ERROR" for x in rs),
                             latency_ms_p50=lat[len(lat) // 2], latency_ms_p95=lat[int(len(lat) * 0.95)],
                             outcomes=dict(Counter(x["outcome"] for x in rs)))
    by = {}
    for x in out:
        by.setdefault(x["id"], {})[x["mode"]] = x["outcome"]
    summary["paired_legacy_to_typed"] = {f"{a} -> {b}": n for (a, b), n in
                                         Counter((v["legacy"], v["typed"]) for v in by.values()).items()}
    (HERE / "v7_scored.json").write_text(json.dumps(dict(source="v7_raw_first_run.json", commit=raw["commit"],
                                                         summary=summary, records=out), indent=1, default=str))
    print(json.dumps(summary, indent=1))
    for x in out:
        if x["mode"] == "typed" and x["outcome"] not in ("correct", "abstain_ok"):
            print(f"{x['id']} {x['outcome']:22s} {x['question']}\n    -> {x['action']}: {x['reason'][:170]}\n    {x['sql'][:240]}")


if __name__ == "__main__":
    main()
