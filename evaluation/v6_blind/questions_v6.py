"""Blind question set v6.0 (agent-generated; see AUTHORING_NOTES.md).

Each entry of V6 is a dict.  Answerable items carry reference_sql and an
independently written alt_sql.  Clarify items carry reference_sql=None and a
`clarify_readings` dict of at least two competing SQL readings that give
different results.  Unsupported items carry reference_sql=None.
"""

PROVENANCE = "agent-generated blind set v6; authored without access to the system or earlier question sets"
SCHEMA_VERSION = "v6.0"

V6 = []


def Q(id, db, question, category, answerability, kind, metric_definition, filters, aggregation_grain,
      join_assumptions, reference_sql=None, alt_sql=None, ambiguity_notes="", clarify_readings=None):
    d = dict(id=id, db=db, schema_version=SCHEMA_VERSION, question=question, category=category,
             expected_answerability=answerability, kind=kind, metric_definition=metric_definition,
             filters=filters, aggregation_grain=aggregation_grain, join_assumptions=join_assumptions,
             reference_sql=reference_sql, alt_sql=alt_sql, ambiguity_notes=ambiguity_notes,
             provenance=PROVENANCE, adjudication_status="not human-adjudicated")
    if clarify_readings is not None:
        d["clarify_readings"] = clarify_readings
    V6.append(d)


NOJOIN = "Anchor table only; no joins."
UNSUP = "Not answerable from the schema; the system should say so / refuse."

# =============================================================================
# FOOD DELIVERY  (food@orders)
# =============================================================================
F = "food@orders"

Q("FD01", F, "How much did we take in delivery fees on orders that were actually delivered?",
  "direct_kpi", "answerable", "scalar",
  "SUM(orders.dlv_fee)", "order_status = 'DELIVERED' (cancelled and refunded orders excluded)", "single total", NOJOIN,
  "SELECT SUM(dlv_fee) FROM orders WHERE order_status = 'DELIVERED'",
  "SELECT TOTAL(dlv_fee * (order_status = 'DELIVERED')) FROM orders",
  "FREEDEL orders carry a 0 fee and are included (they contribute 0).")

Q("FD02", F, "Give me the number of orders for each type of cuisine. Skip restaurants that don't have a cuisine on file.",
  "breakdown", "answerable", "rowset",
  "COUNT(*) of orders", "all order statuses; restaurants with NULL cuisine excluded",
  "one row per non-NULL cuisine that has at least one order (French has no orders and is not listed); NULL cuisine group excluded",
  "orders.restaurant_id -> restaurants.restaurant_id (declared FK, many-to-one)",
  "SELECT r.cuisine, COUNT(*) FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id "
  "WHERE r.cuisine IS NOT NULL GROUP BY r.cuisine",
  "SELECT r.cuisine, SUM(x.n) FROM restaurants r JOIN (SELECT restaurant_id, COUNT(*) AS n FROM orders GROUP BY restaurant_id) x "
  "ON x.restaurant_id = r.restaurant_id WHERE r.cuisine IS NOT NULL GROUP BY r.cuisine",
  "Italian aggregates two restaurants.")

Q("FD03", F, "Which 3 restaurants brought in the most food sales (before fees and tips) on delivered orders?",
  "top_n", "answerable", "ordered",
  "SUM(orders.subtotal_amt)", "order_status = 'DELIVERED'", "one row per restaurant, top 3 by sales descending",
  "orders.restaurant_id -> restaurants (declared FK)",
  "SELECT r.rest_nm, SUM(o.subtotal_amt) AS s FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id "
  "WHERE o.order_status = 'DELIVERED' GROUP BY r.rest_nm ORDER BY s DESC LIMIT 3",
  "SELECT (SELECT rest_nm FROM restaurants r WHERE r.restaurant_id = t.restaurant_id), t.s FROM "
  "(SELECT restaurant_id, SUM(subtotal_amt) AS s FROM orders WHERE order_status = 'DELIVERED' GROUP BY restaurant_id) t "
  "ORDER BY t.s DESC LIMIT 3",
  "Food sales = subtotal_amt (pre-discount item total).")

Q("FD04", F, "Show monthly order volume for January through June 2025, going by when the order was placed.",
  "trend", "answerable", "rowset",
  "COUNT(*) of orders", "order_ts in 2025-01-01..2025-06-30; all statuses", "one row per calendar month 'YYYY-MM' of order_ts",
  NOJOIN,
  "SELECT strftime('%Y-%m', order_ts) AS m, COUNT(*) FROM orders WHERE order_ts >= '2025-01-01' AND order_ts < '2025-07-01' GROUP BY m",
  "SELECT substr(order_ts, 1, 7), COUNT(order_id) FROM orders WHERE substr(order_ts, 1, 4) = '2025' "
  "AND CAST(substr(order_ts, 6, 2) AS INTEGER) BETWEEN 1 AND 6 GROUP BY 1",
  "Date role is stated (placement time), so dlv_ts is not a competing reading.")

Q("FD05", F, "Total tips broken out by the kind of vehicle the courier rides (bike, car, scooter). Leave out couriers whose vehicle isn't recorded.",
  "multi_table_join", "answerable", "rowset",
  "SUM(orders.tip_amt) (NULL tips ignored)", "couriers.vehicle_cd IS NOT NULL; orders without courier drop out of the join",
  "one row per vehicle code (BIKE, CAR, SCTR); NULL vehicle group excluded",
  "orders.courier_id -> couriers.courier_id (undeclared FK, many-to-one)",
  "SELECT c.vehicle_cd, SUM(o.tip_amt) FROM orders o JOIN couriers c ON c.courier_id = o.courier_id "
  "WHERE c.vehicle_cd IS NOT NULL GROUP BY c.vehicle_cd",
  "SELECT v.vehicle_cd, (SELECT SUM(o.tip_amt) FROM orders o WHERE o.courier_id IN "
  "(SELECT c.courier_id FROM couriers c WHERE c.vehicle_cd = v.vehicle_cd)) FROM "
  "(SELECT DISTINCT vehicle_cd FROM couriers WHERE vehicle_cd IS NOT NULL) v",
  "Scooter is stored as the code 'SCTR'.")

Q("FD06", F, "How many delivered orders came from restaurants whose average prep time is 15 minutes or more?",
  "related_numeric_threshold", "answerable", "scalar",
  "COUNT(*) of orders", "order_status = 'DELIVERED' AND restaurants.avg_prep_min >= 15 (inclusive)", "single count",
  "orders.restaurant_id -> restaurants (declared FK)",
  "SELECT COUNT(*) FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id "
  "WHERE o.order_status = 'DELIVERED' AND r.avg_prep_min >= 15",
  "SELECT COUNT(*) FROM orders WHERE order_status = 'DELIVERED' AND restaurant_id IN "
  "(SELECT restaurant_id FROM restaurants WHERE NOT (avg_prep_min < 15))",
  "Pizza Planet (Westside) has exactly 15.0, so '>' vs '>=' changes the answer.")

Q("FD07", F, "What's the average star rating customers give each courier? List by courier name.",
  "fk_inference", "answerable", "rowset",
  "AVG(orders.cust_rating) over rated orders", "cust_rating IS NOT NULL; all statuses (refunded orders can carry ratings)",
  "one row per courier who has at least one rated order", "orders.courier_id -> couriers.courier_id (undeclared FK)",
  "SELECT c.courier_nm, AVG(o.cust_rating) FROM orders o JOIN couriers c ON c.courier_id = o.courier_id "
  "WHERE o.cust_rating IS NOT NULL GROUP BY c.courier_nm",
  "SELECT c.courier_nm, 1.0 * SUM(o.cust_rating) / COUNT(o.cust_rating) FROM couriers c JOIN orders o ON o.courier_id = c.courier_id "
  "GROUP BY c.courier_id HAVING COUNT(o.cust_rating) > 0",
  "The courier link is not a declared FK; it must be inferred from courier_id. Unrated orders must not count as 0.")

Q("FD08", F, "avg tkt size (subtotal) for GOLD-tier custs, delivered orders only?",
  "abbreviation", "answerable", "scalar",
  "AVG(orders.subtotal_amt)", "customers.loyalty_tier = 'GOLD' AND order_status = 'DELIVERED'", "single average",
  "orders.cust_id -> customers (declared FK)",
  "SELECT AVG(o.subtotal_amt) FROM orders o JOIN customers c ON c.cust_id = o.cust_id "
  "WHERE c.loyalty_tier = 'GOLD' AND o.order_status = 'DELIVERED'",
  "SELECT SUM(subtotal_amt) / COUNT(*) FROM orders WHERE order_status = 'DELIVERED' AND cust_id IN "
  "(SELECT cust_id FROM customers WHERE loyalty_tier = 'GOLD')",
  "'tkt' = ticket / order value; 'custs' = customers.")

Q("FD09", F, "How many orders didn't use the SAVE10 promo?",
  "negation_exclusion", "answerable", "scalar",
  "COUNT(*) of orders", "promo_cd IS NULL OR promo_cd <> 'SAVE10' -- orders with no promo code are KEPT; all statuses",
  "single count", NOJOIN,
  "SELECT COUNT(*) FROM orders WHERE promo_cd IS NULL OR promo_cd <> 'SAVE10'",
  "SELECT (SELECT COUNT(*) FROM orders) - (SELECT COUNT(*) FROM orders WHERE promo_cd = 'SAVE10')",
  "A plain promo_cd <> 'SAVE10' silently drops the ~825 orders with NULL promo_cd.")

Q("FD10", F, "How many delivered orders showed up late?",
  "boolean_flag", "answerable", "scalar",
  "COUNT(*) of orders", "order_status = 'DELIVERED' AND is_late = 1", "single count", NOJOIN,
  "SELECT COUNT(*) FROM orders WHERE order_status = 'DELIVERED' AND is_late = 1",
  "SELECT SUM(is_late) FROM orders WHERE order_status = 'DELIVERED'",
  "Refunded orders can also be late; they are excluded because the question says delivered.")

