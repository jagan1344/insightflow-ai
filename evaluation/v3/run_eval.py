"""Run a v3 question set against a system and score vs independent SQL.

usage: python run_eval.py <set: dev|final> <label>
Writes results/<set>_<label>.json (+ .md). Never overwrites other labels.
"""
from __future__ import annotations

import json, os, pathlib, sqlite3, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(HERE))
import fixtures as F  # noqa: E402

FACT = {"clinic": "visits", "logistics": "shipments", "university": "enrollments"}


def parse(spec):
    """'name' or 'name@anchor_table' -> (name, anchor)"""
    name, _, anchor = spec.partition("@")
    return name, (anchor or FACT[name])


def ref(db, sql):
    with sqlite3.connect(str(F.DATA / f"{parse(db)[0]}.db")) as c:
        return c.execute(sql).fetchall()


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def close(a, b, tol=1e-6):
    a, b = _num(a), _num(b)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(abs(a), abs(b), 1.0)


def score(kind, rows, expected):
    """-> (matches, system_value)"""
    if kind == "scalar":
        sv = rows[0][-1] if rows else None
        return (len(rows) == 1 and close(sv, expected[0][0])), sv
    if kind == "empty_ok":
        e = expected[0][0] if expected else None
        if not rows:
            return True, None
        sv = rows[0][-1]
        return (len(rows) == 1 and (sv is None or close(sv, 0) or close(sv, e))), sv
    if kind in ("rowset", "ordered"):
        try:
            sm = [(str(r[0]), float(r[-1])) for r in rows]
        except (TypeError, ValueError):
            return False, None
        em = [(str(r[0]), float(r[-1])) for r in expected]
        if kind == "ordered":
            ok = len(sm) == len(em) and all(a[0] == b[0] and close(a[1], b[1])
                                             for a, b in zip(sm, em))
        else:
            d, e = dict(sm), dict(em)
            ok = len(sm) == len(d) and set(d) == set(e) and all(close(d[k], e[k]) for k in e)
        return ok, sm
    raise ValueError(kind)


def main(set_name, label, register):
    from importlib import import_module
    qs = import_module(f"{set_name}_questions").__dict__[set_name.upper()]
    results = []
    cur_db = None
    orch = None
    for db, qid, fam, q, kind, sql in qs:
        if db != cur_db:
            cur_db = db
            from insightflow.orchestrator import Orchestrator
            register(db)
        r_ = None
        t0 = time.perf_counter()
        try:
            r = Orchestrator().ask(q)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            action = r.decision.action
            conf = float(getattr(r.confidence, "score", 0.0) or 0.0)
            rows = list(r.result.rows) if (r.result and r.result.ok) else []
            gen_sql = (r.sql or "")[:300]
        except Exception as e:
            action, conf, rows, gen_sql = "ERROR", 0.0, [], f"{type(e).__name__}: {e}"
            latency_ms = int((time.perf_counter() - t0) * 1000)
        answered = action in ("ANSWER", "WARN")
        if kind == "grain_trap":
            outcome = ("correct_clarify" if action in ("CLARIFY", "ABSTAIN", "WARN")
                       else "silent_wrong" if answered else "error")
            sysv = None
        elif kind == "clarify":
            outcome = "correct_clarify" if action in ("CLARIFY", "ABSTAIN") else (
                "silent_wrong" if answered else "error")
            sysv = None
        else:
            exp = ref(db, sql)
            if answered:
                ok, sysv = score(kind, rows, exp)
                outcome = "correct" if ok else "silent_wrong"
            elif action in ("CLARIFY", "ABSTAIN"):
                outcome, sysv = "abstained", None
            else:
                outcome, sysv = "error", None
        results.append(dict(db=db, id=qid, family=fam, question=q, kind=kind,
                            action=action, confidence=round(conf, 3),
                            outcome=outcome, latency_ms=latency_ms,
                            sys_value=str(sysv)[:120],
                            expected=(None if kind in ("clarify", "grain_trap") else str(ref(db, sql))[:120]),
                            sql=gen_sql))
    write(set_name, label, results)


def write(set_name, label, results):
    def cnt(f): return sum(1 for r in results if f(r))
    ans = [r for r in results if r["kind"] not in ("clarify", "grain_trap")]
    cl = [r for r in results if r["kind"] in ("clarify", "grain_trap")]
    summ = {
        "n": len(results), "answerable": len(ans),
        "correct": cnt(lambda r: r["outcome"] == "correct"),
        "answered_answerable": cnt(lambda r: r in ans and r["action"] in ("ANSWER", "WARN")),
        "silent_wrong": cnt(lambda r: r["outcome"] == "silent_wrong"),
        "abstained_answerable": cnt(lambda r: r["outcome"] == "abstained"),
        "should_clarify": len(cl),
        "correct_clarify": cnt(lambda r: r["outcome"] == "correct_clarify"),
        "errors": cnt(lambda r: r["outcome"] == "error"),
    }
    wrong = [r for r in results if r["outcome"] == "silent_wrong"]
    summ["mean_conf_silent_wrong"] = (round(sum(r["confidence"] for r in wrong) / len(wrong), 3) if wrong else None)
    summ["silent_wrong_conf_ge_0_7"] = cnt(lambda r: r["outcome"] == "silent_wrong" and r["confidence"] >= 0.7)
    lat = sorted(r["latency_ms"] for r in results)
    summ["latency_ms_p50"] = lat[len(lat) // 2] if lat else None
    summ["latency_ms_p95"] = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
    bands = {"[0,0.3)": (0, 0.3), "[0.3,0.7)": (0.3, 0.7), "[0.7,0.9)": (0.7, 0.9), "[0.9,1.0]": (0.9, 1.01)}
    cal = {}
    for b, (lo_, hi_) in bands.items():
        inb = [r for r in results if r["action"] in ("ANSWER", "WARN") and lo_ <= r["confidence"] < hi_]
        cal[b] = {"answered": len(inb),
                  "correct": sum(r["outcome"] == "correct" for r in inb),
                  "silent_wrong": sum(r["outcome"] == "silent_wrong" for r in inb)}
    summ["calibration_by_confidence_band"] = cal
    fams = {}
    for r in results:
        f = fams.setdefault(r["family"], {"n": 0, "correct": 0, "silent_wrong": 0})
        f["n"] += 1
        f["correct"] += r["outcome"] in ("correct", "correct_clarify")
        f["silent_wrong"] += r["outcome"] == "silent_wrong"
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / f"{set_name}_{label}.json").write_text(json.dumps(
        {"summary": summ, "by_family": fams, "results": results}, indent=2))
    L = [f"# {set_name} / {label}", "",
         f"- correct answers: {summ['correct']}/{summ['answerable']} answerable",
         f"- answered answerable: {summ['answered_answerable']}/{summ['answerable']}",
         f"- silent wrong (answered, wrong; incl. answered-when-should-clarify): {summ['silent_wrong']}/{summ['n']}",
         f"- of which confidence >= 0.70: {summ['silent_wrong_conf_ge_0_7']}",
         f"- abstained on answerable: {summ['abstained_answerable']}",
         f"- correct clarifications: {summ['correct_clarify']}/{summ['should_clarify']}",
         f"- errors: {summ['errors']}", "",
         "| id | family | outcome | action | conf | question |", "|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['id']} | {r['family']} | {r['outcome']} | {r['action']} | {r['confidence']} | {r['question']} |")
    (out / f"{set_name}_{label}.md").write_text("\n".join(L) + "\n")
    print(json.dumps(summ))
