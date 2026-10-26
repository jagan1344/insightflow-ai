"""Run the v7 provisional set ONCE through the full Orchestrator in all three engine modes and save raw output.
Refuses unless backend/ and v7_set.py match V7_MANIFEST.sha256; never overwrites an output. Scoring: score_v7.py.
usage (from backend/): PYTHONPATH=. python ../research_improvement/architecture_recovery/v7_provisional/run_v7.py"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "v7_raw_first_run.json"
MODES = ("typed", "legacy", "typed+legacy")


def manifest():
    m = dict(line.split("  ", 1)[::-1] for line in (HERE / "V7_MANIFEST.sha256").read_text().split("\n") if line.strip())
    return {k.strip(): v.strip() for k, v in m.items()}


def check():
    m = manifest()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD:backend"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, text=True).strip()
    if tree != m["backend_tree"] or dirty:
        sys.exit(f"backend tree {tree} (dirty={bool(dirty)}) is not the frozen tree {m['backend_tree']}; refusing")
    h = hashlib.sha256((HERE / "v7_set.py").read_bytes()).hexdigest()
    if h != m["v7_set.py"]:
        sys.exit("v7_set.py does not match the manifest; refusing")
    if OUT.exists():
        sys.exit(f"{OUT} exists; the set is run once and never overwritten")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), tree


def main():
    head, tree = check()
    sys.path.insert(0, str(HERE))
    import v7_set as V
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import bootstrap, register_relational, set_active
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.orchestrator import Orchestrator

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="v7run_"))
    recs = []
    for dom, build in V.BUILD.items():
        src = build()
        dst = tmp / f"{dom}.db"
        shutil.copy(src, dst)
        settings.database_url = f"sqlite:///{dst}"
        reset_engine(); bootstrap()
        ds_id = register_relational(dom, V.ANCHOR[dom])
        reset_engine(); refresh_schema(); set_active(ds_id)
        for qid, text, _e, _ref, _k in V.Q[dom]:
            for mode in MODES:
                os.environ["INSIGHTFLOW_ENGINE"] = mode
                t0 = time.perf_counter()
                try:
                    r = Orchestrator().ask(text)
                    action, sql, reason = r.decision.action, r.sql or "", r.decision.reason
                    rows = [list(x) for x in r.result.rows] if (r.result and r.result.ok) else []
                    path = "typed" if (r.diagnostics or {}).get("engine") == "typed" else "legacy"
                except Exception as e:  # recorded, never hidden
                    action, sql, reason, rows, path = "ERROR", "", f"{type(e).__name__}: {e}", [], "error"
                recs.append(dict(id=qid, domain=dom, question=text, mode=mode, action=action, path=path, sql=sql,
                                 reason=reason, rows=rows[:200], latency_ms=round((time.perf_counter() - t0) * 1000, 1)))
    os.environ.pop("INSIGHTFLOW_ENGINE", None)
    OUT.write_text(json.dumps(dict(commit=head, backend_tree=tree, n=len(recs), records=recs), indent=1, default=str))
    print(f"wrote {OUT} ({len(recs)} records) at {head}")


if __name__ == "__main__":
    main()
