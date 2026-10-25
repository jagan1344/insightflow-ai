# v5 provisional evaluation set: authoring notes

## Provenance

- An AI agent (Claude) generated this set. **No human has adjudicated it.** Every item has `adjudication_status = "not human-adjudicated"`.
- It was written without access to the system under test. The author did not read, list, or run anything under `backend/`, `web/`, `docs/`, `evaluation/v2`, `evaluation/v3`, `research_improvement/` or `paper_evidence/`, and did not look at any earlier question sets or git history. Questions were not selected or dropped based on how any system might perform.
- The schemas, data and questions are synthetic. The data is deterministic: fixed seeds, Python standard library only. Running the builders twice gives byte-identical databases.
- The reference answers come from the author's own SQL. They have been checked mechanically (see Validation). That check shows internal consistency. It does not show that the chosen interpretation is the one a human panel would pick.

## Files

| File | Purpose |
|---|---|
| `fixtures_v5.py` | `build_hotel()`, `build_insurance()`, `build_energy()`, `build_rides()`, `build_all()`. Each one recreates `data/<name>.db` and returns its path. |
| `questions_v5.py` | `V5`: 105 question dicts. Optional extra keys: `alt_sql`, `clarify_readings`, `trap_sql`. |
| `validate_v5.py` | Builds the DBs, runs every SQL statement, checks the conventions and writes `reference_results.json`. |
| `reference_results.json` | `{id: rows}`. Clarify and unsupported items are `null`. |
| `data/*.db` | The generated SQLite databases. |

## Schemas

### hotel.db (anchor `bookings`, 950 rows)
- `hotels(hotel_id, hotel_nm, city, star_rtg)`, 6 rows. Values include `Captain's Inn`, `Bay & Pier Lodge` and `Grand Palace (Annex)`. **Old Town B&B** has rooms but zero bookings.
- `rooms(room_id, hotel_id, room_no, room_type, sq_m, base_rate)`, 33 rows. **`rooms.hotel_id` is an undeclared FK.** `sq_m` is a numeric attribute on a related table. Room types include `Family (2+2)`.
- `guests(guest_id, guest_nm, country, loyalty_tier)`, 320 rows. Some country and tier values are NULL. Guests 301-320 never book.
- `bookings(bk_id, guest_id→guests, room_id→rooms, booked_on, checkin_dt, nts_cnt, amt, channel, is_cancelled, payment_ok, special_req)`. There are **two date columns**: `booked_on` and `checkin_dt`, and `checkin_dt` has about 3.5% NULLs. `channel` has NULLs. There is a positive flag (`is_cancelled`) and a good-state flag (`payment_ok`).
- `booking_addons(addon_id, bk_id→bookings, addon_type, addon_amt)`, 848 rows. This is a **one-to-many child** of the anchor. Add-on types are drawn with replacement, so one booking can have two `Breakfast` rows (a fan-out trap).

### insurance.db (anchor `claims`, 1,100 rows)
- `products(product_cd, product_nm, line_of_bus)`. Values include `Auto (Comprehensive)`, `Home & Contents` and `Renter's Basic`. **Pet Care** has policies but zero claims.
- `policies(policy_no, holder_nm, product_cd→products, prem_amt, deductible, start_dt, region)`, 520 rows. `prem_amt` and `deductible` are numeric related attributes. `region` has NULLs.
- `adjusters(adj_id, adj_nm, region)`, 8 rows. Values include `Sean O'Brien` and `Lee & Partners (external)`.
- `claims(claim_id, policy_no→policies, adj_id, loss_dt, rpt_dt, closed_dt, claim_amt, status, cause, is_fraud_susp, docs_ok)`. **`claims.adj_id` is an undeclared FK** and is NULL for unassigned claims. There are three dates. `closed_dt` is NULL exactly when status is `Open`. `cause` has NULLs.
- `claim_payments(pmt_id, claim_id→claims, pmt_dt, pmt_amt)`, 1,198 rows. This is a one-to-many child; a claim can have 1-3 payments.
- Two different `region` attributes are reachable: the policyholder's region and the adjuster's region.

### energy.db (anchor `bills`, 1,250 rows)
- `tariffs(tariff_cd, tariff_nm, rate_per_kwh)`. Values include `Time-of-Use (TOU)`, `Green Saver's Plan` and `Farm & Rural`. **EV Night Owl** has no customers and therefore no bills.
- `customers(cust_id, cust_nm, segment, tariff_cd, city)`, 240 rows. **`customers.tariff_cd` is an undeclared FK.** `segment` has NULLs. Cities include `Saint-Jean d'Arc`.
- `meters(meter_id, cust_id→customers, meter_type, install_dt)`, 283 rows. Some customers have 2 meters. `install_dt` has NULLs. Meter types include both `Smart` and `Smart (3-phase)`. A few meters are never billed.
- `customer_programs(cust_id, program_nm, enrolled_dt)`, 312 rows. This is a one-to-many child of customers, so bills relate to programs many-to-many.
- `bills(bill_id, meter_id→meters, period_start, due_dt, paid_dt, kwh, amt, late_fee, meter_ok, is_estimated)`. There are three dates, and `paid_dt` and `late_fee` have NULLs. There is a good-state flag (`meter_ok`) and a positive flag (`is_estimated`). The anchor reaches tariffs through the chain bills→meters→customers→tariffs.

