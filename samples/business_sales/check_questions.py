"""Upload sales_orders.csv through the real API (dataset name 'orders', isolated temp database) and ask every
question through /api/ask; compare with reference SQL. Writes results.json next to this script.
usage (from backend/): PYTHONPATH=. python ../samples/business_sales/check_questions.py"""
import json, os, pathlib, sqlite3, tempfile
HERE = pathlib.Path(__file__).resolve().parent
tmp = pathlib.Path(tempfile.mkdtemp(prefix="bizcheck_"))
os.environ["INSIGHTFLOW_SEED_DB_PATH"] = str(tmp / "app.db")
os.environ["DATABASE_URL"] = f"sqlite:///{tmp / 'app.db'}"
import subprocess, sys
subprocess.run([sys.executable, "data/seed.py"], check=True, capture_output=True, env=os.environ)
from fastapi.testclient import TestClient  # noqa: E402
from insightflow.config import settings  # noqa: E402
settings.database_url = os.environ["DATABASE_URL"]
from api.main import app  # noqa: E402
c = TestClient(app)
r = c.post("/api/upload/orders?mode=replace&dataset_name=orders",
           files={"file": ("sales_orders.csv", (HERE / "sales_orders.csv").read_bytes(), "text/csv")})
assert r.status_code == 200, r.text
T = r.json()["table_name"]; print("table", T, r.json()["rows_inserted"], "rows")
db = sqlite3.connect(tmp / "app.db")

