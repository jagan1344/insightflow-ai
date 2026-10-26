"""Trace every v5 question through the pipeline (diagnostic; uses the revealed v5 set).
usage: python trace_v5.py <out.jsonl> [ids...]"""
import json, os, pathlib, shutil, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
V5 = ROOT / "evaluation" / "v5_provisional"
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(V5))
import fixtures_v5 as FX
from questions_v5 import V5 as QS
FX.build_all()
from insightflow.config import settings
from insightflow.execution.executor import reset_engine
from insightflow.knowledge.dataset_registry import register_relational, set_active, bootstrap
from insightflow.knowledge.schema_agent import refresh_schema
from insightflow.orchestrator import Orchestrator
ids = set(sys.argv[2:])
tmp = pathlib.Path(tempfile.mkdtemp(prefix="v5trace_")); data = V5 / "data"
cur = None; out = open(sys.argv[1], "w")
for q in QS:
    if ids and q["id"] not in ids:
        continue
    if q["db"] != cur:
        cur = q["db"]; name, anchor = cur.split("@")
        dst = tmp / f"{name}__{anchor}.db"; shutil.copy(data / f"{name}.db", dst)
        settings.database_url = f"sqlite:///{dst}"; os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
        reset_engine(); bootstrap(); ds_id = register_relational(cur, anchor); reset_engine(); refresh_schema(); set_active(ds_id)
    r = Orchestrator().ask(q["question"])
    pt = r.plan_trace if isinstance(r.plan_trace, dict) else {}
    out.write(json.dumps(dict(id=q["id"], cat=q["category"], ans=q["expected_answerability"], q=q["question"],
        ref=q["reference_sql"], metric=q["metric_definition"], action=r.decision.action, reason=r.decision.reason,
        sql=r.sql, rows=[list(x) for x in (r.result.rows[:5] if r.result and r.result.ok else [])],
        plan={k: pt.get(k) for k in ("intent_kind", "measures", "dims", "filters", "time", "unavailable", "notes") if k in pt},
        notes=r.notes, findings=r.diagnostics.get("semantic_findings")), default=str) + "\n")
print("done")
