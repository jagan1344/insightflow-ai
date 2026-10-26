"""Recompute every Round 8 number quoted in the manuscript and reports from saved outputs."""
import csv, json, pathlib, sys
H = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(H / "blind")); sys.path.insert(0, str(H.parent / "eval"))
from score_v6 import summarize as s6, BORDERLINE_IDS
import score_v5
fails = []
def chk(n, got, exp):
    ok = got == exp; print(("OK  " if ok else "FAIL"), n, got, "" if ok else f"(claimed {exp})"); ok or fails.append(n)
a = json.load(open(H / "blind/results/v6_A0_first_run.json"))["records"]; s = s6([dict(r) for r in a])
chk("v6 n/answerable", (s["n"], s["answerable"]), (106, 73)); chk("v6 correct", s["correct"], 5)
chk("v6 answered", s["answered_answerable"], 11); chk("v6 wrong", s["silent_wrong_total"], 10)
chk("v6 wrong split", (s["silent_wrong_answerable"], s["answered_clarify_items"]), (6, 4))
chk("v6 refusals", (s["correct_clarify"], s["clarify_or_unsupported"]), (29, 33))
chk("v6 CI correct", tuple(s["correct_ci95"]), (0.03, 0.151)); chk("v6 CI wrong", tuple(s["silent_wrong_ci95"]), (0.052, 0.165))
chk("v6 latency", (round(s["latency_ms_p50"]), round(s["latency_ms_p95"])), (319, 1741))
b = s6([dict(r) for r in a if r["id"] not in BORDERLINE_IDS])
chk("v6 borderline", (b["correct"], b["answerable"], b["silent_wrong_total"], b["n"]), (5, 58, 8, 82))
R = {r["config"]: r for r in csv.DictReader(open(H / "blind/v6_ablation_results.csv"))}
chk("v6 A7", (int(R["A7"]["correct"]), int(R["A7"]["wrong"])), (9, 35))
chk("v6 B5", int(R["B5"]["wrong"]), 12); chk("v6 B1", int(R["B1"]["wrong"]), 31); chk("v6 B4", int(R["B4"]["wrong"]), 33)
c = json.load(open(H / "blind/v6_confidence.json"))
chk("v6 auroc", (c["A0"]["auroc"], c["A7"]["auroc"]), (0.45, 0.479)); chk("v6 ece", c["A0"]["ece_5bin"], 0.639)
chk("v6 min conf / >=0.9 wrong", (c["A0"]["min_conf_answered"], c["A0"]["wrong_ge_0_9"]), (0.835, 9))
p = json.load(open(H / "results/v5_A0_posthoc_dev_final_at_da925ad.json"))["records"]; t = score_v5.summarize([dict(r) for r in p])
chk("v5 posthoc", (t["correct"], t["answered_answerable"], t["silent_wrong_total"], t["correct_clarify"]), (63, 64, 2, 30))
chk("v5 posthoc latency", (round(t["latency_ms_p50"]), round(t["latency_ms_p95"])), (214, 796))
q = json.load(open(H / "results/v5_A7_posthoc_dev_ablation_da925ad.json"))["records"]; u = score_v5.summarize([dict(r) for r in q])
chk("v5 posthoc A7", (u["correct"], u["silent_wrong_total"]), (64, 9))
rc = json.load(open(H / "stage_frozen.json"))
import collections
cc = collections.Counter((o["action"] in ("ANSWER", "WARN"), o["sql_matches_reference"]) for o in rc)
chk("root cause split", (cc[(False, None)], cc[(False, False)], cc[(False, True)]), (22, 29, 6))
print("FAILURES:", fails)
