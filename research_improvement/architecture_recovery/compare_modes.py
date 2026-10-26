"""Controlled comparison through the full Orchestrator: legacy (frozen da925ad pipeline) vs typed vs typed+legacy, on the
same development and held-out questions, same databases, same scorer. Raw records are written before any summary.
usage (from backend/): PYTHONPATH=. python ../research_improvement/architecture_recovery/compare_modes.py <out.json>"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "devsets"))
sys.path.append(str(HERE.parents[1] / "evaluation" / "v3"))

import dev_questions as DQ  # noqa: E402
import heldout as H  # noqa: E402
from run_dev import judge  # noqa: E402
from run_heldout import dbs as heldout_dbs  # noqa: E402

MODES = ("legacy", "typed", "typed+legacy")


class _R:
    def __init__(self, status, rows):
        self.status, self.rows = status, rows


def items():
    for dom, qs in DQ.Q.items():
        for it in qs:
            yield ("dev",) + (dom,) + it
    for dom, qs in H.Q.items():
        for it in qs:
            yield ("heldout", dom) + it


def main(out_path: str):
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import bootstrap, register_relational, set_active
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.orchestrator import Orchestrator

    src = heldout_dbs()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cmp_"))
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()
    anchors = {**DQ.ANCHOR, **H.ANCHOR}
    recs, cur = [], None
    for split, dom, qid, text, expect, ref, kind in items():
        if dom != cur:
            cur = dom
            dst = tmp / f"{dom}.db"
            shutil.copy(src[dom], dst)
            settings.database_url = f"sqlite:///{dst}"
            reset_engine(); bootstrap()
            ds_id = register_relational(dom, anchors[dom])
            reset_engine(); refresh_schema(); set_active(ds_id)
            con = sqlite3.connect(src[dom])
        ref_rows = [tuple(x) for x in con.execute(ref).fetchall()] if ref else None
        for mode in MODES:
            os.environ["INSIGHTFLOW_ENGINE"] = mode
            t0 = time.perf_counter()
            try:
                r = Orchestrator().ask(text)
                ans = r.decision.action in ("ANSWER", "WARN")
                rows = [tuple(x) for x in r.result.rows] if (ans and r.result and r.result.ok) else []
                status, sql, reason = ("answer" if ans else "abstain"), r.sql or "", r.decision.reason
                path = "typed" if (r.diagnostics or {}).get("engine") == "typed" else "legacy"
            except Exception as e:  # recorded, never hidden
                status, rows, sql, reason, path = "error", [], "", f"{type(e).__name__}: {e}", "error"
            ms = round((time.perf_counter() - t0) * 1000, 1)
            recs.append(dict(split=split, domain=dom, id=qid, question=text, expect=expect, kind=kind, mode=mode,
                             status=status, path=path, sql=sql, reason=reason, rows=[list(x) for x in rows[:200]],
                             ms=ms, outcome=judge(expect, kind, ref_rows, _R(status, rows))))
    os.environ.pop("INSIGHTFLOW_ENGINE", None)
    pathlib.Path(out_path).write_text(json.dumps(dict(commit=head, records=recs), indent=1, default=str))
    summarise(recs)


def summarise(recs):
    for split in ("dev", "heldout"):
        print(f"== {split}")
        for mode in MODES:
            rs = [r for r in recs if r["split"] == split and r["mode"] == mode]
            ans = [r for r in rs if r["expect"] == "answer"]
            c = Counter(r["outcome"] for r in rs)
            lat = sorted(r["ms"] for r in rs)
            print(f"  {mode:13s} answerable correct {sum(r['outcome'] == 'correct' for r in ans)}/{len(ans)}  "
                  f"wrong(answerable) {sum(r['outcome'] == 'wrong' for r in ans)}  "
                  f"answered unanswerable {c['answered_unanswerable']}  either-wrong "
                  f"{sum(r['outcome'] == 'wrong' for r in rs if r['expect'] == 'either')}  "
                  f"errors {sum(r['status'] == 'error' for r in rs)}  p50 {lat[len(lat) // 2]} ms  p95 {lat[int(len(lat) * .95)]} ms")
        by = {}
        for r in recs:
            if r["split"] == split:
                by.setdefault(r["id"], {})[r["mode"]] = r["outcome"]
        tr = Counter((v["legacy"], v["typed"]) for v in by.values())
        print("  paired legacy -> typed:", dict(tr))


if __name__ == "__main__":
    main(sys.argv[1])