Q("FD11", F, "Of the delivered orders, how many had a problem with the drop-off, i.e. weren't marked as delivered OK?",
  "boolean_flag", "answerable", "scalar",
  "COUNT(*) of orders", "order_status = 'DELIVERED' AND delivered_ok = 0", "single count", NOJOIN,
  "SELECT COUNT(*) FROM orders WHERE order_status = 'DELIVERED' AND delivered_ok = 0",
  "SELECT SUM(1 - delivered_ok) FROM orders WHERE order_status = 'DELIVERED'",
  "delivered_ok is a normal-condition flag (1 = fine), so the problem case is 0 (polarity).")

Q("FD12", F, "How many different customers have ordered from Mama's Kitchen?",
  "distinct_count", "answerable", "scalar",
  "COUNT(DISTINCT orders.cust_id)", "restaurant = 'Mama''s Kitchen'; all statuses", "single count",
  "orders.restaurant_id -> restaurants (declared FK)",
  "SELECT COUNT(DISTINCT o.cust_id) FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id WHERE r.rest_nm = 'Mama''s Kitchen'",
  "SELECT COUNT(*) FROM customers WHERE cust_id IN (SELECT cust_id FROM orders WHERE restaurant_id = "
  "(SELECT restaurant_id FROM restaurants WHERE rest_nm LIKE 'Mama%Kitchen'))",
  "Name contains an apostrophe.")

Q("FD13", F, "What's the total delivery fee on delivered orders that had at least one drink in them?",
  "join_fanout", "answerable", "scalar",
  "SUM(orders.dlv_fee), each order counted once", "order_status = 'DELIVERED' AND order has >= 1 order_items row with item_cat = 'DRINK'",
  "single total", "orders 1 -> many order_items; use EXISTS / distinct orders so multi-drink orders are not double counted",
  "SELECT SUM(o.dlv_fee) FROM orders o WHERE o.order_status = 'DELIVERED' AND EXISTS "
  "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id AND i.item_cat = 'DRINK')",
  "SELECT SUM(o.dlv_fee) FROM orders o JOIN (SELECT DISTINCT order_id FROM order_items WHERE item_cat = 'DRINK') d "
  "ON d.order_id = o.order_id WHERE o.order_status = 'DELIVERED'",
  "A naive JOIN double counts the 90+ orders that contain two or more drink lines.")

Q("FD14", F, "How many orders never got a courier assigned?",
  "null_condition", "answerable", "scalar",
  "COUNT(*) of orders", "courier_id IS NULL", "single count", NOJOIN,
  "SELECT COUNT(*) FROM orders WHERE courier_id IS NULL",
  "SELECT COUNT(*) - COUNT(courier_id) FROM orders",
  "All such orders are cancelled ones.")

Q("FD15", F, "Compare delivered order counts for Q1 vs Q2 2025 (by order date).",
  "period_comparison", "answerable", "rowset",
  "COUNT(*) of orders", "order_status = 'DELIVERED'; order_ts within 2025-01-01..2025-06-30", "two rows labelled 'Q1' and 'Q2'",
  NOJOIN,
  "SELECT CASE WHEN order_ts < '2025-04-01' THEN 'Q1' ELSE 'Q2' END AS q, COUNT(*) FROM orders "
  "WHERE order_status = 'DELIVERED' AND order_ts >= '2025-01-01' AND order_ts < '2025-07-01' GROUP BY q",
  "SELECT 'Q' || ((CAST(strftime('%m', order_ts) AS INTEGER) + 2) / 3), COUNT(*) FROM orders "
  "WHERE order_status = 'DELIVERED' AND strftime('%Y', order_ts) = '2025' GROUP BY 1",
  "")

Q("FD16", F, "What percentage of delivered orders arrived late?",
  "ratio", "answerable", "scalar",
  "100 * late delivered orders / all delivered orders", "order_status = 'DELIVERED'", "single percentage (0-100)", NOJOIN,
  "SELECT 100.0 * SUM(is_late) / COUNT(*) FROM orders WHERE order_status = 'DELIVERED'",
  "SELECT AVG(CASE WHEN is_late = 1 THEN 100.0 ELSE 0 END) FROM orders WHERE order_status = 'DELIVERED'",
  "")

Q("FD17", F, "What share of delivered food sales came from restaurants in each city? Give percentages.",
  "share_of_total", "answerable", "rowset",
  "100 * SUM(subtotal_amt) per restaurant city / SUM(subtotal_amt) overall", "order_status = 'DELIVERED'",
  "one row per restaurant city (restaurants.city, not the customer's home city); shares sum to 100",
  "orders.restaurant_id -> restaurants (declared FK)",
  "SELECT r.city, 100.0 * SUM(o.subtotal_amt) / (SELECT SUM(subtotal_amt) FROM orders WHERE order_status = 'DELIVERED') "
  "FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id WHERE o.order_status = 'DELIVERED' GROUP BY r.city",
  "SELECT city, 100.0 * s / SUM(s) OVER () FROM (SELECT r.city, SUM(o.subtotal_amt) AS s FROM restaurants r JOIN orders o "
  "ON o.restaurant_id = r.restaurant_id AND o.order_status = 'DELIVERED' GROUP BY r.city)",
  "customers.home_city also exists, but 'restaurants in each city' fixes the role.")

Q("FD18", F, "What were total food sales at Closed Corner Cafe?",
  "multi_table_join", "answerable", "empty_ok",
  "SUM(orders.subtotal_amt)", "restaurant = 'Closed Corner Cafe'", "single total; the restaurant exists but has no orders, so the result is NULL / no sales",
  "orders.restaurant_id -> restaurants (declared FK)",
  "SELECT SUM(o.subtotal_amt) FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id WHERE r.rest_nm = 'Closed Corner Cafe'",
  "SELECT SUM(subtotal_amt) FROM orders WHERE restaurant_id IN (SELECT restaurant_id FROM restaurants WHERE rest_nm LIKE 'Closed Corner%')",
  "Correct behaviour is to report no sales (NULL or 0), not to refuse or pick another restaurant.")

Q("FD19", F, "What was our total tip income for March 2025?",
  "date_role_ambiguity", "clarify", "clarify",
  "SUM(tip_amt)", "March 2025 by an unspecified date column", "single total", NOJOIN,
  ambiguity_notes="orders has order_ts and dlv_ts; late-night month-end orders are delivered in the next month, so the two readings differ.",
  clarify_readings={
      "by_order_ts": "SELECT SUM(tip_amt) FROM orders WHERE order_ts >= '2025-03-01' AND order_ts < '2025-04-01'",
      "by_dlv_ts": "SELECT SUM(tip_amt) FROM orders WHERE dlv_ts >= '2025-03-01' AND dlv_ts < '2025-04-01'"})

Q("FD20", F, "Which restaurant is doing best?",
  "ambiguous", "clarify", "clarify",
  "undefined ('best')", "none", "one restaurant", "orders -> restaurants",
  ambiguity_notes="No metric given: order count, sales, and average rating each crown a different restaurant.",
  clarify_readings={
      "most_orders": "SELECT r.rest_nm, COUNT(*) AS n FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id GROUP BY r.rest_nm ORDER BY n DESC LIMIT 1",
      "most_sales": "SELECT r.rest_nm, SUM(o.subtotal_amt) AS s FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id WHERE o.order_status = 'DELIVERED' GROUP BY r.rest_nm ORDER BY s DESC LIMIT 1",
      "best_rating": "SELECT r.rest_nm, AVG(o.cust_rating) AS a FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id GROUP BY r.rest_nm ORDER BY a DESC LIMIT 1"})

Q("FD21", F, "What's our average order value?",
  "ratio", "clarify", "clarify",
  "undefined average order value", "unclear which orders", "single average", NOJOIN,
  ambiguity_notes="AOV could be food subtotal or the full customer charge (subtotal - discount + fee + tip), over delivered orders or all orders.",
  clarify_readings={
      "subtotal_delivered": "SELECT AVG(subtotal_amt) FROM orders WHERE order_status = 'DELIVERED'",
      "subtotal_all": "SELECT AVG(subtotal_amt) FROM orders",
      "total_charge_delivered": "SELECT AVG(subtotal_amt - disc_amt + dlv_fee + COALESCE(tip_amt, 0)) FROM orders WHERE order_status = 'DELIVERED'"})

Q("FD22", F, "Break down order revenue by item category.",
  "join_fanout", "clarify", "clarify",
  "revenue by order_items.item_cat", "none", "one row per item category", "orders 1 -> many order_items (category lives on the child)",
  ambiguity_notes="Order-level revenue cannot be split by a line-level attribute without double counting; line revenue (qty*unit_price) is a different measure.",
  clarify_readings={
      "line_revenue": "SELECT item_cat, SUM(qty * unit_price) FROM order_items GROUP BY item_cat",
      "order_subtotal_fanned_out": "SELECT d.item_cat, SUM(o.subtotal_amt) FROM orders o JOIN (SELECT DISTINCT order_id, item_cat FROM order_items) d ON d.order_id = o.order_id GROUP BY d.item_cat"})

Q("FD23", F, "How many big orders did we get?",
  "ambiguous", "clarify", "clarify",
  "count of 'big' orders", "undefined size threshold", "single count", "possibly orders -> order_items",
  ambiguity_notes="'Big' has no definition in the data (subtotal threshold? number of items?).",
  clarify_readings={
      "subtotal_50_plus": "SELECT COUNT(*) FROM orders WHERE subtotal_amt >= 50",
      "subtotal_40_plus": "SELECT COUNT(*) FROM orders WHERE subtotal_amt >= 40",
      "four_plus_units": "SELECT COUNT(*) FROM (SELECT order_id FROM order_items GROUP BY order_id HAVING SUM(qty) >= 4)"})

