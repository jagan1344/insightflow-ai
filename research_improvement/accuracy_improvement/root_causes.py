"""Per-question root-cause report for the 57 unanswered answerable v5 questions and the 3 wrong values
(frozen 38b60d1). Classification is manual, from trace_frozen.jsonl + stage_frozen.json; the script merges it
with the machine-derived fields and writes root_causes.json / root_causes.md."""
import json, collections
# id: (earliest stage where the correct reading was lost, class, note, label_dispute)
C = {
 "HO01": ("planner: filters", "Other: inclusion phrase read as a filter", "'cancelled ones included' compiled to is_cancelled = 1; veto caught it", ""),
 "HO02": ("planner: measure binding", "Column abbreviation mismatch", "'room nights' not linked to nts_cnt", ""),
 "HO03": ("coverage audit", "Excessively strict coverage audit", "SQL correct; 'break' (from 'break down') flagged", ""),
 "HO05": ("planner: dimension binding", "Wrong measure selection", "'type of room' bound to booking_addons.addon_type instead of rooms.room_type (wrong dimension)", ""),
 "HO06": ("planner: measure binding", "Column abbreviation mismatch", "'room nights' not linked to nts_cnt", ""),
 "HO07": ("plan validation", "Excessively strict coverage audit", "SQL correct; 'check' from 'check-in' reported as unbound dimension", ""),
 "HO09": ("planner: measure binding", "Missing business synonym", "'reservations' not recognised as the bookings rows", ""),
 "HO11": ("planner: measure binding", "Missing business synonym", "'value of bookings' -> amt and 'payment didn't go through' -> payment_ok = 0 not recognised", ""),
 "HO12": ("planner: filters", "Missing business synonym", "'online travel agencies' not linked to value 'OTA'; exclusion lost", ""),
 "HO13": ("planner: filters", "Other: null-state phrasing", "'don't have a check-in date yet' treated as negative existence instead of checkin_dt IS NULL", ""),
 "HO14": ("planner: measure binding", "Missing business synonym", "'different guests' not read as COUNT(DISTINCT guest_id)", ""),
 "HO15": ("planner: filters", "Unit terminology mismatch", "'square metres' not linked to rooms.sq_m; threshold dropped", ""),
 "HO16": ("coverage audit", "Excessively strict coverage audit", "SQL correct (EXISTS); 'least' from 'at least one' flagged", ""),
 "HO18": ("planner: intent", "Unsupported query capability", "percentage of rows meeting a condition not implemented", ""),
 "HO19": ("planner: intent", "Unsupported query capability", "share of a total for one value not implemented", ""),
 "HO20": ("planner: intent", "Unsupported query capability", "difference between two explicit periods not implemented", ""),
 "HO25": ("planner: measure binding", "Missing business synonym", "'brought in' (revenue) not linked to amt", ""),
 "IN01": ("planner: measure binding", "Column abbreviation mismatch", "'amount claimed' not linked to claim_amt (word order / stem)", ""),
 "IN02": ("planner: measure binding", "Column abbreviation mismatch", "'claimed amount' not linked to claim_amt; 'insurance product' read as a dimension word", ""),
 "IN04": ("planner: measure binding", "Wrong measure selection", "'claimed amount' unbound -> fallback to COUNT(*) (wrong answer)", ""),
 "IN06": ("planner: filters", "Other: number parsing", "'1,000' parsed as 1", ""),
 "IN07": ("planner: intent", "Unsupported query capability", "average date difference not implemented", ""),
 "IN08": ("planner: intent", "Unsupported query capability", "measure of a parent entity (policies) filtered by existence of children; anchor is claims", ""),
 "IN10": ("planner: filters", "Missing business synonym", "'incomplete paperwork' -> docs_ok = 0 not recognised", ""),
 "IN11": ("planner: filters", "Other: null-state phrasing", "'haven't been assigned to an adjuster' -> adj_id IS NULL not recognised", ""),
 "IN12": ("planner: filters", "Other: null-state phrasing", "'cause ... wasn't recorded' -> cause IS NULL not recognised", ""),
 "IN13": ("planner: measure binding", "Column abbreviation mismatch", "'amount claimed' not linked to claim_amt", ""),
 "IN14": ("planner: measure binding", "Wrong measure selection", "noun 'claim' in 'filed a claim' added SUM(claim_amt) as a second measure (wrong answer)", ""),
 "IN15": ("plan validation", "Excessively strict coverage audit", "SQL correct; function word 'for' reported as unbound dimension", ""),
 "IN17": ("planner: intent", "Unsupported query capability", "difference between two explicit periods not implemented", ""),
 "IN18": ("planner: intent", "Unsupported query capability", "percentage of rows meeting a condition not implemented", ""),
 "IN20": ("planner: intent", "Unsupported query capability", "share of a total for one value not implemented", ""),
 "IN21": ("planner: measure binding", "Column abbreviation mismatch", "'amount claimed' not linked to claim_amt", ""),
 "IN26": ("planner: measure binding", "Unsupported query capability", "measure on a one-to-many child table (claim_payments.pmt_amt)", ""),
 "EN01": ("planner: measure binding", "Unit terminology mismatch", "'kilowatt-hours' not linked to kwh", ""),
 "EN02": ("planner: aggregation", "Wrong aggregation operator", "'average bill amount' compiled to SUM; wording audit caught it", ""),
 "EN04": ("coverage audit", "Excessively strict coverage audit", "SQL correct; 'break' flagged", ""),
 "EN05": ("plan validation", "Excessively strict coverage audit", "SQL correct; 'total' reported as unbound dimension", ""),
 "EN08": ("planner: filters", "Other: null-state phrasing", "'installation date is unknown' on a related table not recognised", ""),
 "EN09": ("planner: filters", "Incorrect wording audit", "'Leaving out' not an exclusion cue (filter kept Commercial) and 'how many kWh' counted rows; veto caught it", ""),
 "EN10": ("planner: intent", "Other: intent misclassified", "'priced above 0.20 per kWh' read as a ratio request; threshold on tariffs.rate_per_kwh lost", ""),
 "EN12": ("planner: intent", "Ambiguous metric definition", "price per kWh = SUM(amt)/SUM(kwh) per author; flagged borderline by the author", "borderline"),
 "EN13": ("planner: intent", "Unsupported query capability", "share of a total for one value not implemented", ""),
 "EN14": ("planner: intent", "Unsupported query capability", "difference between two explicit periods not implemented", ""),
 "EN17": ("planner: filters", "Missing schema relationship", "value in a child of a parent table (customer_programs under customers) not reachable", ""),
 "EN18": ("planner: measure binding", "Missing business synonym", "verb 'bill' ('what did we bill') not linked to bills.amt", ""),
 "EN24": ("planner: filters", "Missing business synonym", "'working meters' -> meter_ok = 1 not recognised", ""),
 "RI02": ("planner: measure binding", "Unsupported query capability", "unit conversion minutes -> hours", ""),
 "RI04": ("planner: measure binding", "Column abbreviation mismatch", "plural 'fares' not linked to fare_amt -> COUNT(*); veto caught it", ""),
 "RI05": ("planner: dimension binding", "Missing business synonym", "'drop-off zones' not linked to role dropoff_zone_cd", ""),
 "RI08": ("planner: measure binding", "Column abbreviation mismatch", "plural 'fares' not linked to fare_amt -> COUNT(*); veto caught it", ""),
 "RI10": ("planner: filters", "Column abbreviation mismatch", "'payment method' bound to payment_ok instead of pay_method", ""),
 "RI11": ("planner: filters", "Other: null-state phrasing", "'left blank' -> tip_amt IS NULL not recognised; SUM computed instead", ""),
 "RI12": ("planner: filters", "Other: negation of a value filter", "'not paid in cash' kept only cash trips (wrong answer)", "borderline (NULL methods counted as not cash)"),
 "RI14": ("planner: filters", "Other: comparator phrasing", "'rated 4.8 or higher' not parsed; 'drivers' read as grouping", ""),
 "RI15": ("planner: intent", "Unsupported query capability", "explicit ratio 'total fare divided by total distance' not implemented", ""),
 "RI16": ("planner: intent", "Unsupported query capability", "share of a total for one value; role phrase 'started at' unresolved", ""),
 "RI17": ("planner: intent", "Unsupported query capability", "difference between two explicit periods not implemented", ""),
 "RI20": ("planner: filters", "Missing schema relationship", "value in a child of a parent table (driver_languages under drivers) not reachable", ""),
 "RI23": ("planner: dimension binding", "Missing business synonym", "role phrase 'picked up in' not linked to pickup_zone_cd", ""),
}
st = {o["id"]: o for o in json.load(open("stage_frozen.json"))}
tr = {json.loads(l)["id"]: json.loads(l) for l in open("trace_frozen.jsonl")}
rep = []
for i, (stage, cls, note, dispute) in C.items():
    t = tr[i]; s = st[i]
    rep.append(dict(id=i, question=t["q"], category=t["cat"], reference_sql=t["ref"], action=t["action"],
                    generated_sql=t["sql"], sql_matches_reference=s["sql_matches_reference"],
                    plan=t["plan"], final_reason=t["reason"], semantic_findings=t["findings"],
                    earliest_lost_stage=stage, failure_class=cls, note=note, label_dispute=dispute))
json.dump(rep, open("root_causes.json", "w"), indent=1, default=str)
cnt = collections.Counter(r["failure_class"] for r in rep)
with open("root_causes.md", "w") as f:
    f.write("# Root causes: 57 unanswered answerable + 3 wrong values (v5, frozen 38b60d1)\n\n")
    f.write("Machine-derived split (`stage_frozen.json`): of 57 refusals, 22 produced no SQL, 29 produced SQL that "
            "does NOT match the reference (the veto was right), 6 produced matching SQL (the veto was over-strict).\n\n")
    f.write("| class | count |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in cnt.most_common()))
    f.write("\n| id | stage | class | note |\n|---|---|---|---|\n")
    for r in rep:
        f.write(f"| {r['id']} | {r['earliest_lost_stage']} | {r['failure_class']} | {r['note']}{' (label: ' + r['label_dispute'] + ')' if r['label_dispute'] else ''} |\n")
print(len(rep)); [print(v, k) for k, v in cnt.most_common()]
