"""M0 baseline: what the CURRENT (single-table) system does on the
multi-table fixtures. The only thing it can be given is one table, so we
register each schema's fact table as an uploaded dataset (copy of the
fixture DB so registry metadata never touches the fixtures)."""
import pathlib, shutil, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "backend"))
import fixtures as F, run_eval as R

TMP = pathlib.Path(tempfile.mkdtemp(prefix="v3base_"))


def register(spec):
    import os, json
    db, anchor = R.parse(spec)
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import register_relational as register_uploaded, set_active, bootstrap
    from insightflow.knowledge.schema_agent import refresh_schema
    dst = TMP / f"{db}__{anchor}.db"
    shutil.copy(F.DATA / f"{db}.db", dst)
    settings.database_url = f"sqlite:///{dst}"
    reset_engine(); bootstrap()
    cfg = F.DATA / f"{db}.metrics.json"
    if cfg.exists():
        os.environ["INSIGHTFLOW_METRICS_FILE"] = str(cfg)
    else:
        os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
    ds_id = register_uploaded(spec, anchor)
    reset_engine(); refresh_schema(); set_active(ds_id)


if __name__ == "__main__":
    F.build_a(); F.build_b()
    R.main("dev", sys.argv[1] if len(sys.argv) > 1 else "M0_baseline", register)
