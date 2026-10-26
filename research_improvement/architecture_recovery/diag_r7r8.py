"""DIAGNOSTIC ONLY: run the new engine on the already-revealed Round 7 (v5) and Round 8 (v6) sets and score with the
unchanged scorer. These sets were seen before the engine was written, so the numbers are regression diagnostics,
never independent evidence, and the sets must not be used to tune the engine.
usage (from backend/): PYTHONPATH=. python ../research_improvement/architecture_recovery/diag_r7r8.py <out_dir>"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_improvement" / "eval"))
import score_v5 as S  # noqa: E402

from insightflow.engine.engine import answer  # noqa: E402

SETS = {
    "v5": (ROOT / "evaluation" / "v5_provisional", "fixtures_v5", "questions_v5", "V5",
           {"HO18", "HO19", "IN18", "IN20", "EN12", "EN13", "RI15", "RI16"}),
    "v6": (ROOT / "evaluation" / "v6_blind", "fixtures_v6", "questions_v6", "V6", {"FD16", "LS16", "TC15", "WH17"}),
}


def run(name: str):
    d, fx, qs, var, pct = SETS[name]
    sys.path.insert(0, str(d))
    FX = __import__(fx)
    QS = getattr(__import__(qs), var)
    paths = FX.build_all()
    data = pathlib.Path(next(iter(paths.values()))).parent
    ref = json.load(open(d / "reference_results.json"))
    recs = []
    for q in QS:
        db, anchor = q["db"].split("@")
        r = answer(q["question"], str(data / f"{db}.db"), anchor)
        action = "ANSWER" if r.status == "answer" else "ERROR" if r.status == "error" else "CLARIFY"
        recs.append(dict(id=q["id"], db=q["db"], category=q["category"], answerability=q["expected_answerability"],
                         kind=q["kind"], question=q["question"], action=action, status=r.status, message=r.message,
                         sql=r.display_sql, rows=[list(x) for x in r.rows[:500]], expected=ref.get(q["id"]),
                         latency_ms=r.ms, trace=r.trace()))
    S.PERCENT_IDS = pct
    s = S.summarize(recs)
    sys.path.remove(str(d))
    return recs, s


def main(out_dir: str):
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    for name in SETS:
        recs, s = run(name)
        json.dump(dict(engine_commit=head, diagnostic_only=True, records=recs, summary=s),
                  open(out / f"{name}_engine_diag.json", "w"), indent=1, default=str)
        print(name, {k: s[k] for k in ("n", "answerable", "correct", "coverage", "accuracy_when_answered",
                                        "silent_wrong_answerable", "answered_clarify_items", "correct_clarify",
                                        "clarify_or_unsupported", "unnecessary_clarify", "errors", "latency_ms_p50")})


if __name__ == "__main__":
    main(sys.argv[1])
