"""Build QUESTIONS.md from results.json (written by check_questions.py)."""
import json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
R = json.load(open(HERE / "results.json"))
def fmt(v):
    return f"{v:,.2f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) else str(v))
def show(rows):
    if len(rows) == 1 and len(rows[0]) == 1:
        return fmt(rows[0][0])
    return "; ".join(f"{r[0]}: {fmt(r[-1])}" for r in rows[:12])
L = ["# Business sales dataset: questions to ask", "",
     "`sales_orders.csv` has 12,000 synthetic e-commerce order rows (2024–2025), regenerated exactly by `make_dataset.py`.",
     "", "## Columns", "", "| Column | Meaning |", "|---|---|",
     "| order_id | order number |", "| order_date | date ordered (always present) |",
     "| ship_date | date shipped (empty if not shipped yet, about 6%) |", "| region | North / South / East / West |",
     "| sales_channel | Online / Retail Store / Marketplace / Phone |", "| customer_segment | Consumer / Small Business / Enterprise |",
     "| sales_rep | 8 sales reps |", "| product_category | Electronics / Furniture / Office Supplies / Appliances |",
     "| product_name | 12 products |", "| quantity | units ordered |", "| unit_price | list price per unit |",
     "| discount_amount | discount given on the order |", "| revenue | amount charged after discount |", "| cost | cost of goods |",
     "| shipping_fee | delivery fee |", "| is_returned | 1 = returned |", "| is_priority | 1 = priority order |",
     "| customer_rating | 1–5 (empty if the customer gave none, about 25%) |", "",
     "## How to load it", "", "1. Start the backend and the frontend (see the README).",
     "2. In the app, click **Upload**, choose `sales_orders.csv`, and enter **`orders`** as the dataset name. "
     "This matters: the table becomes `dataset_orders`, so the word \"orders\" in questions is understood.",
     "3. Open **Ask AI** and ask the questions below.", "",
     "Every question below was run through the real API (`/api/ask`, default typed engine) and compared with hand-written SQL. "
     "From `backend/`, `PYTHONPATH=. python ../samples/business_sales/check_questions.py` re-runs the check and "
     "`python ../samples/business_sales/make_questions_md.py` rebuilds this file.", "",
     "**WARN** means the answer is correct but rests on an assumption the app states. For example, \"Revenue by product "
     "category\" has no aggregation word, so the app says it summed the revenue.", ""]
secs = list(dict.fromkeys(r["section"] for r in R))
L += ["## Questions that are answered correctly", ""]
for s in secs:
    items = [r for r in R if r["section"] == s and r["status"] == "correct"]
    if items:
        L += [f"### {s}", "", "| Question | App decision | Expected answer |", "|---|---|---|"]
        L += [f"| {r['question']} | {r['action']} | {show(r['expected'])} |" for r in items] + [""]
L += ["## Questions where the app asks you to clarify (intended behaviour)", "", "| Question | Why it asks |", "|---|---|"]
L += [f"| {r['question']} | {r['reason'].replace('|', '/')[:160]} |" for r in R if r["status"] == "asks (as it should)"]
L += ["", "To get an answer, name the date column (\"Monthly revenue by order date\", \"Total revenue for order date in 2024\"), "
      "give a year with the month, or use words that are in the data.", "",
      "## Phrasings the app does not understand yet (it asks instead of guessing)", "",
      "| Question | Reason | Rephrase as (verified above) |", "|---|---|---|"]
rephrase = {"Total quantity sold": "Total quantity", "Average discount amount for Enterprise customers": "Average discount amount for Enterprise",
            "Which region has the highest revenue?": "Top 1 region by revenue"}
L += [f"| {r['question']} | {r['reason'][:90]} | {rephrase.get(r['question'], '')} |" for r in R if r["status"] == "asks"]
L += ["", "## Known bug: do not rely on this phrasing", "", "| Question | App answer | Correct answer |", "|---|---|---|"]
L += [f"| {r['question']} | {show(r['rows'])} | {show(r['expected'])} |" for r in R if r["status"] == "WRONG"]
L += ["", "\"Excluding A **and** B\" excludes only A and then *keeps only* B. The bug is present in the evaluated (frozen) engine "
      "as well. Until it is fixed, ask \"Total revenue excluding Electronics\" and \"Total revenue excluding Furniture\" "
      "separately, or use \"Total revenue by product category\".", ""]
(HERE / "QUESTIONS.md").write_text("\n".join(L))
print({s: sum(r["status"] == s for r in R) for s in dict.fromkeys(r["status"] for r in R)})