Q("FD24", F, "Forecast how many orders we'll get in July 2025.",
  "unsupported_metric", "unsupported", "clarify",
  "forecast", "n/a", "n/a", UNSUP,
  ambiguity_notes="Requires a predictive model; data ends 2025-06-30.")

Q("FD25", F, "Which customers have never placed an order?",
  "anti_join", "unsupported", "clarify",
  "customers with no orders", "n/a", "n/a", UNSUP,
  ambiguity_notes="Anti-join from a lookup table, outside the anchor-table question scope.")

Q("FD26", F, "What's the average distance a courier travels per delivery?",
  "unsupported_metric", "unsupported", "clarify",
  "distance", "n/a", "n/a", UNSUP,
  ambiguity_notes="No distance / location coordinates exist anywhere in the schema.")

# =============================================================================
# RESIDENTIAL LEASES  (lease@leases)
# =============================================================================
L = "lease@leases"

Q("LS01", L, "What's the total monthly rent across all of our active leases?",
  "direct_kpi", "answerable", "scalar",
  "SUM(leases.monthly_rent)", "lease_status = 'ACTIVE'", "single total", NOJOIN,
  "SELECT SUM(monthly_rent) FROM leases WHERE lease_status = 'ACTIVE'",
  "SELECT TOTAL(CASE lease_status WHEN 'ACTIVE' THEN monthly_rent END) FROM leases",
  "Active = status flag, not a date computation.")

Q("LS02", L, "How many leases have we written for each unit type?",
  "breakdown", "answerable", "rowset",
  "COUNT(*) of leases", "all leases, all statuses", "one row per units.unit_type (no NULL types exist)",
  "leases.unit_id -> units (declared FK)",
  "SELECT u.unit_type, COUNT(*) FROM leases l JOIN units u ON u.unit_id = l.unit_id GROUP BY u.unit_type",
  "SELECT u.unit_type, SUM(x.c) FROM units u JOIN (SELECT unit_id, COUNT(*) AS c FROM leases GROUP BY unit_id) x "
  "ON x.unit_id = u.unit_id GROUP BY u.unit_type",
  "")

Q("LS03", L, "Which three buildings had the highest average monthly rent on leases signed during 2024?",
  "top_n", "answerable", "ordered",
  "AVG(leases.monthly_rent)", "signed_dt in calendar 2024", "one row per building, top 3 descending",
  "leases.unit_id -> units.bldg_name",
  "SELECT u.bldg_name, AVG(l.monthly_rent) AS a FROM leases l JOIN units u ON u.unit_id = l.unit_id "
  "WHERE l.signed_dt BETWEEN '2024-01-01' AND '2024-12-31' GROUP BY u.bldg_name ORDER BY a DESC LIMIT 3",
  "SELECT b, s * 1.0 / n FROM (SELECT u.bldg_name AS b, SUM(l.monthly_rent) AS s, COUNT(*) AS n FROM units u JOIN leases l "
  "ON l.unit_id = u.unit_id WHERE strftime('%Y', l.signed_dt) = '2024' GROUP BY u.bldg_name) ORDER BY s * 1.0 / n DESC LIMIT 3",
  "Date role stated (signed).")

Q("LS04", L, "How many leases began in each year from 2019 to 2025?",
  "trend", "answerable", "rowset",
  "COUNT(*) of leases", "start_dt in 2019-01-01..2025-12-31", "one row per start year 'YYYY'", NOJOIN,
  "SELECT strftime('%Y', start_dt), COUNT(*) FROM leases WHERE start_dt BETWEEN '2019-01-01' AND '2025-12-31' GROUP BY 1",
  "SELECT substr(start_dt, 1, 4) AS y, COUNT(lease_id) FROM leases WHERE CAST(substr(start_dt, 1, 4) AS INTEGER) BETWEEN 2019 AND 2025 GROUP BY y",
  "'Began' = start_dt, not signed_dt.")

Q("LS05", L, "How many leases are for units of at least 900 square feet?",
  "related_numeric_threshold", "answerable", "scalar",
  "COUNT(*) of leases", "units.sq_ft >= 900 (inclusive)", "single count", "leases.unit_id -> units",
  "SELECT COUNT(*) FROM leases l JOIN units u ON u.unit_id = l.unit_id WHERE u.sq_ft >= 900",
  "SELECT COUNT(*) FROM leases WHERE unit_id IN (SELECT unit_id FROM units WHERE sq_ft > 899)",
  "One unit is exactly 900 sq ft.")

Q("LS06", L, "How many leases did each leasing agent sign? Show the agents' names.",
  "fk_inference", "answerable", "rowset",
  "COUNT(*) of leases", "all leases", "one row per staff member appearing as leasing agent (staff with zero leases omitted)",
  "leases.leasing_agent_id -> staff.staff_id (undeclared FK; role = leasing agent)",
  "SELECT s.staff_name, COUNT(*) FROM leases l JOIN staff s ON s.staff_id = l.leasing_agent_id GROUP BY s.staff_name",
  "SELECT s.staff_name, (SELECT COUNT(*) FROM leases l WHERE l.leasing_agent_id = s.staff_id) AS n FROM staff s WHERE n > 0",
  "staff is role-playing (also referenced by prop_mgr_id); the question names the role.")

Q("LS07", L, "Total monthly rent on active leases, by property manager.",
  "fk_inference", "answerable", "rowset",
  "SUM(leases.monthly_rent)", "lease_status = 'ACTIVE'", "one row per property manager with >= 1 active lease",
  "leases.prop_mgr_id -> staff.staff_id (undeclared FK; role = property manager)",
  "SELECT s.staff_name, SUM(l.monthly_rent) FROM leases l JOIN staff s ON s.staff_id = l.prop_mgr_id WHERE l.lease_status = 'ACTIVE' GROUP BY s.staff_name",
  "SELECT s.staff_name, x.r FROM staff s JOIN (SELECT prop_mgr_id, SUM(monthly_rent) AS r FROM leases WHERE lease_status = 'ACTIVE' GROUP BY prop_mgr_id) x "
  "ON x.prop_mgr_id = s.staff_id",
  "Joining via leasing_agent_id instead gives a different answer.")

Q("LS08", L, "avg sec dep on 2BR units where pets ok?",
  "abbreviation", "answerable", "scalar",
  "AVG(leases.security_dep)", "units.unit_type = '2BR' AND leases.pets_ok = 1", "single average", "leases.unit_id -> units",
  "SELECT AVG(l.security_dep) FROM leases l JOIN units u ON u.unit_id = l.unit_id WHERE u.unit_type = '2BR' AND l.pets_ok = 1",
  "SELECT SUM(security_dep) / COUNT(*) FROM leases WHERE pets_ok = 1 AND unit_id IN (SELECT unit_id FROM units WHERE bedrooms = 2)",
  "'sec dep' = security deposit; 2BR units are exactly the bedrooms = 2 units.")

Q("LS09", L, "Leaving out leases that came with a move-in concession, what's the average monthly rent?",
  "negation_exclusion", "answerable", "scalar",
  "AVG(leases.monthly_rent)", "concession_amt IS NULL OR concession_amt = 0 -- NULL (no concession recorded) and 0 are KEPT; only positive concessions are excluded",
  "single average", NOJOIN,
  "SELECT AVG(monthly_rent) FROM leases WHERE concession_amt IS NULL OR concession_amt = 0",
  "SELECT SUM(monthly_rent) / COUNT(*) FROM leases WHERE COALESCE(concession_amt, 0) = 0",
  "Filtering concession_amt = 0 or concession_amt IS NULL alone each give a different (wrong) number.")

Q("LS10", L, "How many leases are not in good standing?",
  "boolean_flag", "answerable", "scalar",
  "COUNT(*) of leases", "in_good_standing = 0", "single count", NOJOIN,
  "SELECT COUNT(*) FROM leases WHERE in_good_standing = 0",
  "SELECT COUNT(*) - SUM(in_good_standing) FROM leases",
  "Normal-condition flag; negated in the question.")

Q("LS11", L, "How many of our leases are month-to-month?",
  "null_condition", "answerable", "scalar",
  "COUNT(*) of leases", "end_dt IS NULL (month-to-month leases have no end date / term)", "single count", NOJOIN,
  "SELECT COUNT(*) FROM leases WHERE end_dt IS NULL",
  "SELECT COUNT(*) - COUNT(term_mos) FROM leases",
  "end_dt NULL and term_mos NULL coincide by construction.")

Q("LS12", L, "How many unique tenants have ever signed a lease with us?",
  "distinct_count", "answerable", "scalar",
  "COUNT(DISTINCT tenant_id)", "all leases", "single count", NOJOIN,
  "SELECT COUNT(DISTINCT tenant_id) FROM leases",
  "SELECT COUNT(*) FROM (SELECT tenant_id FROM leases GROUP BY tenant_id)",
  "Renewals and repeat tenants make COUNT(*) much larger.")

Q("LS13", L, "What's the total monthly rent across leases that have had at least one late rent payment?",
  "join_fanout", "answerable", "scalar",
  "SUM(leases.monthly_rent), each lease once", "lease has >= 1 rent_payments row with is_late = 1", "single total",
  "leases 1 -> many rent_payments; use EXISTS so leases with several late payments are counted once",
  "SELECT SUM(l.monthly_rent) FROM leases l WHERE EXISTS (SELECT 1 FROM rent_payments p WHERE p.lease_id = l.lease_id AND p.is_late = 1)",
  "SELECT SUM(l.monthly_rent) FROM leases l JOIN (SELECT DISTINCT lease_id FROM rent_payments WHERE is_late = 1) p ON p.lease_id = l.lease_id",
  "Naive join sums the rent once per late payment.")

