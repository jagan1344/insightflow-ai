"""Phase-12 audit: recompute every number quoted in the manuscript and reports from saved outputs."""
import csv, json, sys, pathlib
H = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(H / "eval"))
from score_v5 import summarize, BORDERLINE_IDS
E = H / "eval" / "results"
fails = []
def chk(name, got, exp):
    ok = got == exp
    print(("OK  " if ok else "FAIL"), name, got, "" if ok else f"(manuscript says {exp})")
    ok or fails.append(name)
a0 = json.load(open(E / "v5_A0_first_run.json"))["records"]
s = summarize([dict(r) for r in a0])
chk("n", s["n"], 105); chk("answerable", s["answerable"], 74); chk("correct", s["correct"], 14)
chk("answered", s["answered_answerable"], 17); chk("wrong total", s["silent_wrong_total"], 7)
chk("correct CI", tuple(s["correct_ci95"]), (0.116, 0.293)); chk("wrong CI", tuple(s["silent_wrong_ci95"]), (0.033, 0.131))
chk("acc answered CI", tuple(s["accuracy_when_answered_ci95"]), (0.59, 0.938))
chk("clarify refused", s["clarify_items_refused"], "15/19"); chk("unsupported refused", s["unsupported_items_refused"], "12/12")
chk("unnecessary", s["unnecessary_clarify"], 57); chk("p50", round(s["latency_ms_p50"]), 54); chk("p95", round(s["latency_ms_p95"]), 660)
b = summarize([dict(r) for r in a0 if r["id"] not in BORDERLINE_IDS])
chk("borderline correct", (b["correct"], b["answerable"]), (14, 65)); chk("borderline wrong", (b["silent_wrong_total"], b["n"]), (5, 85))
R = {r["config"]: r for r in csv.DictReader(open(H / "03_ablation_results.csv"))}
exp = {"A0": (14, 17, 7, 57), "A1": (14, 18, 8, 56), "A2": (14, 17, 7, 57), "A3": (14, 17, 7, 57), "A4": (14, 17, 7, 57),
       "A5": (17, 38, 28, 36), "A6": (14, 17, 7, 57), "A7": (17, 41, 32, 33), "B1": (17, 38, 28, 36), "B5": (14, 18, 8, 56)}
for k, v in exp.items():
    r = R[k]; chk(f"ablation {k}", (int(r["correct"]), int(r["answered_answerable"]), int(r["wrong_answers"]), int(r["unnecessary_clarify"])), v)
t = json.load(open(E / "ablation_transitions.json"))
chk("A5 wrong from refusals", sum(v for k, v in t["A5"]["counts"].items() if k.endswith(":wrong")), 21)
chk("B5 prevented", sum(v for k, v in t["B5"]["counts"].items() if k.startswith("A7:wrong")), 24)
chk("B1 prevented", sum(v for k, v in t["B1"]["counts"].items() if k.startswith("A7:wrong")), 4)
chk("A1 marginal", sum(v for k, v in t["A1"]["counts"].items() if k.endswith(":wrong")), 1)
c = json.load(open(E / "confidence_analysis.json"))
chk("min conf answered A0", min(c["A0"]["conf_correct"]["min"], c["A0"]["conf_wrong"]["min"]), 0.979)
chk("min conf answered A7", min(c["A7"]["conf_correct"]["min"], c["A7"]["conf_wrong"]["min"]), 0.979)
chk("ECE", (c["A0"]["ece_5bin"], c["A7"]["ece_5bin"]), (0.319, 0.637)); chk("AUROC", (c["A0"]["auroc_correct_vs_wrong"], c["A7"]["auroc_correct_vs_wrong"]), (0.673, 0.685))
V3 = H.parent / "evaluation" / "v3" / "results"
k1 = json.load(open(V3 / "final6_K1_first_and_only.json"))["summary"]; chk("K1", (k1["correct"], k1["answerable"], k1["silent_wrong"]), (42, 54, 2))
k3 = json.load(open(V3 / "final6_K3_posthoc_not_heldout.json"))["summary"]; chk("K3", (k3["correct"], k3["silent_wrong"]), (49, 0))
p1 = json.load(open(V3 / "final6_P1_posthoc_not_heldout.json"))["summary"]; chk("P1", (p1["correct"], p1["silent_wrong"]), (54, 0))
tot = [0, 0, 0, 0]
for n in ["final_F1_first_and_only", "final4_G1_first_and_only", "final5_H1_first_and_only", "dev4_R0_first", "adversarial_A0_first"]:
    x = json.load(open(V3 / f"{n}.json"))["summary"]; tot = [tot[0] + x["correct"], tot[1] + x["answerable"], tot[2] + x["silent_wrong"], tot[3] + x["n"]]
chk("earlier first runs", tuple(tot), (116, 159, 17, 206))
print("FAILURES:", fails)
