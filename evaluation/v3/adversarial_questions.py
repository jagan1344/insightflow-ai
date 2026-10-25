"""ADVERSARIAL / drift set (v3). Same independent-oracle protocol as
dev_questions. Written after the dev set, before looking at system output
on these questions."""
A = "clinic"
B = "logistics"

_S = ("SELECT SUM(v.fee) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id "
      "WHERE d.specialty {c}")

ADVERSARIAL = [
 # conflicting / multi-value filters: alternatives, not an empty conjunction
 (A, "X01", "multi_value", "Total fee for Cardiology doctors and Pediatrics doctors", "scalar",
  _S.format(c="IN ('Cardiology','Pediatrics')")),
 (B, "X02", "multi_value", "Total freight cost for Gold tier customers and Silver tier customers", "scalar",
  "SELECT SUM(s.freight_usd) FROM shipments s JOIN customers u ON u.cust_key=s.cust_ref WHERE u.tier IN ('Gold','Silver')"),
 # injection-shaped value: must refuse to guess and must not mutate anything
 (A, "X03", "unusual_value", "Total fee for patients insured by Cigna'; DROP TABLE visits;--", "clarify", None),
 # misleading wording: asks for something the plan would silently drop
 (A, "X04", "misleading", "What was the total fee not including copay?", "clarify", None),
 (A, "X05", "unfamiliar_term", "What are the total charges?", "clarify", None),
 # empty period: absolute year outside the data
 (A, "X06", "empty", "Total fee for visits in June 2031", "empty_ok",
  "SELECT SUM(fee) FROM visits WHERE visit_date>='2031-06-01' AND visit_date<'2031-07-01'"),
 # NULL handling
 (A, "X07", "nulls", "How many visits have no discharge date?", "scalar",
  "SELECT COUNT(*) FROM visits WHERE discharge_date IS NULL"),
 (A, "X08", "nulls", "What is the average copay for Cardiology doctors?", "scalar",
  "SELECT AVG(v.copay) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id WHERE d.specialty='Cardiology'"),
 (B, "X09", "nulls", "How many shipments have no insured value?", "scalar",
  "SELECT COUNT(*) FROM shipments WHERE insured_usd IS NULL"),
 # punctuation-heavy values
 (A, "X10", "unusual_value", "Total fee for Dr. K. Okafor-11", "scalar",
  "SELECT SUM(v.fee) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id WHERE d.full_name='Dr. K. Okafor-11'"),
 (B, "X11", "unusual_value", "Total freight cost for carrier Sky Cargo (Intl)", "scalar",
  "SELECT SUM(s.freight_usd) FROM shipments s JOIN carriers c ON c.carrier_key=s.carrier_ref WHERE c.carrier_label='Sky Cargo (Intl)'"),
 # casing / whitespace
 (A, "X12", "wording", "TOTAL FEE FOR CARDIOLOGY DOCTORS", "scalar", _S.format(c="= 'Cardiology'")),
 (A, "X13", "wording", "total   fee   for   cardiology    doctors", "scalar", _S.format(c="= 'Cardiology'")),
 # complex multi-operation
 (A, "X14", "complex", "Top 3 specialties by total fee for visits in March 2025", "ordered",
  "SELECT d.specialty, SUM(v.fee) s FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id "
  "WHERE v.visit_date>='2025-03-01' AND v.visit_date<'2025-04-01' GROUP BY d.specialty ORDER BY s DESC LIMIT 3"),
 (A, "X15", "complex", "Average fee per visit by specialty", "rowset",
  "SELECT d.specialty, AVG(v.fee) FROM visits v JOIN doctors d ON d.doctor_id=v.doctor_id GROUP BY d.specialty"),
 (B, "X16", "complex", "Total freight cost for shipments delivered in June 2025", "scalar",
  "SELECT SUM(freight_usd) FROM shipments WHERE delivered_dt>='2025-06-01' AND delivered_dt<'2025-07-01'"),
 # role-playing dimension with a paraphrase the schema does not literally contain
 (B, "X17", "paraphrase", "Total freight cost by destination hub", "rowset",
  "SELECT h.hub_label, SUM(s.freight_usd) FROM shipments s JOIN hubs h ON h.hub_key=s.dest_hub GROUP BY h.hub_label"),
 (B, "X18", "ambiguous", "Total freight cost for the Hamburg Terminal", "clarify", None),
 # unit / grain trap: parcels is a different grain than shipments
 (B, "X19", "grain", "How many parcels are there?", "clarify", None),
 (B, "X20", "nulls", "What is the average weight?", "scalar",
  "SELECT AVG(weight_kg) FROM shipments"),
]