Q("LS14", L, "How much in late fees have we charged on Oak & Elm Residences leases?",
  "multi_table_join", "answerable", "scalar",
  "SUM(rent_payments.late_fee)", "units.bldg_name = 'Oak & Elm Residences'", "single total",
  "rent_payments.lease_id -> leases (child of anchor); leases.unit_id -> units",
  "SELECT SUM(p.late_fee) FROM rent_payments p JOIN leases l ON l.lease_id = p.lease_id JOIN units u ON u.unit_id = l.unit_id "
  "WHERE u.bldg_name = 'Oak & Elm Residences'",
  "SELECT SUM(late_fee) FROM rent_payments WHERE lease_id IN (SELECT lease_id FROM leases WHERE unit_id IN "
  "(SELECT unit_id FROM units WHERE bldg_name LIKE 'Oak & Elm%'))",
  "Payment history only exists from 2024-07 onward.")

Q("LS15", L, "Leases signed in 2023 versus 2024: how many in each year?",
  "period_comparison", "answerable", "rowset",
  "COUNT(*) of leases", "signed_dt in 2023 or 2024", "two rows labelled '2023' and '2024'", NOJOIN,
  "SELECT strftime('%Y', signed_dt) AS y, COUNT(*) FROM leases WHERE signed_dt >= '2023-01-01' AND signed_dt < '2025-01-01' GROUP BY y",
  "SELECT '2023', SUM(signed_dt LIKE '2023-%') FROM leases UNION ALL SELECT '2024', SUM(signed_dt LIKE '2024-%') FROM leases",
  "")

Q("LS16", L, "What percent of our leases are renewals?",
  "ratio", "answerable", "scalar",
  "100 * renewal leases / all leases", "none", "single percentage (0-100)", NOJOIN,
  "SELECT 100.0 * SUM(is_renewal) / COUNT(*) FROM leases",
  "SELECT AVG(is_renewal) * 100 FROM leases",
  "")

Q("LS17", L, "For active leases, what percentage of total monthly rent does each building account for?",
  "share_of_total", "answerable", "rowset",
  "100 * SUM(monthly_rent) per building / SUM(monthly_rent)", "lease_status = 'ACTIVE' in both numerator and denominator",
  "one row per building with active leases", "leases.unit_id -> units",
  "SELECT u.bldg_name, 100.0 * SUM(l.monthly_rent) / (SELECT SUM(monthly_rent) FROM leases WHERE lease_status = 'ACTIVE') "
  "FROM leases l JOIN units u ON u.unit_id = l.unit_id WHERE l.lease_status = 'ACTIVE' GROUP BY u.bldg_name",
  "SELECT b, 100.0 * r / SUM(r) OVER () FROM (SELECT u.bldg_name AS b, SUM(l.monthly_rent) AS r FROM units u JOIN leases l ON l.unit_id = u.unit_id "
  "WHERE l.lease_status = 'ACTIVE' GROUP BY u.bldg_name)",
  "")

Q("LS18", L, "How much monthly rent comes from leases with a security deposit over $10,000?",
  "direct_kpi", "answerable", "empty_ok",
  "SUM(leases.monthly_rent)", "security_dep > 10000", "single total; no lease qualifies so the result is NULL / none", NOJOIN,
  "SELECT SUM(monthly_rent) FROM leases WHERE security_dep > 10000",
  "SELECT SUM(l.monthly_rent) FROM leases l WHERE l.lease_id IN (SELECT lease_id FROM leases WHERE NOT security_dep <= 10000)",
  "Largest deposit is well under $10k; correct answer is 'none'.")

Q("LS19", L, "How many leases did we have in 2024?",
  "date_role_ambiguity", "clarify", "clarify",
  "COUNT(*) of leases", "2024 by an unspecified date role", "single count", NOJOIN,
  ambiguity_notes="Could mean signed in 2024, started in 2024, or in force at any time during 2024.",
  clarify_readings={
      "signed_2024": "SELECT COUNT(*) FROM leases WHERE signed_dt BETWEEN '2024-01-01' AND '2024-12-31'",
      "started_2024": "SELECT COUNT(*) FROM leases WHERE start_dt BETWEEN '2024-01-01' AND '2024-12-31'",
      "in_force_2024": "SELECT COUNT(*) FROM leases WHERE start_dt <= '2024-12-31' AND (end_dt IS NULL OR end_dt >= '2024-01-01')"})

Q("LS20", L, "Which staff member is responsible for the most leases?",
  "ambiguous", "clarify", "clarify",
  "COUNT(*) of leases per staff member", "none", "one staff member", "staff is referenced twice: leasing_agent_id and prop_mgr_id",
  ambiguity_notes="Role-playing dimension without its role: as leasing agent the leader differs from as property manager (and combined counting double counts staff in both roles).",
  clarify_readings={
      "as_leasing_agent": "SELECT s.staff_name, COUNT(*) AS n FROM leases l JOIN staff s ON s.staff_id = l.leasing_agent_id GROUP BY s.staff_name ORDER BY n DESC LIMIT 1",
      "as_property_manager": "SELECT s.staff_name, COUNT(*) AS n FROM leases l JOIN staff s ON s.staff_id = l.prop_mgr_id GROUP BY s.staff_name ORDER BY n DESC LIMIT 1"})

Q("LS21", L, "Show me rent collected by month for 2025.",
  "date_role_ambiguity", "clarify", "clarify",
  "SUM(rent_payments.amt_paid)", "2025 by an unspecified date", "one row per month", "leases 1 -> many rent_payments",
  ambiguity_notes="rent_payments has due_dt and paid_dt; late payments land in a later month, so the monthly series differ.",
  clarify_readings={
      "by_due_month": "SELECT substr(due_dt, 1, 7), SUM(amt_paid) FROM rent_payments WHERE due_dt LIKE '2025-%' GROUP BY 1",
      "by_paid_month": "SELECT substr(paid_dt, 1, 7), SUM(amt_paid) FROM rent_payments WHERE paid_dt LIKE '2025-%' GROUP BY 1"})

Q("LS22", L, "What's our late payment rate?",
  "ratio", "clarify", "clarify",
  "late rate", "undefined denominator", "single percentage", "leases 1 -> many rent_payments",
  ambiguity_notes="Share of payments that were late, share of leases with any late payment, or share of rent dollars paid late.",
  clarify_readings={
      "pct_payments_late": "SELECT 100.0 * SUM(is_late) / COUNT(*) FROM rent_payments",
      "pct_leases_with_late": "SELECT 100.0 * COUNT(DISTINCT CASE WHEN p.is_late = 1 THEN p.lease_id END) / COUNT(DISTINCT p.lease_id) FROM rent_payments p",
      "pct_dollars_late": "SELECT 100.0 * SUM(CASE WHEN is_late = 1 THEN amt_due ELSE 0 END) / SUM(amt_due) FROM rent_payments"})

Q("LS23", L, "Who are our top-paying tenants?",
  "ambiguous", "clarify", "clarify",
  "undefined", "none", "top tenants", "leases -> tenants; leases 1 -> many rent_payments",
  ambiguity_notes="Highest contracted monthly rent vs most money actually paid (payments only since 2024-07); also no N given.",
  clarify_readings={
      "highest_monthly_rent": "SELECT t.tenant_name, MAX(l.monthly_rent) AS r FROM leases l JOIN tenants t ON t.tenant_id = l.tenant_id GROUP BY t.tenant_id ORDER BY r DESC, t.tenant_name LIMIT 5",
      "most_paid": "SELECT t.tenant_name, SUM(p.amt_paid) AS s FROM rent_payments p JOIN leases l ON l.lease_id = p.lease_id JOIN tenants t ON t.tenant_id = l.tenant_id GROUP BY t.tenant_id ORDER BY s DESC, t.tenant_name LIMIT 5"})

Q("LS24", L, "Project our occupancy rate for 2026.",
  "unsupported_metric", "unsupported", "clarify",
  "forecast", "n/a", "n/a", UNSUP, ambiguity_notes="Forecast; data ends mid-2025.")

Q("LS25", L, "Which units have never been leased?",
  "anti_join", "unsupported", "clarify",
  "units with no leases", "n/a", "n/a", UNSUP, ambiguity_notes="Anti-join from a lookup table.")

Q("LS26", L, "What's the average tenant satisfaction score by building?",
  "unsupported_metric", "unsupported", "clarify",
  "satisfaction", "n/a", "n/a", UNSUP, ambiguity_notes="No satisfaction / survey data exists.")

# =============================================================================
# MOBILE TELECOM  (telecom@monthly_bills)
# =============================================================================
T = "telecom@monthly_bills"

Q("TC01", T, "What's the total monthly recurring charge we billed for January through June 2025?",
  "direct_kpi", "answerable", "scalar",
  "SUM(monthly_bills.mrc_amt)", "bill_period 2025-01..2025-06", "single total", NOJOIN,
  "SELECT SUM(mrc_amt) FROM monthly_bills WHERE bill_period BETWEEN '2025-01' AND '2025-06'",
  "SELECT TOTAL(mrc_amt) FROM monthly_bills WHERE CAST(substr(bill_period, 6, 2) AS INTEGER) <= 6 AND bill_period LIKE '2025-%'",
  "All bills in the data are for these periods.")

Q("TC02", T, "Overage charges by customer region. Show subscribers with no region as their own blank group.",
  "breakdown", "answerable", "rowset",
  "SUM(monthly_bills.ovg_amt)", "none", "one row per subscribers.region INCLUDING a NULL-region group (label NULL)",
  "monthly_bills.sub_id -> subscribers (undeclared FK)",
  "SELECT s.region, SUM(b.ovg_amt) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id GROUP BY s.region",
  "SELECT region, SUM(o) FROM (SELECT (SELECT region FROM subscribers s WHERE s.sub_id = b.sub_id) AS region, b.ovg_amt AS o FROM monthly_bills b) GROUP BY region",
  "")

