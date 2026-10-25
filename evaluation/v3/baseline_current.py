"""M0 baseline: what the CURRENT (single-table) system does on the
multi-table fixtures. The only thing it can be given is one table, so we
register each schema's fact table as an uploaded dataset (copy of the
fixture DB so registry metadata never touches the fixtures)."""
import pathlib, shutil, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "backend"))
import fixtures as F, run_eval as R

TMP = pathlib.Path(tempfile.mkdtemp(prefix="v3base_"))


def register(db):
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import register_relational as register_uploaded, set_active, bootstrap
    from insightflow.knowledge.schema_agent import refresh_schema
    dst = TMP / f"{db}.db"
    shutil.copy(F.DATA / f"{db}.db", dst)
    settings.database_url = f"sqlite:///{dst}"
    reset_engine(); bootstrap()
    ds_id = register_uploaded(db, R.FACT[db])
    reset_engine(); refresh_schema(); set_active(ds_id)


if __name__ == "__main__":
    F.build_a(); F.build_b()
    R.main("dev", sys.argv[1] if len(sys.argv) > 1 else "M0_baseline", register)
