"""Validate the v5 provisional question set against its own fixtures.

Builds all DBs, executes every reference_sql and alt_sql, checks the kind
conventions, checks clarify readings disagree, checks trap formulations differ,
and writes reference_results.json.
"""
import collections
import json
import math
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_v5  # noqa: E402
from questions_v5 import V5  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ["direct_kpi", "breakdown", "top_n", "trend", "multi_table_join", "related_numeric_threshold",
              "fk_inference", "abbreviation", "negation_exclusion", "boolean_flag", "null_condition",
              "distinct_count", "join_fanout", "date_role_ambiguity", "period_comparison", "ratio",
              "share_of_total", "many_to_many", "anti_join", "ambiguous", "unsupported_metric"]
REQUIRED = ["id", "db", "schema_version", "question", "category", "expected_answerability", "kind",
            "metric_definition", "filters", "aggregation_grain", "join_assumptions", "reference_sql",
            "ambiguity_notes", "provenance", "adjudication_status"]


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    return a == b


def same_rows(a, b, ordered):
    if len(a) != len(b):
        return False
    if not ordered:
        a, b = sorted(a, key=lambda r: str(r[0])), sorted(b, key=lambda r: str(r[0]))
    return all(len(x) == len(y) and all(close(p, q) for p, q in zip(x, y)) for x, y in zip(a, b))


def main():
    paths = fixtures_v5.build_all()
    cons = {k: sqlite3.connect(v) for k, v in paths.items()}
    errors, results = [], {}
    ids = [q["id"] for q in V5]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids")
    for q in V5:
        qid = q["id"]
        for k in REQUIRED:
            if k not in q:
                errors.append("%s: missing key %s" % (qid, k))
        if q["category"] not in CATEGORIES:
            errors.append("%s: bad category %s" % (qid, q["category"]))
        con = cons[q["db"].split("@")[0]]
        ans, kind = q["expected_answerability"], q["kind"]
        if ans != "answerable":
            if kind != "clarify" or q["reference_sql"] is not None:
                errors.append("%s: non-answerable must be kind clarify with no SQL" % qid)
            results[qid] = None
            readings = q.get("clarify_readings")
            if readings:
                outs = [con.execute(s).fetchall() for s in readings]
                if any(same_rows(outs[i], outs[j], False) for i in range(len(outs)) for j in range(i + 1, len(outs))):
                    errors.append("%s: clarify readings do not differ: %s" % (qid, outs))
            continue
        if kind not in ("scalar", "rowset", "ordered", "empty_ok"):
            errors.append("%s: bad kind for answerable" % qid)
            continue
        try:
            ref = con.execute(q["reference_sql"]).fetchall()
            alt = con.execute(q["alt_sql"]).fetchall()
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: SQL error %s" % (qid, exc))
            continue
        results[qid] = [list(r) for r in ref]
        if kind == "scalar":
            if not (len(ref) == 1 and len(ref[0]) == 1 and isinstance(ref[0][0], (int, float))):
                errors.append("%s: scalar expects one numeric value, got %s" % (qid, ref))
        elif kind == "empty_ok":
            if not (ref == [] or ref == [(None,)]):
                errors.append("%s: empty_ok expects NULL or no rows, got %s" % (qid, ref))
        else:
            if not ref or any(len(r) != 2 for r in ref):
                errors.append("%s: expects (label, number) rows" % qid)
            labels = [r[0] for r in ref]
            if len(set(labels)) != len(labels) or any(l is None for l in labels):
                errors.append("%s: labels not unique / NULL label" % qid)
            if any(not isinstance(r[1], (int, float)) for r in ref):
                errors.append("%s: non-numeric value" % qid)
            if kind == "ordered":
                m = re.search(r"LIMIT (\d+)\s*$", q["reference_sql"])
                if not m:
                    errors.append("%s: ordered without LIMIT" % qid)
                else:
                    n = int(m.group(1))
                    ext = con.execute(q["reference_sql"][:m.start()] + "LIMIT %d" % (n + 1)).fetchall()
                    vals = [r[1] for r in ext]
                    if len(vals) > n and close(vals[n - 1], vals[n]):
                        errors.append("%s: tie at cut-off %s" % (qid, ext))
                    if len(set(vals[:n])) != len(vals[:n]):
                        errors.append("%s: tie inside top-N %s" % (qid, ext))
        if not same_rows(ref, alt, kind == "ordered"):
            errors.append("%s: reference and alt disagree\n  ref=%s\n  alt=%s" % (qid, ref, alt))
        if q.get("trap_sql"):
            trap = con.execute(q["trap_sql"]).fetchall()
            if same_rows(ref, trap, False):
                errors.append("%s: trap formulation gives the same result as reference" % qid)

    cat = collections.Counter(q["category"] for q in V5)
    ansc = collections.Counter(q["expected_answerability"] for q in V5)
    kindc = collections.Counter(q["kind"] for q in V5)
    dbc = collections.Counter(q["db"] for q in V5)
    for c in CATEGORIES:
        if cat[c] < 2:
            errors.append("category %s has fewer than 2 questions" % c)
    print("questions:", len(V5))
    print("by db:", dict(dbc))
    print("by answerability:", dict(ansc))
    print("by kind:", dict(kindc))
    print("by category:")
    for c in CATEGORIES:
        print("  %-26s %d" % (c, cat[c]))
    n_alt = sum(1 for q in V5 if q["expected_answerability"] == "answerable")
    n_read = sum(1 for q in V5 if q.get("clarify_readings"))
    n_trap = sum(1 for q in V5 if q.get("trap_sql"))
    print("answerable with ref/alt agreement checked:", n_alt)
    print("clarify items with divergent readings checked:", n_read)
    print("trap formulations checked to differ:", n_trap)
    with open(os.path.join(HERE, "reference_results.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    if errors:
        print("\nFAILED (%d problems):" % len(errors))
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("\nALL CHECKS PASSED; reference_results.json written")


if __name__ == "__main__":
    main()