Q("TC03", T, "Top 5 subscribers by total mobile data used in H1 2025, in GB.",
  "top_n", "answerable", "ordered",
  "SUM(data_mb) / 1024 (GB)", "bill_period 2025-01..2025-06", "one row per subscriber (label cust_name), top 5 descending",
  "monthly_bills.sub_id -> subscribers (undeclared FK)",
  "SELECT s.cust_name, SUM(b.data_mb) / 1024.0 AS gb FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id "
  "WHERE b.bill_period BETWEEN '2025-01' AND '2025-06' GROUP BY s.sub_id ORDER BY gb DESC LIMIT 5",
  "SELECT (SELECT cust_name FROM subscribers s WHERE s.sub_id = x.sub_id), x.mb / 1024.0 FROM "
  "(SELECT sub_id, SUM(data_mb) AS mb FROM monthly_bills WHERE bill_period LIKE '2025-0%' GROUP BY sub_id) x ORDER BY x.mb DESC LIMIT 5",
  "Unit conversion MB -> GB uses 1024.")

Q("TC04", T, "Monthly overage revenue by usage month.",
  "trend", "answerable", "rowset",
  "SUM(ovg_amt)", "none", "one row per bill_period 'YYYY-MM'", NOJOIN,
  "SELECT bill_period, SUM(ovg_amt) FROM monthly_bills GROUP BY bill_period",
  "SELECT p, (SELECT SUM(ovg_amt) FROM monthly_bills b WHERE b.bill_period = d.p) FROM (SELECT DISTINCT bill_period AS p FROM monthly_bills) d",
  "'Usage month' fixes the date role to bill_period.")

Q("TC05", T, "Average recurring charge per bill for each plan, by plan name.",
  "fk_inference", "answerable", "rowset",
  "AVG(monthly_bills.mrc_amt)", "none", "one row per plan that has bills (Legacy Talk & Text has none and is omitted)",
  "monthly_bills.plan_cd -> plans.plan_cd (undeclared FK on a text code)",
  "SELECT p.plan_name, AVG(b.mrc_amt) FROM monthly_bills b JOIN plans p ON p.plan_cd = b.plan_cd GROUP BY p.plan_name",
  "SELECT p.plan_name, x.s / x.n FROM plans p JOIN (SELECT plan_cd, SUM(mrc_amt) AS s, COUNT(*) AS n FROM monthly_bills GROUP BY plan_cd) x ON x.plan_cd = p.plan_cd",
  "Prorated first bills pull some averages below list price.")

Q("TC06", T, "How many bills were on plans with a data allowance of 5 GB or less?",
  "related_numeric_threshold", "answerable", "scalar",
  "COUNT(*) of bills", "plans.data_cap_gb <= 5 (inclusive); unlimited plans (NULL cap) excluded", "single count",
  "monthly_bills.plan_cd -> plans (undeclared)",
  "SELECT COUNT(*) FROM monthly_bills b JOIN plans p ON p.plan_cd = b.plan_cd WHERE p.data_cap_gb <= 5",
  "SELECT COUNT(*) FROM monthly_bills WHERE plan_cd IN (SELECT plan_cd FROM plans WHERE data_cap_gb IS NOT NULL AND NOT data_cap_gb > 5)",
  "Basic 5GB sits exactly at 5. Treating NULL (unlimited) as 0 would wrongly include unlimited plans.")

Q("TC07", T, "sum of roam chgs for POSTPAID subs, Q2 bill periods",
  "abbreviation", "answerable", "scalar",
  "SUM(roam_amt) (NULL ignored)", "subscribers.acct_type = 'POSTPAID' AND bill_period 2025-04..2025-06", "single total",
  "monthly_bills.sub_id -> subscribers (undeclared)",
  "SELECT SUM(b.roam_amt) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id WHERE s.acct_type = 'POSTPAID' "
  "AND b.bill_period BETWEEN '2025-04' AND '2025-06'",
  "SELECT TOTAL(roam_amt) FROM monthly_bills WHERE bill_period IN ('2025-04', '2025-05', '2025-06') AND sub_id IN "
  "(SELECT sub_id FROM subscribers WHERE acct_type = 'POSTPAID')",
  "'roam chgs' = roaming charges; 'subs' = subscribers.")

Q("TC08", T, "Total tax billed to subscribers outside the NORTH region.",
  "negation_exclusion", "answerable", "scalar",
  "SUM(tax_amt)", "subscribers.region IS NULL OR region <> 'NORTH' -- subscribers with no region are KEPT (they are not in NORTH)",
  "single total", "monthly_bills.sub_id -> subscribers (undeclared)",
  "SELECT SUM(b.tax_amt) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id WHERE s.region IS NULL OR s.region <> 'NORTH'",
  "SELECT (SELECT SUM(tax_amt) FROM monthly_bills) - (SELECT SUM(tax_amt) FROM monthly_bills WHERE sub_id IN (SELECT sub_id FROM subscribers WHERE region = 'NORTH'))",
  "region <> 'NORTH' alone drops NULL-region subscribers.")

Q("TC09", T, "How many bills went over the data allowance?",
  "boolean_flag", "answerable", "scalar",
  "COUNT(*) of bills", "cap_ok = 0", "single count", NOJOIN,
  "SELECT COUNT(*) FROM monthly_bills WHERE cap_ok = 0",
  "SELECT COUNT(*) - SUM(cap_ok) FROM monthly_bills",
  "cap_ok is normal-condition named (1 = within allowance); polarity matters.")

Q("TC10", T, "How many bills haven't been paid yet?",
  "null_condition", "answerable", "scalar",
  "COUNT(*) of bills", "paid_dt IS NULL", "single count", NOJOIN,
  "SELECT COUNT(*) FROM monthly_bills WHERE paid_dt IS NULL",
  "SELECT COUNT(*) - COUNT(paid_dt) FROM monthly_bills",
  "")

Q("TC11", T, "How many unique subscribers were billed for March 2025 usage?",
  "distinct_count", "answerable", "scalar",
  "COUNT(DISTINCT sub_id)", "bill_period = '2025-03'", "single count", NOJOIN,
  "SELECT COUNT(DISTINCT sub_id) FROM monthly_bills WHERE bill_period = '2025-03'",
  "SELECT COUNT(*) FROM (SELECT sub_id FROM monthly_bills WHERE bill_period LIKE '2025-03' GROUP BY sub_id)",
  "'For March usage' fixes the date role.")

Q("TC12", T, "What's the total recurring charge on bills that got at least one outage credit?",
  "join_fanout", "answerable", "scalar",
  "SUM(mrc_amt), each bill once", "bill has >= 1 bill_adjustments row with reason_cd = 'OUTAGE'", "single total",
  "monthly_bills 1 -> many bill_adjustments; EXISTS avoids double counting",
  "SELECT SUM(b.mrc_amt) FROM monthly_bills b WHERE EXISTS (SELECT 1 FROM bill_adjustments a WHERE a.bill_id = b.bill_id AND a.reason_cd = 'OUTAGE')",
  "SELECT SUM(b.mrc_amt) FROM monthly_bills b JOIN (SELECT DISTINCT bill_id FROM bill_adjustments WHERE reason_cd = 'OUTAGE') a ON a.bill_id = b.bill_id",
  "")

Q("TC13", T, "Add up the adjustment amounts posted against Unlimited Max bills.",
  "multi_table_join", "answerable", "scalar",
  "SUM(bill_adjustments.adj_amt) (stored as negative credits; sign kept)", "monthly_bills.plan_cd = 'UNL-MAX'", "single total",
  "bill_adjustments.bill_id -> monthly_bills (child of anchor); plan name via plans",
  "SELECT SUM(a.adj_amt) FROM bill_adjustments a JOIN monthly_bills b ON b.bill_id = a.bill_id JOIN plans p ON p.plan_cd = b.plan_cd WHERE p.plan_name = 'Unlimited Max'",
  "SELECT SUM(adj_amt) FROM bill_adjustments WHERE bill_id IN (SELECT bill_id FROM monthly_bills WHERE plan_cd = 'UNL-MAX')",
  "Answer is negative (credits). An answer equal in magnitude but positive should be judged by the scorer's sign policy.")

Q("TC14", T, "Compare overage revenue in Q1 vs Q2 2025 by usage month.",
  "period_comparison", "answerable", "rowset",
  "SUM(ovg_amt)", "bill_period 2025-01..2025-06", "two rows labelled 'Q1' and 'Q2'", NOJOIN,
  "SELECT CASE WHEN bill_period <= '2025-03' THEN 'Q1' ELSE 'Q2' END AS q, SUM(ovg_amt) FROM monthly_bills "
  "WHERE bill_period BETWEEN '2025-01' AND '2025-06' GROUP BY q",
  "SELECT 'Q1', SUM(CASE WHEN bill_period IN ('2025-01','2025-02','2025-03') THEN ovg_amt END) FROM monthly_bills "
  "UNION ALL SELECT 'Q2', SUM(CASE WHEN bill_period IN ('2025-04','2025-05','2025-06') THEN ovg_amt END) FROM monthly_bills",
  "")

Q("TC15", T, "Of the bills that have been paid, what percentage were paid after the due date?",
  "ratio", "answerable", "scalar",
  "100 * paid bills with paid_dt > due_dt / paid bills", "paid_dt IS NOT NULL", "single percentage (0-100)", NOJOIN,
  "SELECT 100.0 * SUM(paid_dt > due_dt) / COUNT(*) FROM monthly_bills WHERE paid_dt IS NOT NULL",
  "SELECT 100.0 * (SELECT COUNT(*) FROM monthly_bills WHERE julianday(paid_dt) > julianday(due_dt)) / (SELECT COUNT(paid_dt) FROM monthly_bills)",
  "Unpaid bills are not in the denominator (stated in the question).")

