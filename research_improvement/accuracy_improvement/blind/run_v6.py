"""Run the frozen build (da925ad, backend tree d760e82) on the v6 blind set.
usage: python run_v6.py <config A0..A7|B1..B6> <label>. Refuses any other backend tree; never overwrites."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[3]
V6 = ROOT / "evaluation" / "v6_blind"
OUT = pathlib.Path(__file__).resolve().parent / "results"
FROZEN_TREE = "d760e8298357686f3139449e0ff8e237795c21b9"
ALL = ["semantic", "confidence_gate", "result_consistency", "plan_fidelity", "mention_coverage", "answer_verifier"]
CONFIGS = {"A0": "", "A1": "semantic", "A2": "confidence_gate", "A3": "result_consistency", "A4": "plan_fidelity",
           "A5": "mention_coverage", "A6": "answer_verifier", "A7": ",".join(ALL)}
for i, keep in enumerate(ALL, 1):
    CONFIGS[f"B{i}"] = ",".join(c for c in ALL if c != keep)


def check_frozen():
    tree = subprocess.check_output(["git", "rev-parse", "HEAD:backend"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, text=True).strip()
    if tree != FROZEN_TREE or dirty:
        sys.exit(f"backend is not the frozen tree ({tree}, dirty={bool(dirty)}); refusing to run")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main(config, label):
    head = check_frozen()
    os.environ["INSIGHTFLOW_ABLATE"] = CONFIGS[config]
    OUT.mkdir(exist_ok=True)
    out = OUT / f"v6_{config}_{label}.json"
    if out.exists():
        sys.exit(f"{out} exists; never overwritten")
    sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(V6))
    import fixtures_v6 as FX
    from questions_v6 import V6 as QS
    FX.build_all()
    ref = json.load(open(V6 / "reference_results.json"))
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import register_relational, set_active, bootstrap
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.orchestrator import Orchestrator
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="v6run_")); data = V6 / "data"
    recs, cur = [], None
    for q in QS:
        if q["db"] != cur:
            cur = q["db"]; name, anchor = cur.split("@")
            dst = tmp / f"{name}__{anchor}.db"; shutil.copy(data / f"{name}.db", dst)
            settings.database_url = f"sqlite:///{dst}"; os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
            reset_engine(); bootstrap(); ds_id = register_relational(cur, anchor); reset_engine(); refresh_schema(); set_active(ds_id)
        t0 = time.perf_counter()
        try:
            r = Orchestrator().ask(q["question"]); err = None
            action, conf = r.decision.action, float(r.confidence.score or 0)
            rows = [list(x) for x in r.result.rows] if (r.result and r.result.ok) else []
            sql, reason, findings = r.sql or "", r.decision.reason, (r.diagnostics or {}).get("semantic_findings")
            signals = {k: round(float(v), 4) for k, v in (r.confidence.signals or {}).items()}
            notes = list(r.notes or [])
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            action, conf, rows, sql, reason, findings, signals, notes = "ERROR", 0.0, [], "", err, None, {}, []
        ms = round((time.perf_counter() - t0) * 1000, 1)
        recs.append(dict(id=q["id"], db=q["db"], category=q["category"], answerability=q["expected_answerability"],
                         kind=q["kind"], question=q["question"], action=action, confidence=round(conf, 4), sql=sql,
                         rows=rows[:500], n_rows=len(rows), expected=ref.get(q["id"]), reason=reason,
                         semantic_findings=findings, signals=signals, notes=notes[:40], latency_ms=ms, error=err))
    json.dump(dict(config=config, ablate=CONFIGS[config], label=label, head=head, frozen_tree=FROZEN_TREE,
                   n=len(recs), records=recs), open(out, "w"), indent=1, default=str)
    print(f"wrote {out} ({len(recs)} records)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
