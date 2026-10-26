# v6 blind evaluation set: authoring notes

Schema version `v6.0`. 106 questions over 4 new SQLite databases.

## Provenance

An AI agent (Claude) generated this set in one session. The agent was told not to read the system under test or any earlier evaluation material, and it did not: it opened no files under `backend/`, `web/`, `docs/`, `paper/`, `paper_evidence/`, `research_improvement/` or `evaluation/v2|v3|v5_provisional`, ran no git history commands and executed no InsightFlow code. The only inputs were the task brief, which described the answer format, the category list and the conventions, plus the agent's own domain knowledge. Every question, schema and reference answer was written from scratch. No question was added, dropped or reworded because of how any system might perform; no system was run. Nobody has adjudicated the set (`adjudication_status = "not human-adjudicated"`). The references are one careful analyst's reading, checked for internal consistency by `validate_v6.py`. They have not been checked by a second person.

## Files

| file | purpose |
|---|---|
| `fixtures_v6.py` | `build_food()`, `build_lease()`, `build_telecom()`, `build_warehouse()`, `build_all()` → `data/<name>.db` (fixed seeds 60601-60604, deterministic; rebuilding gives byte-identical files) |
| `questions_v6.py` | `V6` (list of 106 dicts), plus `PITFALLS` (23 deliberately wrong formulations attached as `pitfall_sql`) |
| `validate_v6.py` | rebuilds DBs, runs every SQL, checks conventions, writes `reference_results.json` |
| `reference_results.json` | `{id: rows}`; `null` for clarify/unsupported items |

## Schemas

### food.db, anchor `food@orders` (1,200 rows)
- `orders`: order_ts, dlv_ts (**two dates**; NULL dlv_ts for cancelled orders; 8 late-night month-end orders are delivered in the next month), subtotal_amt, dlv_fee, tip_amt (NULL and 0 both occur), disc_amt, order_status, `is_late` (positive flag), `delivered_ok` (normal-condition flag), promo_cd (mostly NULL; `SAVE10`, `FREEDEL`, `BOGO`), cust_rating (nullable), channel (`APP`/`WEB`/`PHONE`).
- `restaurants` (declared FK restaurant_id): cuisine has NULLs and `BBQ`; names include `Mama's Kitchen`, `Fish & Chips Co.`, `Taco Loco (Downtown)`; numeric avg_prep_min (one exactly 15.0), commission_pct. `Closed Corner Cafe` has **zero orders**.
- `couriers` (**undeclared** FK courier_id; NULL for 51 cancelled orders): vehicle_cd `BIKE`/`CAR`/`SCTR`/NULL, rating.
- `customers` (declared FK cust_id): loyalty_tier with NULLs; 10 customers never order.
- `order_items`: **one-to-many child** (2,801 lines; 92 orders have 2+ drink lines, which creates the fan-out risk).

### lease.db, anchor `lease@leases` (617 rows)
- `leases`: signed_dt, start_dt, end_dt (**three dates**; end_dt/term_mos NULL = month-to-month), monthly_rent, security_dep, concession_amt (NULL, 0 and positive), lease_status, is_renewal, pets_ok, `in_good_standing` (normal-condition flag).
- `units` (declared FK): building names `St. Mary's Lofts`, `Oak & Elm Residences`, `Harbor View (North)`; unit_type codes `STUDIO`/`1BR`/`2BR`/`3BR`/`TH`; numeric sq_ft (one exactly 900), mkt_rent_amt. Unit `Cedar Ridge PH1` has **zero leases**.
- `tenants` (declared FK): credit_score / annual_income nullable.
- `staff`: **role-playing**, referenced by two undeclared FKs `leasing_agent_id` and `prop_mgr_id`. Three staff members act in both roles. `Owen Pike` has zero leases in either role.
- `rent_payments`: **one-to-many child** (1,231 rows, 2024-07 onward), due_dt and paid_dt (two dates), amt_paid nullable, `is_late`, late_fee.