Q("TC16", T, "What percentage of total recurring revenue does each plan make up?",
  "share_of_total", "answerable", "rowset",
  "100 * SUM(mrc_amt) per plan / SUM(mrc_amt)", "none", "one row per plan name with bills", "monthly_bills.plan_cd -> plans",
  "SELECT p.plan_name, 100.0 * SUM(b.mrc_amt) / (SELECT SUM(mrc_amt) FROM monthly_bills) FROM monthly_bills b JOIN plans p ON p.plan_cd = b.plan_cd GROUP BY p.plan_name",
  "SELECT p.plan_name, 100.0 * x.s / SUM(x.s) OVER () FROM plans p JOIN (SELECT plan_cd, SUM(mrc_amt) AS s FROM monthly_bills GROUP BY plan_cd) x ON x.plan_cd = p.plan_cd",
  "")

Q("TC17", T, "How much recurring revenue did the Legacy Talk & Text plan bring in?",
  "fk_inference", "answerable", "empty_ok",
  "SUM(mrc_amt)", "plan_name = 'Legacy Talk & Text'", "single total; plan exists but has no bills -> NULL / none",
  "monthly_bills.plan_cd -> plans (undeclared)",
  "SELECT SUM(b.mrc_amt) FROM monthly_bills b JOIN plans p ON p.plan_cd = b.plan_cd WHERE p.plan_name = 'Legacy Talk & Text'",
  "SELECT SUM(mrc_amt) FROM monthly_bills WHERE plan_cd = (SELECT plan_cd FROM plans WHERE plan_name LIKE 'Legacy Talk%')",
  "")

Q("TC18", T, "avg voice mins per bill for PREPAID accts?",
  "abbreviation", "answerable", "scalar",
  "AVG(voice_min)", "subscribers.acct_type = 'PREPAID'", "single average", "monthly_bills.sub_id -> subscribers (undeclared)",
  "SELECT AVG(b.voice_min) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id WHERE s.acct_type = 'PREPAID'",
  "SELECT 1.0 * SUM(voice_min) / COUNT(*) FROM monthly_bills WHERE sub_id IN (SELECT sub_id FROM subscribers WHERE acct_type = 'PREPAID')",
  "")

Q("TC19", T, "How many bills did we have in March 2025?",
  "date_role_ambiguity", "clarify", "clarify",
  "COUNT(*) of bills", "March 2025 by unspecified date", "single count", NOJOIN,
  ambiguity_notes="bill_period (usage month) vs stmt_dt (statement issued, the following month) vs due_dt.",
  clarify_readings={
      "usage_month": "SELECT COUNT(*) FROM monthly_bills WHERE bill_period = '2025-03'",
      "statement_month": "SELECT COUNT(*) FROM monthly_bills WHERE stmt_dt BETWEEN '2025-03-01' AND '2025-03-31'"})

Q("TC20", T, "What's our ARPU?",
  "ratio", "clarify", "clarify",
  "average revenue per user", "undefined", "single value", "possibly monthly_bills -> subscribers",
  ambiguity_notes="Per bill (= per subscriber-month) or per subscriber over the half-year; MRC only or including overage/roaming/tax.",
  clarify_readings={
      "per_bill_mrc": "SELECT AVG(mrc_amt) FROM monthly_bills",
      "per_bill_all_charges": "SELECT AVG(mrc_amt + ovg_amt + COALESCE(roam_amt, 0)) FROM monthly_bills",
      "per_subscriber_total": "SELECT SUM(mrc_amt + ovg_amt + COALESCE(roam_amt, 0)) / COUNT(DISTINCT sub_id) FROM monthly_bills"})

Q("TC21", T, "Which region is performing best?",
  "ambiguous", "clarify", "clarify",
  "undefined", "none", "one region", "monthly_bills -> subscribers",
  ambiguity_notes="Total revenue, revenue per bill, or overage each rank regions differently.",
  clarify_readings={
      "total_revenue": "SELECT s.region, SUM(b.mrc_amt + b.ovg_amt) AS r FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id GROUP BY s.region ORDER BY r DESC LIMIT 1",
      "revenue_per_bill": "SELECT s.region, AVG(b.mrc_amt + b.ovg_amt) AS r FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id GROUP BY s.region ORDER BY r DESC LIMIT 1",
      "lowest_unpaid_share": "SELECT s.region, AVG(b.paid_dt IS NULL) AS u FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id GROUP BY s.region ORDER BY u ASC LIMIT 1"})

Q("TC22", T, "What's the average bill amount by adjustment reason?",
  "join_fanout", "clarify", "clarify",
  "avg by bill_adjustments.reason_cd", "none", "one row per reason", "monthly_bills 1 -> many bill_adjustments",
  ambiguity_notes="Grouping bills by a one-to-many attribute: average of the bill (each bill once per reason) vs average adjustment amount; 'bill amount' itself undefined.",
  clarify_readings={
      "avg_bill_mrc_distinct": "SELECT d.reason_cd, AVG(b.mrc_amt) FROM monthly_bills b JOIN (SELECT DISTINCT bill_id, reason_cd FROM bill_adjustments) d ON d.bill_id = b.bill_id GROUP BY d.reason_cd",
      "avg_adjustment": "SELECT reason_cd, AVG(adj_amt) FROM bill_adjustments GROUP BY reason_cd"})

Q("TC23", T, "How much revenue did we have for May 2025?",
  "date_role_ambiguity", "clarify", "clarify",
  "SUM(mrc_amt + ovg_amt + roam)", "May 2025 by unspecified date", "single total", NOJOIN,
  ambiguity_notes="Usage month, statement month, or cash received (paid_dt) in May.",
  clarify_readings={
      "usage_month": "SELECT SUM(mrc_amt + ovg_amt + COALESCE(roam_amt, 0)) FROM monthly_bills WHERE bill_period = '2025-05'",
      "statement_month": "SELECT SUM(mrc_amt + ovg_amt + COALESCE(roam_amt, 0)) FROM monthly_bills WHERE stmt_dt LIKE '2025-05-%'",
      "paid_month": "SELECT SUM(mrc_amt + ovg_amt + COALESCE(roam_amt, 0)) FROM monthly_bills WHERE paid_dt LIKE '2025-05-%'"})

Q("TC24", T, "Break down total recurring charges by add-on.",
  "many_to_many", "unsupported", "clarify",
  "MRC by add-on", "n/a", "n/a", "subscribers many <-> many addons via sub_addons; no valid allocation of a bill to add-ons",
  ambiguity_notes="Many-to-many: a subscriber with 3 add-ons would have their MRC counted 3 times.")

Q("TC25", T, "What's the average monthly data usage for each add-on?",
  "many_to_many", "unsupported", "clarify",
  "data usage by add-on", "n/a", "n/a", "bridge table sub_addons (many-to-many)",
  ambiguity_notes="Usage cannot be attributed to add-ons; many-to-many breakdown.")

Q("TC26", T, "Which plans don't have any bills?",
  "anti_join", "unsupported", "clarify",
  "plans without bills", "n/a", "n/a", UNSUP, ambiguity_notes="Anti-join from a lookup table.")

Q("TC27", T, "What's each subscriber's probability of churning next quarter?",
  "unsupported_metric", "unsupported", "clarify",
  "churn probability", "n/a", "n/a", UNSUP, ambiguity_notes="Predictive model, not in data.")

# =============================================================================
# WAREHOUSE  (warehouse@inv_moves)
# =============================================================================
W = "warehouse@inv_moves"

Q("WH01", W, "How many units did we receive in total in the first half of 2025?",
  "direct_kpi", "answerable", "scalar",
  "SUM(qty)", "move_type = 'RCPT'; move_ts in 2025-01-01..2025-06-30", "single total", NOJOIN,
  "SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT' AND move_ts >= '2025-01-01' AND move_ts < '2025-07-01'",
  "SELECT TOTAL(CASE WHEN move_type = 'RCPT' THEN qty END) FROM inv_moves WHERE strftime('%Y', move_ts) = '2025' AND CAST(strftime('%m', move_ts) AS INTEGER) <= 6",
  "Receipts only (returns are RTN, not receipts). Date role = move_ts; all move_ts fall in H1 2025, while a few posted_dt values could spill into July.")

Q("WH02", W, "Total units moved by product category, with uncategorized items shown as a separate group.",
  "breakdown", "answerable", "rowset",
  "SUM(qty)", "all move types", "one row per items.category INCLUDING the NULL category group (label NULL)",
  "inv_moves.sku_cd -> items.sku_cd (undeclared FK)",
  "SELECT i.category, SUM(m.qty) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd GROUP BY i.category",
  "SELECT c, SUM(q) FROM (SELECT (SELECT category FROM items i WHERE i.sku_cd = m.sku_cd) AS c, m.qty AS q FROM inv_moves m) GROUP BY c",
  "")

Q("WH03", W, "Top 5 products by units picked.",
  "top_n", "answerable", "ordered",
  "SUM(qty)", "move_type = 'PICK'", "one row per item (label item_desc), top 5 descending",
  "inv_moves.sku_cd -> items (undeclared)",
  "SELECT i.item_desc, SUM(m.qty) AS u FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE m.move_type = 'PICK' GROUP BY i.item_desc ORDER BY u DESC LIMIT 5",
  "SELECT (SELECT item_desc FROM items i WHERE i.sku_cd = x.sku_cd), x.u FROM (SELECT sku_cd, SUM(qty) AS u FROM inv_moves WHERE move_type = 'PICK' GROUP BY sku_cd) x ORDER BY x.u DESC LIMIT 5",
  "")

Q("WH04", W, "How many inventory movements happened each month, by movement timestamp?",
  "trend", "answerable", "rowset",
  "COUNT(*) of moves", "none", "one row per 'YYYY-MM' of move_ts", NOJOIN,
  "SELECT strftime('%Y-%m', move_ts), COUNT(*) FROM inv_moves GROUP BY 1",
  "SELECT substr(move_ts, 1, 7) AS m, COUNT(move_id) FROM inv_moves GROUP BY m",
  "")

