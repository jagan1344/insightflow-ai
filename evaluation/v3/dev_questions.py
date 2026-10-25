"""DEV question set (v3). Reference SQL is independent sqlite3 against the
fixture DBs, written by hand from the schema - never produced by the
planner. kinds:
  scalar | rowset (keyed by first col) | ordered (top-N order matters)
  clarify  (ambiguous / unknown: the only correct behaviour is CLARIFY/ABSTAIN)
  empty_ok (known value, zero fact rows: NULL/0/no rows is correct)
families: single, join_filter, grouped, distinct, fanout, time, topn,
  unknown, ambiguous, zero_fact, nulls
"""
A = "clinic"
B = "logistics"

DEV = [
 # ---- schema A: clinic (measure: visits.fee) ----
 (A, "A01", "single", "What is the total fee across all visits?", "scalar",
  "SELECT SUM(fee) FROM visits"),
 (A, "A02", "single", "How many visits were there?", "scalar",
  "SELECT COUNT(*) FROM visits"),
 (A, "A03", "grouped", "Total fee by specialty", "rowset",
  "SELECT d.specialty, SUM(v.fee) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id GROUP BY d.specialty"),
 (A, "A04", "nulls", "Total fee by insurer", "rowset",
  "SELECT i.insurer_name, SUM(v.fee) FROM visits v JOIN patients p ON p.patient_id=v.patient_id "
  "LEFT JOIN insurers i ON i.insurer_id=p.insurer_id GROUP BY i.insurer_name"),
 (A, "A05", "join_filter", "Total fee for Cardiology doctors", "scalar",
  "SELECT SUM(v.fee) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id WHERE d.specialty='Cardiology'"),
 (A, "A06", "distinct", "How many distinct patients visited in March 2025?", "scalar",
  "SELECT COUNT(DISTINCT patient_id) FROM visits WHERE visit_date>='2025-03-01' AND visit_date<'2025-04-01'"),
 (A, "A07", "join_filter", "Total fee for patients insured by Medicaid (State)", "scalar",
  "SELECT SUM(v.fee) FROM visits v JOIN patients p ON p.patient_id=v.patient_id "
  "JOIN insurers i ON i.insurer_id=p.insurer_id WHERE i.insurer_name='Medicaid (State)'"),
 (A, "A08", "ambiguous", "Total fee at Saint Mary's Clinic", "clarify", None),
 (A, "A09", "fanout", "Total fee for visits with an Imaging procedure", "scalar",
  "SELECT SUM(fee) FROM visits WHERE EXISTS (SELECT 1 FROM visit_procedures vp JOIN procedures pr "
  "ON pr.procedure_id=vp.procedure_id WHERE vp.visit_id=visits.visit_id AND pr.category='Imaging')"),
 (A, "A10", "fanout", "How many visits included an MRI?", "scalar",
  "SELECT COUNT(DISTINCT vp.visit_id) FROM visit_procedures vp JOIN procedures pr "
  "ON pr.procedure_id=vp.procedure_id WHERE pr.procedure_name='MRI'"),
 (A, "A11", "zero_fact", "Total fee for patients insured by Pacific Mutual", "empty_ok",
  "SELECT SUM(v.fee) FROM visits v JOIN patients p ON p.patient_id=v.patient_id "
  "JOIN insurers i ON i.insurer_id=p.insurer_id WHERE i.insurer_name='Pacific Mutual'"),
 (A, "A12", "unknown", "Total fee for patients insured by Cigna", "clarify", None),
 (A, "A13", "topn", "Top 3 doctors by total fee", "ordered",
  "SELECT d.full_name, SUM(v.fee) s FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id "
  "GROUP BY d.full_name ORDER BY s DESC LIMIT 3"),
 (A, "A14", "nulls", "What is the average copay?", "scalar",
  "SELECT AVG(copay) FROM visits"),
 (A, "A15", "ambiguous", "Total fee in June 2025", "clarify", None),  # two date columns, none named
 (A, "A17", "time", "Total fee for visits in June 2025", "scalar",
  "SELECT SUM(fee) FROM visits WHERE visit_date>='2025-06-01' AND visit_date<'2025-07-01'"),
 (A, "A16", "ambiguous", "Total fee by month", "clarify", None),  # visit_date vs discharge_date

 # ---- schema B: logistics (measure: shipments.freight_usd) ----
 (B, "B01", "single", "What is the total freight cost?", "scalar",
  "SELECT SUM(freight_usd) FROM shipments"),
 (B, "B02", "single", "How many shipments were there?", "scalar",
  "SELECT COUNT(*) FROM shipments"),
 (B, "B03", "nulls", "Total freight cost by carrier", "rowset",
  "SELECT c.carrier_label, SUM(s.freight_usd) FROM shipments s LEFT JOIN carriers c "
  "ON c.carrier_key=s.carrier_ref GROUP BY c.carrier_label"),
 (B, "B04", "join_filter", "Total freight cost for carrier O'Brien & Sons", "scalar",
  "SELECT SUM(s.freight_usd) FROM shipments s JOIN carriers c ON c.carrier_key=s.carrier_ref "
  "WHERE c.carrier_label=\"O'Brien & Sons\""),
 (B, "B05", "join_filter", "Total freight cost for Gold tier customers", "scalar",
  "SELECT SUM(s.freight_usd) FROM shipments s JOIN customers u ON u.cust_key=s.cust_ref WHERE u.tier='Gold'"),
 (B, "B06", "grouped", "Total freight cost by origin hub", "rowset",
  "SELECT h.hub_label, SUM(s.freight_usd) FROM shipments s JOIN hubs h ON h.hub_key=s.origin_hub GROUP BY h.hub_label"),
 (B, "B07", "ambiguous", "Total freight cost for Port of Rotterdam", "clarify", None),
 (B, "B08", "join_filter", "How many parcels were shipped by Blue Jay Freight?", "scalar",
  "SELECT COUNT(*) FROM parcels p JOIN shipments s ON s.shp_no=p.shp_no JOIN carriers c "
  "ON c.carrier_key=s.carrier_ref WHERE c.carrier_label='Blue Jay Freight'"),
 (B, "B09", "fanout", "Total freight cost for shipments tagged Fragile", "scalar",
  "SELECT SUM(freight_usd) FROM shipments WHERE EXISTS (SELECT 1 FROM shipment_tags st JOIN tags t "
  "ON t.tag_key=st.tag_key WHERE st.shp_no=shipments.shp_no AND t.tag_label='Fragile')"),
 (B, "B10", "distinct", "How many distinct customers shipped in July 2025?", "scalar",
  "SELECT COUNT(DISTINCT cust_ref) FROM shipments WHERE ship_dt>='2025-07-01' AND ship_dt<'2025-08-01'"),
 (B, "B11", "zero_fact", "Total freight cost for carrier Dormant Haulage", "empty_ok",
  "SELECT SUM(s.freight_usd) FROM shipments s JOIN carriers c ON c.carrier_key=s.carrier_ref "
  "WHERE c.carrier_label='Dormant Haulage'"),
 (B, "B12", "unknown", "Total freight cost for carrier Fedex", "clarify", None),
 (B, "B13", "topn", "Top 2 carriers by total freight cost", "ordered",
  "SELECT c.carrier_label, SUM(s.freight_usd) s FROM shipments s JOIN carriers c "
  "ON c.carrier_key=s.carrier_ref GROUP BY c.carrier_label ORDER BY s DESC LIMIT 2"),
 (B, "B14", "nulls", "What is the average insured value?", "scalar",
  "SELECT AVG(insured_usd) FROM shipments"),
 (B, "B15", "ambiguous", "Total freight cost by region code", "clarify", None),
]