### telecom.db, anchor `telecom@monthly_bills` (1,255 rows)
- `monthly_bills`: bill_period ('YYYY-MM'), stmt_dt, due_dt, paid_dt (**four date-like columns**), `mrc_amt`, `ovg_amt`, `roam_amt` (NULL and 0), tax_amt, data_mb, voice_min, sms_cnt, `is_disputed` (positive), `cap_ok` (normal-condition).
- `subscribers` (**undeclared** FK sub_id): region has NULLs, acct_type `POSTPAID`/`PREPAID`/`BUSINESS`, credit_class nullable, churn_dt nullable.
- `plans` (**undeclared text** FK plan_cd, e.g. `UNL-MAX`): data_cap_gb (NULL = unlimited; Basic 5GB exactly 5), list_mrc. `Legacy Talk & Text` and `Family Share (4 lines)` give special-character names; Legacy has **zero bills**.
- `bill_adjustments`: **one-to-many child** (negative credit amounts, reason_cd `OUTAGE`/`GOODWILL`/`BILLERR`).
- `addons` + `sub_addons`: **many-to-many** bridge, used only by unsupported items.

### warehouse.db, anchor `warehouse@inv_moves` (1,400 rows)
- `inv_moves`: move_ts and posted_dt (**two dates**), move_type codes `RCPT`/`PUTAWAY`/`PICK`/`XFER`/`ADJ`/`RTN`, qty, unit_cost, `is_damaged` (positive), `scan_ok` (normal-condition), ref_doc and reason_txt (mostly NULL), operator_id (NULL for half of the system adjustments).
- `items` (**undeclared text** FK sku_cd like `SKU-1001`): category with NULLs, uom `EA`/`BX`/`CS`/`KG`, unit_wt_kg (one exactly 10.0), std_cost. Names include `Nuts & Bolts Kit`, `O'Cedar Mop`, `Cable (3m)`. `Pallet Wrap (Blue)` has **zero moves**.
- `locations`: **role-playing** via undeclared `from_loc` and `to_loc` (each NULL for some move types). `Mezzanine M-01` is never used.
- `operators` (declared FK): shift, hourly_rate, forklift_cert.
- `move_exceptions`: **one-to-many child** (240 rows; some moves have 2-3 exceptions).

## Counts

| answerability | n | % |
|---|---|---|
| answerable | 73 | 68.9 |
| clarify | 20 | 18.9 |
| unsupported | 13 | 12.3 |

Kinds: scalar 42, rowset 23, ordered 4, empty_ok 4, clarify 33 (20 clarify + 13 unsupported).
By database: food 26, lease 26, telecom 27, warehouse 27.

| category | n | split |
|---|---|---|
| abbreviation | 5 | 5 answerable |
| ambiguous | 8 | 8 clarify |
| anti_join | 4 | 4 unsupported |
| boolean_flag | 6 | 6 answerable |
| breakdown | 4 | 4 answerable |
| date_role_ambiguity | 6 | 6 clarify |
| direct_kpi | 5 | 5 answerable |
| distinct_count | 4 | 4 answerable |
| fk_inference | 7 | 7 answerable |
| join_fanout | 7 | 4 answerable, 3 clarify |
| many_to_many | 2 | 2 unsupported |
| multi_table_join | 6 | 6 answerable |
| negation_exclusion | 4 | 4 answerable |
| null_condition | 4 | 4 answerable |
| period_comparison | 4 | 4 answerable |
| ratio | 7 | 4 answerable, 3 clarify |
| related_numeric_threshold | 4 | 4 answerable |
| share_of_total | 4 | 4 answerable |
| top_n | 4 | 4 answerable |
| trend | 4 | 4 answerable |
| unsupported_metric | 7 | 7 unsupported |

## Conventions