Q("WH05", W, "How many units were received into each receiving location (where the receipts landed)?",
  "fk_inference", "answerable", "rowset",
  "SUM(qty)", "move_type = 'RCPT'", "one row per destination location name",
  "inv_moves.to_loc -> locations.loc_id (undeclared FK; destination role)",
  "SELECT l.loc_name, SUM(m.qty) FROM inv_moves m JOIN locations l ON l.loc_id = m.to_loc WHERE m.move_type = 'RCPT' GROUP BY l.loc_name",
  "SELECT (SELECT loc_name FROM locations l WHERE l.loc_id = x.to_loc), x.q FROM (SELECT to_loc, SUM(qty) AS q FROM inv_moves WHERE move_type = 'RCPT' GROUP BY to_loc) x",
  "Receipts have from_loc NULL; using from_loc would produce nothing.")

Q("WH06", W, "Units picked out of each storage location.",
  "fk_inference", "answerable", "rowset",
  "SUM(qty)", "move_type = 'PICK'", "one row per source location name",
  "inv_moves.from_loc -> locations.loc_id (undeclared FK; source role)",
  "SELECT l.loc_name, SUM(m.qty) FROM inv_moves m JOIN locations l ON l.loc_id = m.from_loc WHERE m.move_type = 'PICK' GROUP BY l.loc_name",
  "SELECT l.loc_name, (SELECT SUM(qty) FROM inv_moves m WHERE m.from_loc = l.loc_id AND m.move_type = 'PICK') AS q FROM locations l WHERE q IS NOT NULL",
  "'Out of' = source (from_loc); to_loc gives pack/ship stations instead.")

Q("WH07", W, "How many moves involved items heavier than 10 kg per unit?",
  "related_numeric_threshold", "answerable", "scalar",
  "COUNT(*) of moves", "items.unit_wt_kg > 10 (strict)", "single count", "inv_moves.sku_cd -> items (undeclared)",
  "SELECT COUNT(*) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE i.unit_wt_kg > 10",
  "SELECT COUNT(*) FROM inv_moves WHERE sku_cd IN (SELECT sku_cd FROM items WHERE NOT unit_wt_kg <= 10)",
  "'Chain 5m' weighs exactly 10.0 kg and must be excluded.")

Q("WH08", W, "What's the total value (quantity times unit cost) of moves handled by night-shift operators?",
  "multi_table_join", "answerable", "scalar",
  "SUM(qty * unit_cost)", "operators.shift = 'NIGHT'", "single total", "inv_moves.operator_id -> operators (declared FK)",
  "SELECT SUM(m.qty * m.unit_cost) FROM inv_moves m JOIN operators o ON o.operator_id = m.operator_id WHERE o.shift = 'NIGHT'",
  "SELECT SUM(qty * unit_cost) FROM inv_moves WHERE operator_id IN (SELECT operator_id FROM operators WHERE shift = 'NIGHT')",
  "Value uses the move's unit_cost, not items.std_cost.")

Q("WH09", W, "total qty of XFERs for HARDWARE cat",
  "abbreviation", "answerable", "scalar",
  "SUM(qty)", "move_type = 'XFER' AND items.category = 'HARDWARE'", "single total", "inv_moves.sku_cd -> items (undeclared)",
  "SELECT SUM(m.qty) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE m.move_type = 'XFER' AND i.category = 'HARDWARE'",
  "SELECT SUM(qty) FROM inv_moves WHERE move_type = 'XFER' AND sku_cd IN (SELECT sku_cd FROM items WHERE category = 'HARDWARE')",
  "XFER = transfer.")

Q("WH10", W, "How many moves were not cycle-count corrections?",
  "negation_exclusion", "answerable", "scalar",
  "COUNT(*) of moves", "reason_txt IS NULL OR reason_txt <> 'Cycle count' -- moves with no reason recorded are KEPT",
  "single count", NOJOIN,
  "SELECT COUNT(*) FROM inv_moves WHERE reason_txt IS NULL OR reason_txt <> 'Cycle count'",
  "SELECT COUNT(*) - (SELECT COUNT(*) FROM inv_moves WHERE reason_txt = 'Cycle count') FROM inv_moves",
  "reason_txt <> 'Cycle count' alone drops ~1000 NULL-reason moves.")

Q("WH11", W, "How many moves had a failed barcode scan?",
  "boolean_flag", "answerable", "scalar",
  "COUNT(*) of moves", "scan_ok = 0", "single count", NOJOIN,
  "SELECT COUNT(*) FROM inv_moves WHERE scan_ok = 0",
  "SELECT COUNT(*) - SUM(scan_ok) FROM inv_moves",
  "scan_ok is normal-condition named; failed = 0.")

Q("WH12", W, "How many damaged units came in on receipts?",
  "boolean_flag", "answerable", "scalar",
  "SUM(qty)", "move_type = 'RCPT' AND is_damaged = 1", "single total (units, not moves)", NOJOIN,
  "SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT' AND is_damaged = 1",
  "SELECT SUM(qty * is_damaged) FROM inv_moves WHERE move_type = 'RCPT'",
  "Units, not number of moves.")

Q("WH13", W, "How many movements have no operator recorded against them?",
  "null_condition", "answerable", "scalar",
  "COUNT(*) of moves", "operator_id IS NULL", "single count", NOJOIN,
  "SELECT COUNT(*) FROM inv_moves WHERE operator_id IS NULL",
  "SELECT COUNT(*) - COUNT(operator_id) FROM inv_moves",
  "")

Q("WH14", W, "How many distinct SKUs were picked in May 2025?",
  "distinct_count", "answerable", "scalar",
  "COUNT(DISTINCT sku_cd)", "move_type = 'PICK' AND move_ts in May 2025", "single count", NOJOIN,
  "SELECT COUNT(DISTINCT sku_cd) FROM inv_moves WHERE move_type = 'PICK' AND move_ts >= '2025-05-01' AND move_ts < '2025-06-01'",
  "SELECT COUNT(*) FROM (SELECT sku_cd FROM inv_moves WHERE move_type = 'PICK' AND strftime('%Y-%m', move_ts) = '2025-05' GROUP BY sku_cd)",
  "Pick date taken as move_ts (when the pick happened). posted_dt reading is an alternative but 'picked in May' refers to the physical event; see borderline list.")

Q("WH15", W, "What's the total quantity on moves that logged at least one exception?",
  "join_fanout", "answerable", "scalar",
  "SUM(qty), each move once", "move has >= 1 move_exceptions row", "single total",
  "inv_moves 1 -> many move_exceptions; EXISTS avoids double counting",
  "SELECT SUM(m.qty) FROM inv_moves m WHERE EXISTS (SELECT 1 FROM move_exceptions e WHERE e.move_id = m.move_id)",
  "SELECT SUM(m.qty) FROM inv_moves m JOIN (SELECT DISTINCT move_id FROM move_exceptions) e ON e.move_id = m.move_id",
  "")

Q("WH16", W, "Units picked in April vs May 2025, by move date.",
  "period_comparison", "answerable", "rowset",
  "SUM(qty)", "move_type = 'PICK'; move_ts in April or May 2025", "two rows labelled '2025-04' and '2025-05'", NOJOIN,
  "SELECT strftime('%Y-%m', move_ts) AS m, SUM(qty) FROM inv_moves WHERE move_type = 'PICK' AND move_ts >= '2025-04-01' AND move_ts < '2025-06-01' GROUP BY m",
  "SELECT '2025-04', SUM(CASE WHEN move_ts LIKE '2025-04-%' THEN qty END) FROM inv_moves WHERE move_type = 'PICK' "
  "UNION ALL SELECT '2025-05', SUM(CASE WHEN move_ts LIKE '2025-05-%' THEN qty END) FROM inv_moves WHERE move_type = 'PICK'",
  "")

Q("WH17", W, "What percentage of received units were damaged?",
  "ratio", "answerable", "scalar",
  "100 * SUM(qty where is_damaged = 1) / SUM(qty)", "move_type = 'RCPT'", "single percentage (0-100), unit-weighted", NOJOIN,
  "SELECT 100.0 * SUM(CASE WHEN is_damaged = 1 THEN qty ELSE 0 END) / SUM(qty) FROM inv_moves WHERE move_type = 'RCPT'",
  "SELECT 100.0 * (SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT' AND is_damaged = 1) / (SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT')",
  "Units-weighted (question says 'received units'); move-weighted rate differs.")

Q("WH18", W, "What share of picked units did each operator shift handle, in percent?",
  "share_of_total", "answerable", "rowset",
  "100 * SUM(qty) per shift / SUM(qty)", "move_type = 'PICK' (all picks have an operator)", "one row per shift (DAY, NIGHT, SWING)",
  "inv_moves.operator_id -> operators (declared FK)",
  "SELECT o.shift, 100.0 * SUM(m.qty) / (SELECT SUM(qty) FROM inv_moves WHERE move_type = 'PICK') FROM inv_moves m JOIN operators o ON o.operator_id = m.operator_id "
  "WHERE m.move_type = 'PICK' GROUP BY o.shift",
  "SELECT shift, 100.0 * u / SUM(u) OVER () FROM (SELECT o.shift, SUM(m.qty) AS u FROM operators o JOIN inv_moves m ON m.operator_id = o.operator_id AND m.move_type = 'PICK' GROUP BY o.shift)",
  "")