# (section, question, reference SQL or None when the right behaviour is to ask, kind)
Q = [
 ("Totals", "How many orders are there?", "SELECT COUNT(*) FROM T", "scalar"),
 ("Totals", "What is the total revenue?", "SELECT SUM(revenue) FROM T", "scalar"),
 ("Totals", "Total cost", "SELECT SUM(cost) FROM T", "scalar"),
 ("Totals", "Total discount amount", "SELECT SUM(discount_amount) FROM T", "scalar"),
 ("Totals", "Total quantity sold", "SELECT SUM(quantity) FROM T", "scalar"),
 ("Totals", "Total quantity", "SELECT SUM(quantity) FROM T", "scalar"),
 ("Totals", "Total shipping fee", "SELECT SUM(shipping_fee) FROM T", "scalar"),
 ("Averages and extremes", "Average revenue", "SELECT AVG(revenue) FROM T", "scalar"),
 ("Averages and extremes", "Average customer rating", "SELECT AVG(customer_rating) FROM T", "scalar"),
 ("Averages and extremes", "Highest revenue", "SELECT MAX(revenue) FROM T", "scalar"),
 ("Averages and extremes", "Lowest unit price", "SELECT MIN(unit_price) FROM T", "scalar"),
 ("Averages and extremes", "Average discount amount for Enterprise customers", "SELECT AVG(discount_amount) FROM T WHERE customer_segment='Enterprise'", "scalar"),
 ("Averages and extremes", "Average discount amount for Enterprise", "SELECT AVG(discount_amount) FROM T WHERE customer_segment='Enterprise'", "scalar"),
 ("Breakdowns", "Total revenue by region", "SELECT region, SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Revenue by product category", "SELECT product_category, SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Number of orders by sales channel", "SELECT sales_channel, COUNT(*) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Total revenue by customer segment", "SELECT customer_segment, SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Total revenue by sales rep", "SELECT sales_rep, SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Average customer rating by product category", "SELECT product_category, AVG(customer_rating) FROM T GROUP BY 1", "rowset"),
 ("Breakdowns", "Total quantity by product name", "SELECT product_name, SUM(quantity) FROM T GROUP BY 1", "rowset"),
 ("Ranking", "Top 5 products by revenue", "SELECT product_name, SUM(revenue) FROM T GROUP BY 1 ORDER BY 2 DESC LIMIT 5", "ordered"),
 ("Ranking", "Top 3 sales reps by revenue", "SELECT sales_rep, SUM(revenue) FROM T GROUP BY 1 ORDER BY 2 DESC LIMIT 3", "ordered"),
 ("Ranking", "Bottom 3 products by quantity", "SELECT product_name, SUM(quantity) FROM T GROUP BY 1 ORDER BY 2 ASC LIMIT 3", "ordered"),
 ("Ranking", "Which region has the highest revenue?", "SELECT region, SUM(revenue) FROM T GROUP BY 1 ORDER BY 2 DESC LIMIT 1", "ordered"),
 ("Ranking", "Top 1 region by revenue", "SELECT region, SUM(revenue) FROM T GROUP BY 1 ORDER BY 2 DESC LIMIT 1", "ordered"),
 ("Filters", "Total revenue for Electronics", "SELECT SUM(revenue) FROM T WHERE product_category='Electronics'", "scalar"),
 ("Filters", "Total revenue in the West region", "SELECT SUM(revenue) FROM T WHERE region='West'", "scalar"),
 ("Filters", "Total revenue for Online orders in the North", "SELECT SUM(revenue) FROM T WHERE sales_channel='Online' AND region='North'", "scalar"),
 ("Filters", "Number of orders with quantity of 5 or more", "SELECT COUNT(*) FROM T WHERE quantity >= 5", "scalar"),
 ("Filters", "Number of orders with revenue over 1000", "SELECT COUNT(*) FROM T WHERE revenue > 1000", "scalar"),
 ("Filters", "Total revenue for Furniture by region", "SELECT region, SUM(revenue) FROM T WHERE product_category='Furniture' GROUP BY 1", "rowset"),
 ("Negation, flags and missing values", "How many orders were returned?", "SELECT COUNT(*) FROM T WHERE is_returned=1", "scalar"),
 ("Negation, flags and missing values", "Total revenue of orders that were not returned", "SELECT SUM(revenue) FROM T WHERE is_returned=0", "scalar"),
 ("Negation, flags and missing values", "How many priority orders?", "SELECT COUNT(*) FROM T WHERE is_priority=1", "scalar"),
 ("Negation, flags and missing values", "How many orders have not shipped?", "SELECT COUNT(*) FROM T WHERE ship_date IS NULL", "scalar"),
 ("Negation, flags and missing values", "How many orders have no customer rating?", "SELECT COUNT(*) FROM T WHERE customer_rating IS NULL", "scalar"),
 ("Negation, flags and missing values", "Total revenue excluding Marketplace", "SELECT SUM(revenue) FROM T WHERE sales_channel <> 'Marketplace'", "scalar"),
 ("Negation, flags and missing values", "Total revenue excluding Electronics and Furniture", "SELECT SUM(revenue) FROM T WHERE product_category NOT IN ('Electronics','Furniture')", "scalar"),
 ("Percentages and shares", "Percentage of orders that were returned", "SELECT 100.0*SUM(is_returned)/COUNT(*) FROM T", "scalar"),
 ("Percentages and shares", "Share of revenue by region", "SELECT region, 100.0*SUM(revenue)/(SELECT SUM(revenue) FROM T) FROM T GROUP BY 1", "rowset"),
 ("Percentages and shares", "Share of orders by sales channel", "SELECT sales_channel, 100.0*COUNT(*)/(SELECT COUNT(*) FROM T) FROM T GROUP BY 1", "rowset"),
 ("Formulas", "Total revenue minus cost", "SELECT SUM(revenue)-SUM(cost) FROM T", "scalar"),
 ("Formulas", "Total quantity times unit price", "SELECT SUM(quantity*unit_price) FROM T", "scalar"),
 ("Formulas", "Revenue divided by quantity", "SELECT SUM(revenue)*1.0/SUM(quantity) FROM T", "scalar"),
 ("Formulas", "Total discount amount divided by revenue", "SELECT SUM(discount_amount)*1.0/SUM(revenue) FROM T", "scalar"),
 ("Time", "Monthly revenue by order date", "SELECT substr(order_date,1,7), SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Time", "Total revenue by order date quarter", None, None),
 ("Time", "Number of orders ordered in March 2025", None, None),
 ("Time", "Total revenue for order date in 2024", "SELECT SUM(revenue) FROM T WHERE order_date >= '2024-01-01' AND order_date < '2025-01-01'", "scalar"),
 ("Time", "Yearly revenue by order date", "SELECT substr(order_date,1,4), SUM(revenue) FROM T GROUP BY 1", "rowset"),
 ("Distinct counts", "Number of distinct products", "SELECT COUNT(DISTINCT product_name) FROM T", "scalar"),
 ("Distinct counts", "Number of distinct sales reps", "SELECT COUNT(DISTINCT sales_rep) FROM T", "scalar"),
 ("Should ask (clarify)", "Monthly revenue", None, None),
 ("Should ask (clarify)", "Total revenue in 2025", None, None),
 ("Should ask (clarify)", "What is our profit margin?", None, None),
 ("Should ask (clarify)", "Which customers are most loyal?", None, None),
 ("Should ask (clarify)", "Total revenue in the last 30 days", None, None),
 ("Should ask (clarify)", "Forecast next month's revenue", None, None),
 ("Should ask (clarify)", "Total revenue in May", None, None),
 ("Should ask (clarify)", "Revenue per order", None, None),
 ("Safety (refused)", "Delete all orders", None, None),
]
import sys as _s
_s.path.append(str(HERE.parents[1] / "evaluation" / "v3"))
from run_eval import score  # noqa: E402
out = []
for sec, q, ref, kind in Q:
    j = c.post("/api/ask", json={"question": q}).json()
    act = j["decision"]["action"]; rows = [tuple(x) for x in j.get("result_rows") or []]
    exp = [tuple(x) for x in db.execute(ref.replace("FROM T", f'FROM "{T}"')).fetchall()] if ref else None
    if ref:
        ok = act in ("ANSWER", "WARN") and score(kind, rows, exp)[0]
        status = "correct" if ok else ("asks" if act not in ("ANSWER", "WARN") else "WRONG")
    else:
        status = "asks (as it should)" if act not in ("ANSWER", "WARN") else "answers"
    out.append(dict(section=sec, question=q, action=act, status=status, reason=j["decision"]["reason"],
                    sql=j.get("sql") or "", rows=[list(x) for x in rows[:12]], expected=[list(x) for x in (exp or [])[:12]]))
    print(f"{status:20s} {act:8s} {q}  | {j['decision']['reason'][:90]}")
(HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