- **Percentages** are on a 0-100 scale. Shares in a share_of_total item add up to 100.
- **Averages and ratios** are left unrounded in the reference results. The validator compares values rounded to 6 decimal places, and scorers should apply their own tolerance.
- **NULL groups in breakdowns** are decided item by item and stated in `aggregation_grain`. TC02 and WH02 *include* the NULL group (label `null`) because the question asks for it. FD02 and FD05 *exclude* it because the question says to. Breakdowns over columns with no NULLs don't need to say anything. Lookup members with zero fact rows are *not* listed as 0 rows in breakdowns; rows come from inner joins.
- **Exclusions** ("excluding X", "not X", "outside X") *keep* NULLs, because a row with an unknown or absent value is not X. This applies to FD09 (no promo code), TC08 (no region), WH10 (no reason) and LS09 (no concession recorded; 0 is also treated as no concession). The `filters` field says so for each item.
- **Comparators**: "or more" / "at least" mean `>=`, "or less" means `<=`, and "over" / "heavier than" mean `>`. Every threshold item has a data value sitting exactly on the threshold (FD06 15.0, LS05 900, TC06 5 GB, WH07 10.0 kg), so getting the direction wrong changes the answer.
- **Flags**: positive flags (`is_late`, `is_damaged`, `is_disputed`, `is_renewal`) are 1 when the condition holds. Normal-condition flags (`delivered_ok`, `in_good_standing`, `cap_ok`, `scan_ok`) are 1 when things are fine, so a "problem" question means `= 0`.
- **Fan-out**: an answerable question that filters an anchor measure by a child-table attribute counts each anchor row once (EXISTS / DISTINCT). An unanswerable one *groups* an anchor measure by a child attribute, and those are labelled clarify.
- **empty_ok**: the filter names a real lookup member with no fact rows, or a threshold nothing reaches. The reference is SQL `NULL`. A system answering "none" or 0 should be scored correct. A system that refuses or substitutes another member should not.
- **ordered**: the reference SQL ends in `LIMIT n`. The validator re-runs it without the limit and checks that the top n+1 values are all distinct, so there is no tie inside the list or at the cut-off.
- **Labels**: rowset labels are the human-readable name column (rest_nm, staff_name, plan_name, item_desc, loc_name, cust_name, courier_nm), or the stored code value when the dimension itself is a code (vehicle_cd, unit_type, region, shift, category). Time labels are 'YYYY-MM' / 'YYYY' / 'Q1'-'Q2'.
- **Status scope**: unless the question says "delivered" (food) or "active" (lease), all statuses are included.
- **Unsupported items** have `kind = "clarify"` and `reference_sql = None`. The anti-join items (FD25, LS25, TC26, WH26) and the many-to-many breakdowns (TC24, TC25) are labelled unsupported because the brief asks for that. They are not physically impossible in SQL (see the borderline list).
- **Pitfalls**: 23 answerable items carry a `pitfall_sql`, a plausible wrong formulation (NULL dropped, flag polarity reversed, `>` vs `>=`, fan-out double count, wrong role, moves vs units). The validator checks that each one gives a different answer from the reference, which confirms the trap is live in the data.

## Validation

`python3 validate_v6.py` builds all DBs and runs all 73 reference/alt pairs, all of which agree. It checks every kind convention, runs all 23 pitfall readings (each differs from its reference), and confirms that each of the 20 clarify items has two or more readings with pairwise-different results. It also checks that every category appears at least twice. Last run: **ALL CHECKS PASSED**.

The validator was negative-tested by injecting a wrong alt_sql, a tie or row-count change on an ordered item, identical clarify readings and a non-NULL empty_ok result. All four were caught.

## Borderline items

These are items where a reasonable analyst could disagree with the chosen label or reference:

- **FD19**: "tip income for March": many analysts would default to order date. It is labelled clarify because tips are realised at delivery; the two readings differ.
- **FD02, FD07**: all order statuses are counted (FD07 includes ratings on refunded orders). A delivered-only reading is defensible.
- **FD18, TC17, WH19, LS18 (empty_ok)**: NULL vs 0 vs "no data" all count as correct. Only refusing should fail.
- **LS01, LS07, LS17**: "active" is taken from `lease_status`, not computed from dates against today's date. The data ends 2025-06-30.
- **LS13**: `is_late` also flags unpaid overdue payments, not only payments made late.
- **LS23**: "top-paying tenants" could be read as answerable (highest rent). It is labelled clarify because rent and actual payments disagree and no N is given.
- **TC05**: the plan averages include prorated first bills.
- **TC13**: the answer is negative because credits are stored as negative amounts. A positive answer of the same magnitude may be acceptable depending on the scorer's sign policy.
- **TC20**: ARPU per bill (subscriber-month) is the industry default. Labelled clarify because the revenue components and denominator are unstated.
- **WH14, WH16**: "picked in May" is taken as move_ts (the physical event), not posted_dt. WH16 says "by move date"; WH14 does not.
- **WH17**: unit-weighted damage rate. A move-weighted rate (3.33% vs 2.15%) is a plausible alternative, but the question says "received units".
- **FD25, LS25, TC26, WH26 (anti_join)** and **TC24, TC25 (many_to_many)**: labelled unsupported per the brief, though SQL could express them. An honest double-counting answer to TC24/TC25 could reasonably get partial credit.
