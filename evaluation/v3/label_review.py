"""Re-score sealed first-run records under PROPOSED label corrections.
Nothing sealed is edited; this writes a separate report that always shows the
originally reported figures next to the corrected ones.

usage: python label_review.py > results/label_review_round5.md"""
import json, pathlib, sqlite3

R = pathlib.Path(__file__).resolve().parent / "results"
D = pathlib.Path(__file__).resolve().parent / "data"

# proposed corrections: (run file, id) -> (new kind, independent expected value, justification)
def ref(db, sql):
    with sqlite3.connect(str(D / f"{db}.db")) as c:
        return c.execute(sql).fetchall()

F17_VALUES = {col: ref("library", f"SELECT COUNT(DISTINCT book_id) FROM loans WHERE {col}>='2025-01-01' AND {col}<'2026-01-01'")[0][0]
              for col in ("loan_date", "due_date", "returned_date")}
C25 = ref("university", "SELECT SUM(e.tuition_paid) FROM enrollments e JOIN students s ON s.student_id=e.student_id "
                        "WHERE s.home_state IS NULL OR s.home_state<>'California'")[0][0]
CORR = {
    ("final4_G1_first_and_only", "F17"): dict(
        new_kind="scalar", expected=F17_VALUES["loan_date"],
        verdict="defective label (underspecified question whose readings all agree)",
        why=f"3 date columns give identical distinct-book counts {F17_VALUES}; the stated policy is to answer when "
            "every reading agrees. Original label (CLARIFY) contradicted that policy."),
    ("final_F1_first_and_only", "C25"): dict(
        new_kind="scalar", expected=C25,
        verdict="defective label (question is unambiguous; label encoded then-missing capability)",
        why="'excluding California students' has one reading; independent SQL gives "
            f"{C25:.2f}. The original label expected CLARIFY only because exclusion was unsupported."),
    ("final5_H1_first_and_only", "H15"): dict(
        new_kind="clarify", expected=None,
        verdict="defective label (ambiguous wording: 'held' = ordinary verb or status value 'Held')",
        why="independent SQL: 9274.14 without the status filter vs 5731.77 with status='Held'; the readings differ, "
            "so by the stated policy a clarification is the correct response."),
    ("final5_H1_first_and_only", "M14"): dict(
        new_kind="clarify", expected=None,
        verdict="defective label (two date columns on the base table; readings differ)",
        why="independent SQL: units planned in June 2025 is 8320 by started_at and 8199 by finished_at; the question "
            "names neither, so a clarification is the correct response."),
}
FIRST_VALUE = {  # first-run system values for corrected-label questions, from the reproduced diagnosis
    ("final4_G1_first_and_only", "F17"): ("ANSWER", 9),   # diagnosis_G1_silent_errors_reproduced_at_36878e7.json
}


def score(name, corrections):
    res = json.load(open(R / f"{name}.json"))["results"]
    ans = cor = ans_ans = bad = abst = cl_need = cl_ok = 0
    for r in res:
        kind, outcome, action = r["kind"], r["outcome"], r["action"]
        c = corrections.get((name, r["id"]))
        if c:
            kind = c["new_kind"]
            if kind == "clarify":
                outcome = "correct_clarify" if action in ("CLARIFY", "ABSTAIN") else "silent_wrong"
            elif (name, r["id"]) in FIRST_VALUE:
                a, v = FIRST_VALUE[(name, r["id"])]
                outcome = "correct" if abs(float(v) - float(c["expected"])) < 1e-6 else "silent_wrong"
            else:
                outcome = "correct" if action in ("ANSWER", "WARN") and False else \
                          ("silent_wrong" if action in ("ANSWER", "WARN") else "abstained")
        if kind in ("clarify", "grain_trap"):
            cl_need += 1; cl_ok += outcome == "correct_clarify"
            bad += outcome == "silent_wrong"
        else:
            ans += 1; cor += outcome == "correct"
            ans_ans += action in ("ANSWER", "WARN")
            bad += outcome == "silent_wrong"; abst += outcome == "abstained"
    n = len(res)
    return dict(n=n, answerable=ans, correct=cor, answered=ans_ans, silent_wrong=bad,
                abstained=abst, clarify_needed=cl_need, clarify_ok=cl_ok)


print("# Label review (round 5) - proposed corrections; sealed records unchanged\n")
for key, c in CORR.items():
    print(f"- **{key[1]}** ({key[0]}): {c['verdict']}. {c['why']}")
print()
for name in ("final4_G1_first_and_only", "final_F1_first_and_only", "final5_H1_first_and_only"):
    o, k = score(name, {}), score(name, {kk: v for kk, v in CORR.items() if kk[0] == name})
    print(f"\n### {name}\n")
    print("| | answerable | correct | answered | silent wrong | abstained (answerable) | clarifications correct |")
    print("|---|---|---|---|---|---|---|")
    for lab, s in (("original label (as sealed, as first reported)", o), ("proposed corrected label", k)):
        print(f"| {lab} | {s['answerable']} | {s['correct']}/{s['answerable']} | {s['answered']}/{s['answerable']} "
              f"| {s['silent_wrong']}/{s['n']} | {s['abstained']} | {s['clarify_ok']}/{s['clarify_needed']} |")
