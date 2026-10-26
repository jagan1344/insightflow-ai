import os, pathlib, shutil, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[2]; V5 = ROOT / "evaluation" / "v5_provisional"
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(V5))
import fixtures_v5 as FX; from questions_v5 import V5 as QS
from insightflow.config import settings
from insightflow.execution.executor import reset_engine
from insightflow.knowledge.dataset_registry import register_relational, set_active, bootstrap, get_active_dataset
from insightflow.knowledge.schema_agent import refresh_schema
from insightflow.knowledge.vocabulary import normalise
tmp = pathlib.Path(tempfile.mkdtemp()); cur = None
for q in QS:
    if q["db"] != cur:
        cur = q["db"]; n, a = cur.split("@"); d = tmp / f"{n}.db"; shutil.copy(V5 / "data" / f"{n}.db", d)
        settings.database_url = f"sqlite:///{d}"; reset_engine(); bootstrap(); i = register_relational(cur, a); reset_engine(); refresh_schema(); set_active(i)
    nq, rw = normalise(q["question"], get_active_dataset())
    if rw: print(q["id"], "|", nq, "|", [r.describe() for r in rw])