Q("WH19", W, "How many units of Pallet Wrap (Blue) were moved in 2025?",
  "multi_table_join", "answerable", "empty_ok",
  "SUM(qty)", "items.item_desc = 'Pallet Wrap (Blue)'; 2025", "single total; the item exists but never moved -> NULL / none",
  "inv_moves.sku_cd -> items (undeclared)",
  "SELECT SUM(m.qty) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE i.item_desc = 'Pallet Wrap (Blue)' AND m.move_ts LIKE '2025-%'",
  "SELECT SUM(qty) FROM inv_moves WHERE sku_cd = (SELECT sku_cd FROM items WHERE item_desc LIKE 'Pallet Wrap%')",
  "")

Q("WH20", W, "How many units did we receive in March 2025?",
  "date_role_ambiguity", "clarify", "clarify",
  "SUM(qty) of receipts", "March 2025 by unspecified date", "single total", NOJOIN,
  ambiguity_notes="move_ts (physical receipt) vs posted_dt (ledger posting, up to 4 days later); month-end receipts post in April.",
  clarify_readings={
      "by_move_ts": "SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT' AND move_ts >= '2025-03-01' AND move_ts < '2025-04-01'",
      "by_posted_dt": "SELECT SUM(qty) FROM inv_moves WHERE move_type = 'RCPT' AND posted_dt BETWEEN '2025-03-01' AND '2025-03-31'"})

Q("WH21", W, "Total units by location.",
  "ambiguous", "clarify", "clarify",
  "SUM(qty) per location", "none", "one row per location", "locations referenced twice: from_loc and to_loc",
  ambiguity_notes="Role-playing dimension without a role: units moved out of vs into each location.",
  clarify_readings={
      "by_source": "SELECT l.loc_name, SUM(m.qty) FROM inv_moves m JOIN locations l ON l.loc_id = m.from_loc GROUP BY l.loc_name",
      "by_destination": "SELECT l.loc_name, SUM(m.qty) FROM inv_moves m JOIN locations l ON l.loc_id = m.to_loc GROUP BY l.loc_name"})

Q("WH22", W, "Who's our most productive operator?",
  "ambiguous", "clarify", "clarify",
  "undefined productivity", "none", "one operator", "inv_moves -> operators",
  ambiguity_notes="Number of moves, units moved, or value moved; each picks a different person.",
  clarify_readings={
      "most_moves": "SELECT o.op_name, COUNT(*) AS n FROM inv_moves m JOIN operators o ON o.operator_id = m.operator_id GROUP BY o.op_name ORDER BY n DESC LIMIT 1",
      "most_units": "SELECT o.op_name, SUM(m.qty) AS n FROM inv_moves m JOIN operators o ON o.operator_id = m.operator_id GROUP BY o.op_name ORDER BY n DESC LIMIT 1",
      "most_value": "SELECT o.op_name, SUM(m.qty * m.unit_cost) AS n FROM inv_moves m JOIN operators o ON o.operator_id = m.operator_id GROUP BY o.op_name ORDER BY n DESC LIMIT 1"})

Q("WH23", W, "Break down units moved by exception code.",
  "join_fanout", "clarify", "clarify",
  "units by move_exceptions.exc_cd", "none", "one row per exception code", "inv_moves 1 -> many move_exceptions",
  ambiguity_notes="Grouping move quantity by a child attribute double counts moves with several exceptions; units_affected on the exception is a different measure.",
  clarify_readings={
      "move_qty_per_code": "SELECT d.exc_cd, SUM(m.qty) FROM inv_moves m JOIN (SELECT DISTINCT move_id, exc_cd FROM move_exceptions) d ON d.move_id = m.move_id GROUP BY d.exc_cd",
      "units_affected": "SELECT exc_cd, SUM(units_affected) FROM move_exceptions GROUP BY exc_cd"})

Q("WH24", W, "What was the value of stock moved per zone in Q2 2025?",
  "ambiguous", "clarify", "clarify",
  "SUM(qty * unit_cost) per zone", "Q2 2025", "one row per zone", "locations.zone reachable through from_loc or to_loc",
  ambiguity_notes="Source zone vs destination zone (role-playing locations).",
  clarify_readings={
      "source_zone": "SELECT l.zone, SUM(m.qty * m.unit_cost) FROM inv_moves m JOIN locations l ON l.loc_id = m.from_loc WHERE m.move_ts >= '2025-04-01' AND m.move_ts < '2025-07-01' GROUP BY l.zone",
      "destination_zone": "SELECT l.zone, SUM(m.qty * m.unit_cost) FROM inv_moves m JOIN locations l ON l.loc_id = m.to_loc WHERE m.move_ts >= '2025-04-01' AND m.move_ts < '2025-07-01' GROUP BY l.zone"})

Q("WH25", W, "Predict which SKUs will stock out next month.",
  "unsupported_metric", "unsupported", "clarify",
  "forecast", "n/a", "n/a", UNSUP, ambiguity_notes="Forecast; no on-hand balances or demand model.")

Q("WH26", W, "Which SKUs haven't moved at all in 2025?",
  "anti_join", "unsupported", "clarify",
  "items with no moves", "n/a", "n/a", UNSUP, ambiguity_notes="Anti-join from a lookup table.")

Q("WH27", W, "What was the inbound freight cost per receipt?",
  "unsupported_metric", "unsupported", "clarify",
  "freight cost", "n/a", "n/a", UNSUP, ambiguity_notes="No freight / shipping cost data in the schema.")


# -----------------------------------------------------------------------------
# Pitfall readings: a plausible WRONG formulation for selected answerable items.
# validate_v6.py checks that each pitfall gives a different result from the
# reference, i.e. that the trap the question targets is live in the data.
# -----------------------------------------------------------------------------
PITFALLS = {
    "FD06": ("strict > instead of 'or more'", "SELECT COUNT(*) FROM orders o JOIN restaurants r ON r.restaurant_id = o.restaurant_id WHERE o.order_status = 'DELIVERED' AND r.avg_prep_min > 15"),
    "FD07": ("unrated orders counted as 0", "SELECT c.courier_nm, AVG(COALESCE(o.cust_rating, 0)) FROM orders o JOIN couriers c ON c.courier_id = o.courier_id GROUP BY c.courier_nm"),
    "FD09": ("NULL promo codes dropped", "SELECT COUNT(*) FROM orders WHERE promo_cd <> 'SAVE10'"),
    "FD11": ("flag polarity reversed", "SELECT COUNT(*) FROM orders WHERE order_status = 'DELIVERED' AND delivered_ok = 1"),
    "FD13": ("fan-out double counting", "SELECT SUM(o.dlv_fee) FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE i.item_cat = 'DRINK' AND o.order_status = 'DELIVERED'"),
    "LS05": ("strict > instead of 'at least'", "SELECT COUNT(*) FROM leases l JOIN units u ON u.unit_id = l.unit_id WHERE u.sq_ft > 900"),
    "LS07": ("wrong role (leasing agent)", "SELECT s.staff_name, SUM(l.monthly_rent) FROM leases l JOIN staff s ON s.staff_id = l.leasing_agent_id WHERE l.lease_status = 'ACTIVE' GROUP BY s.staff_name"),
    "LS09": ("zero-concession rows dropped", "SELECT AVG(monthly_rent) FROM leases WHERE concession_amt IS NULL"),
    "LS12": ("COUNT(*) instead of distinct", "SELECT COUNT(tenant_id) FROM leases"),
    "LS13": ("fan-out double counting", "SELECT SUM(l.monthly_rent) FROM leases l JOIN rent_payments p ON p.lease_id = l.lease_id WHERE p.is_late = 1"),
    "TC06": ("strict < instead of 'or less'", "SELECT COUNT(*) FROM monthly_bills b JOIN plans p ON p.plan_cd = b.plan_cd WHERE p.data_cap_gb < 5"),
    "TC08": ("NULL regions dropped", "SELECT SUM(b.tax_amt) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id WHERE s.region <> 'NORTH'"),
    "TC09": ("flag polarity reversed", "SELECT COUNT(*) FROM monthly_bills WHERE cap_ok = 1"),
    "TC12": ("fan-out double counting", "SELECT SUM(b.mrc_amt) FROM monthly_bills b JOIN bill_adjustments a ON a.bill_id = b.bill_id WHERE a.reason_cd = 'OUTAGE'"),
    "TC02": ("NULL region group dropped", "SELECT s.region, SUM(b.ovg_amt) FROM monthly_bills b JOIN subscribers s ON s.sub_id = b.sub_id WHERE s.region IS NOT NULL GROUP BY s.region"),
    "WH02": ("NULL category group dropped", "SELECT i.category, SUM(m.qty) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE i.category IS NOT NULL GROUP BY i.category"),
    "WH07": (">= instead of strict >", "SELECT COUNT(*) FROM inv_moves m JOIN items i ON i.sku_cd = m.sku_cd WHERE i.unit_wt_kg >= 10"),
    "WH10": ("NULL reasons dropped", "SELECT COUNT(*) FROM inv_moves WHERE reason_txt <> 'Cycle count'"),
    "WH11": ("flag polarity reversed", "SELECT COUNT(*) FROM inv_moves WHERE scan_ok = 1"),
    "WH12": ("moves counted instead of units", "SELECT COUNT(*) FROM inv_moves WHERE move_type = 'RCPT' AND is_damaged = 1"),
    "WH15": ("fan-out double counting", "SELECT SUM(m.qty) FROM inv_moves m JOIN move_exceptions e ON e.move_id = m.move_id"),
    "WH17": ("move-weighted instead of unit-weighted", "SELECT 100.0 * AVG(is_damaged) FROM inv_moves WHERE move_type = 'RCPT'"),
    "WH06": ("wrong role (destination)", "SELECT l.loc_name, SUM(m.qty) FROM inv_moves m JOIN locations l ON l.loc_id = m.to_loc WHERE m.move_type = 'PICK' GROUP BY l.loc_name"),
}
for _q in V6:
    if _q["id"] in PITFALLS:
        _q["pitfall_sql"] = {"description": PITFALLS[_q["id"]][0], "sql": PITFALLS[_q["id"]][1]}