### rides.db (anchor `trips`, 1,450 rows)
- `zones(zone_cd, zone_nm, borough)`. Values include `Airport (JFK)`, `St. Mary's Park` and `Arts & Theatre District`. **Old Mill (Closed)** has zero trips.
- `drivers(driver_id, driver_nm, vehicle_cls, rating, join_dt)`, 60 rows. `rating` is a numeric related attribute. Vehicle classes include `Green (EV)`.
- `driver_languages(driver_id, lang)`, 105 rows. This is a one-to-many child of drivers, so trips relate to languages many-to-many.
- `riders(rider_id, signup_dt, rider_tier)`, 450 rows. Riders 421-450 never ride.
- `trips(trip_id, driver_id→drivers, rider_id→riders, pickup_zone_cd, dropoff_zone_cd, req_ts, status, fare_amt, tip_amt, dist_km, dur_min, is_surge, payment_ok, pay_method)`. **The `zones` table plays two roles** through `pickup_zone_cd` and `dropoff_zone_cd`, and neither is declared as an FK. `tip_amt` contains both NULL and 0.00. `pay_method` has NULLs. Cancelled trips can carry a 5.00 fee.

## Counts (105 questions)

By answerability:
- answerable: 74 (70.5%)
- clarify: 19 (18.1%)
- unsupported: 12 (11.4%)

By kind:
- scalar: 51
- rowset: 15
- ordered: 4
- empty_ok: 4
- clarify: 31 (all 19 clarify items plus all 12 unsupported items use kind `clarify`)

By database:
- hotel: 26
- insurance: 28
- energy: 25
- rides: 26

| category | answerable | clarify | unsupported | total |
|---|---|---|---|---|
| direct_kpi | 4 | | | 4 |
| breakdown | 3 | | | 3 |
| top_n | 4 | | | 4 |
| trend | 4 | | | 4 |
| multi_table_join | 6 | | | 6 |
| related_numeric_threshold | 4 | | | 4 |
| fk_inference | 7 | | | 7 |
| abbreviation | 4 | | | 4 |
| negation_exclusion | 5 | | | 5 |
| boolean_flag | 6 | | | 6 |
| null_condition | 6 | | | 6 |
| distinct_count | 4 | | | 4 |
| join_fanout | 4 | 2 | | 6 |
| date_role_ambiguity | 1 | 3 | | 4 |
| period_comparison | 4 | 1 | | 5 |
| ratio | 4 | 5 | | 9 |
| share_of_total | 4 | | | 4 |
| many_to_many | | | 2 | 2 |
| anti_join | | | 4 | 4 |
| ambiguous | | 8 | | 8 |
| unsupported_metric | | | 6 | 6 |

## Conventions

- **Rates and shares** are expressed as percentages from 0 to 100. A fraction equal to that value divided by 100 should be scored as equivalent.
- **Exclusions keep NULLs.** "Excluding X" is implemented as `col IS NOT 'X'`, so rows with an unknown category stay in. Each such item has a `trap_sql` using `<>`, and the validator confirms the two give different results.
- **Rowset labels** are human-readable names. Lookup members with zero fact rows, such as Old Town B&B, Pet Care and EV Night Owl, are absent from the breakdowns because the reference uses inner joins. A lenient scorer may accept an extra zero row.
- **empty_ok items:** HO25, IN21, EN18 and RI23 each filter on a lookup value that exists but has no fact rows. NULL, 0 or an empty result are all correct answers. A clarification is not.
- **Anti-joins and many-to-many breakdowns** are labelled `unsupported`, following the brief, even though SQL could express an answer.

## Validation

`python3 validate_v5.py`:
- Rebuilds all databases.
- Checks required keys and categories.
- Runs every `reference_sql` and its independently written `alt_sql`, and requires them to agree: within 1e-9 relative tolerance, order-insensitive for rowsets, order-sensitive for ordered.
- Checks the kind conventions: a scalar is one numeric value; rowset and ordered results have unique, non-NULL labels and numeric values; empty_ok returns NULL or no rows.
- For ordered items, checks there is no tie at the cut-off by re-running with `LIMIT n+1`.
- For every clarify item, runs its `clarify_readings` and confirms they give materially different results.
- Confirms all 15 `trap_sql` formulations differ from the reference.

Result: **ALL CHECKS PASSED**. That covers 74 ref/alt pairs, 19 sets of divergent readings and 15 traps.

## Borderline items (a human adjudicator should look at these first)

- **EN15** ("How many bills fall in March 2025?") is marked clarify. Some readers would take `period_start` as the obvious bill month.
- **IN16** ("claims did we get in Q2 2025") is marked clarify. "Get" leans towards the reported date.
- **EN12** ("overall average price per kWh") uses the volume-weighted SUM(amt)/SUM(kwh). The mean of per-bill ratios differs; this is the trap.
- **HO12, IN13, EN09, RI12** are exclusions that keep NULL-category rows. An analyst might argue that unknown values should be flagged rather than kept. RI12 ("not paid in cash" with a NULL method) is the weakest of these.
- **HO03, IN02, EN04, RI04** are breakdowns that omit lookup members with zero rows.
- **HO26** ("average length of stay per guest") is marked clarify. "Per guest" might be read loosely as "per booking".
- **RI07** ("average fare in the Arts & Theatre District") is ambiguous because of the zone role. It is also unclear whether cancelled-fee trips count.
- **IN28** ("What's the average claim?") is marked clarify. Many people would default to AVG(claim_amt).
- **EN16 and RI19** are labelled as unsupported many-to-many breakdowns. They could reasonably be treated as clarify instead.
- **The anti-join items** (HO23, IN24, EN19, RI21) are unsupported by convention, not because the data cannot answer them.
