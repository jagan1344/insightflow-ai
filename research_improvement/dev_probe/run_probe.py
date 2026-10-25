import sys, os, json, time
sys.path.insert(0, '/home/user/insightflow-ai/evaluation/v3'); sys.path.insert(0, '/home/user/insightflow-ai/backend')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir('/home/user/insightflow-ai/backend')
import fixtures_r6 as FR, baseline_current as B, run_eval as RE
from probe_questions import PROBE
FR.build_air(); FR.build_saas(); FR.build_farm()
from insightflow.orchestrator import Orchestrator
out = []; cur = None
for cat, db, q, exp in PROBE:
    if db != cur: B.register(db); cur = db
    t0 = time.perf_counter(); r = Orchestrator().ask(q); ms = int((time.perf_counter()-t0)*1000)
    act = r.decision.action; ans = act in ("ANSWER", "WARN")
    rows = [tuple(x) for x in r.result.rows] if (r.result and r.result.ok) else []
    if exp == "CLARIFY":
        verdict = "safe_reject" if not ans else "WRONG_answered"
    else:
        alt = exp.startswith("CLARIFY_OR:")
        sql = exp.split(":", 1)[1] if ":" in exp and (alt or exp.startswith("ORDERED:")) else exp
        if not ans:
            verdict = "safe_reject" if alt else "unnecessary_clarify"
        elif alt and sql == "SELECT 1":
            verdict = "answered_unverified"
        else:
            ref = RE.ref(db, sql)
            kind = "ordered" if exp.startswith("ORDERED:") else ("scalar" if len(ref) == 1 and len(ref[0]) == 1 else "rowset")
            ok, _ = RE.score(kind, rows, ref)
            verdict = "correct" if ok else "WRONG_answered"
    out.append(dict(category=cat, db=db, question=q, action=act, confidence=round(r.confidence.score, 3),
                    verdict=verdict, sql=r.sql, reason=r.decision.reason[:200], latency_ms=ms))
    print(f"{verdict:20} {act:7} {r.confidence.score:.2f} [{cat}] {q}")
json.dump(out, open(sys.argv[1], "w"), indent=1)
