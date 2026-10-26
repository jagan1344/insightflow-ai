"""Validate the v6 blind question set against freshly built fixtures.

Checks:
  * schema of every question dict (required keys, allowed values, unique ids)
  * every answerable item: reference_sql and alt_sql execute and agree
  * kind conventions: scalar = 1x1 numeric; rowset/ordered = (label, number) rows;
    ordered = strictly decreasing/increasing values in the shown rows and no tie at
    the cut-off (checked by re-running the query without its LIMIT);
    empty_ok = NULL scalar or no rows
  * every clarify item: reference_sql is None and >= 2 clarify_readings that all
    execute and are pairwise different
  * every unsupported item: reference_sql is None
Writes reference_results.json ({id: rows, null for clarify/unsupported}).
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixtures_v6  # noqa: E402
from questions_v6 import V6  # noqa: E402

CATEGORIES = {"direct_kpi", "breakdown", "top_n", "trend", "multi_table_join", "related_numeric_threshold",
              "fk_inference", "abbreviation", "negation_exclusion", "boolean_flag", "null_condition",
              "distinct_count", "join_fanout", "date_role_ambiguity", "period_comparison", "ratio",
              "share_of_total", "many_to_many", "anti_join", "ambiguous", "unsupported_metric"}
REQUIRED = ["id", "db", "schema_version", "question", "category", "expected_answerability", "kind",
            "metric_definition", "filters", "aggregation_grain", "join_assumptions", "reference_sql", "alt_sql",
            "ambiguity_notes", "provenance", "adjudication_status"]
ANCHORS = {"food": "orders", "lease": "leases", "telecom": "monthly_bills", "warehouse": "inv_moves"}
PREFIX = {"food": "FD", "lease": "LS", "telecom": "TC", "warehouse": "WH"}


def norm_val(v):
    if isinstance(v, float):
        return round(v, 6)
    return v


def norm(rows, ordered):
    rows = [tuple(norm_val(v) for v in r) for r in rows]
    if not ordered:
        rows = sorted(rows, key=lambda r: tuple((x is None, str(type(x)), x if x is not None else 0) for x in r))
    return rows


def run(con, sql):
    return [tuple(r) for r in con.execute(sql).fetchall()]


def main():
    fixtures_v6.build_all()
    cons = {n: sqlite3.connect(fixtures_v6.db_path(n)) for n in ANCHORS}
    errors, results = [], {}
    pitfall_live = 0
    ids = Counter(q["id"] for q in V6)
    for i, c in ids.items():
        if c > 1:
            errors.append(f"duplicate id {i}")

    for q in V6:
        qid = q["id"]
        err = lambda m: errors.append(f"{qid}: {m}")  # noqa: E731
        for k in REQUIRED:
            if k not in q:
                err(f"missing key {k}")
        db, _, anchor = q["db"].partition("@")
        if db not in ANCHORS or ANCHORS[db] != anchor:
            err(f"bad db {q['db']}")
            continue
        if not qid.startswith(PREFIX[db]):
            err("id prefix does not match db")
        if q["category"] not in CATEGORIES:
            err(f"bad category {q['category']}")
        ans, kind = q["expected_answerability"], q["kind"]
        con = cons[db]
        if ans == "answerable":
            if kind not in ("scalar", "rowset", "ordered", "empty_ok"):
                err(f"answerable item with kind {kind}")
            if not q["reference_sql"] or not q["alt_sql"]:
                err("answerable item lacks reference_sql or alt_sql")
                continue
            if q["reference_sql"].strip() == q["alt_sql"].strip():
                err("alt_sql identical to reference_sql")
            try:
                ref = run(con, q["reference_sql"])
                alt = run(con, q["alt_sql"])
            except sqlite3.Error as e:
                err(f"SQL error: {e}")
                continue
            if norm(ref, kind == "ordered") != norm(alt, kind == "ordered"):
                err(f"reference/alt disagree:\n   ref={norm(ref, kind == 'ordered')}\n   alt={norm(alt, kind == 'ordered')}")
            if kind == "scalar":
                if len(ref) != 1 or len(ref[0]) != 1 or not isinstance(ref[0][0], (int, float)):
                    err(f"scalar must be one numeric value, got {ref}")
            elif kind in ("rowset", "ordered"):
                if not ref:
                    err("rowset/ordered returned no rows")
                for r in ref:
                    if len(r) != 2 or not isinstance(r[1], (int, float)) or not (r[0] is None or isinstance(r[0], str)):
                        err(f"row is not (label, number): {r}")
                        break
                labels = [r[0] for r in ref]
                if len(set(labels)) != len(labels):
                    err("duplicate labels in rowset")
                if kind == "ordered":
                    m = re.search(r"\s+LIMIT\s+(\d+)\s*$", q["reference_sql"], re.I)
                    if not m:
                        err("ordered item needs a trailing LIMIT n")
                    else:
                        n = int(m.group(1))
                        full = run(con, q["reference_sql"][:m.start()])
                        vals = [round(r[1], 6) for r in full[:n + 1]]
                        if len(set(vals)) != len(vals):
                            err(f"tie within top {n} or at cut-off: {vals}")
                        if len(ref) != n:
                            err(f"ordered returned {len(ref)} rows, expected {n}")
            elif kind == "empty_ok":
                if not (ref == [] or (len(ref) == 1 and all(v is None for v in ref[0]))):
                    err(f"empty_ok must return NULL or no rows, got {ref}")
            if "pitfall_sql" in q:
                try:
                    pit = run(con, q["pitfall_sql"]["sql"])
                    if norm(pit, False) == norm(ref, False):
                        err(f"pitfall '{q['pitfall_sql']['description']}' gives the same result as the reference")
                    else:
                        pitfall_live += 1
                except sqlite3.Error as e:
                    err(f"pitfall SQL error: {e}")
            results[qid] = [list(r) for r in ref]
        elif ans == "clarify":
            if kind != "clarify" or q["reference_sql"] is not None:
                err("clarify item must have kind clarify and reference_sql None")
            readings = q.get("clarify_readings") or {}
            if len(readings) < 2:
                err("clarify item needs >= 2 clarify_readings")
            outs = {}
            for name, sql in readings.items():
                try:
                    outs[name] = norm(run(con, sql), False)
                except sqlite3.Error as e:
                    err(f"reading {name} SQL error: {e}")
            names = list(outs)
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    if outs[names[a]] == outs[names[b]]:
                        err(f"readings {names[a]} and {names[b]} give identical results {outs[names[a]]}")
            results[qid] = None
        elif ans == "unsupported":
            if kind != "clarify" or q["reference_sql"] is not None:
                err("unsupported item must have kind clarify and reference_sql None")
            results[qid] = None
        else:
            err(f"bad answerability {ans}")

    cat = Counter(q["category"] for q in V6)
    for c in CATEGORIES:
        if cat[c] < 2:
            errors.append(f"category {c} covered only {cat[c]} times")

    ansc = Counter(q["expected_answerability"] for q in V6)
    kindc = Counter(q["kind"] for q in V6)
    dbc = Counter(q["db"] for q in V6)
    print(f"questions: {len(V6)}")
    print(f"pitfall readings checked (all differ from reference): {pitfall_live}")
    print("by db:", dict(dbc))
    print("by answerability:", {k: f"{v} ({100.0 * v / len(V6):.1f}%)" for k, v in ansc.items()})
    print("by kind:", dict(kindc))
    print("by category:")
    for c in sorted(CATEGORIES):
        sub = Counter(q["expected_answerability"] for q in V6 if q["category"] == c)
        print(f"  {c:28s} {cat[c]:3d}  {dict(sub)}")

    with open(os.path.join(HERE, "reference_results.json"), "w") as f:
        json.dump(results, f, indent=1, sort_keys=True)

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
