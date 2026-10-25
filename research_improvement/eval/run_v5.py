"""Run the frozen InsightFlow pipeline on the v5 provisional set.

usage: python run_v5.py <config> <label>
  config: A0 (full) | A1..A7 (ablations, see CONFIGS)
Refuses to run unless backend/ equals the frozen tree. Never overwrites an
existing output file. Raw outputs are written before any aggregate is computed."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
V5 = ROOT / "evaluation" / "v5_provisional"
OUT = pathlib.Path(__file__).resolve().parent / "results"
FROZEN_TREE = "00db6e20d39f69a6181577f764abaffd27cf08e1"
CONFIGS = {
    "A0": "",
    "A1": "semantic",
    "A2": "confidence_gate",
    "A3": "result_consistency",
    "A4": "plan_fidelity",
    "A5": "mention_coverage",
    "A6": "answer_verifier",
    "A7": "semantic,confidence_gate,result_consistency,plan_fidelity,mention_coverage,answer_verifier",
}


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
    out = OUT / f"v5_{config}_{label}.json"
    if out.exists():
        sys.exit(f"{out} exists; never overwritten")
    sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(V5))
    import fixtures_v5 as FX
    from questions_v5 import V5 as QS
    FX.build_all()
    ref = json.load(open(V5 / "reference_results.json"))
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import register_relational, set_active, bootstrap
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.orchestrator import Orchestrator
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="v5run_"))
    data = pathlib.Path(FX.build_hotel()).parent
    recs, cur = [], None
    for q in QS:
        if q["db"] != cur:
            cur = q["db"]
            name, anchor = cur.split("@")
            dst = tmp / f"{name}__{anchor}.db"
            shutil.copy(data / f"{name}.db", dst)
            settings.database_url = f"sqlite:///{dst}"
            os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
            reset_engine(); bootstrap()
            ds_id = register_relational(cur, anchor)
            reset_engine(); refresh_schema(); set_active(ds_id)
        t0 = time.perf_counter()
        try:
            r = Orchestrator().ask(q["question"])
            err = None
            action, conf = r.decision.action, float(r.confidence.score or 0)
            rows = [list(x) for x in r.result.rows] if (r.result and r.result.ok) else []
            sql, reason = r.sql or "", r.decision.reason
            findings = r.diagnostics.get("semantic_findings")
            failure = str(getattr(r, "failure_category", ""))
            signals = {k: round(float(v), 4) for k, v in (r.confidence.signals or {}).items()}
        except Exception as e:  # recorded, never hidden
            err = f"{type(e).__name__}: {e}"
            action, conf, rows, sql, reason, findings, failure, signals = "ERROR", 0.0, [], "", err, None, "exception", {}
        ms = round((time.perf_counter() - t0) * 1000, 1)
        recs.append(dict(id=q["id"], db=q["db"], category=q["category"], answerability=q["expected_answerability"],
                         kind=q["kind"], question=q["question"], action=action, confidence=round(conf, 4),
                         sql=sql, rows=rows[:500], n_rows=len(rows), expected=ref.get(q["id"]),
                         reason=reason, semantic_findings=findings, failure_category=failure,
                         signals=signals, latency_ms=ms, error=err))
    json.dump(dict(config=config, ablate=CONFIGS[config], label=label, head=head, frozen_tree=FROZEN_TREE,
                   n=len(recs), records=recs), open(out, "w"), indent=1, default=str)
    print(f"wrote {out} ({len(recs)} records)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
