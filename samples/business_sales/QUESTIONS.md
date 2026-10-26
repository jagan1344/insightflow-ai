# Business sales dataset: questions to ask

`sales_orders.csv` has 12,000 synthetic e-commerce order rows (2024–2025), regenerated exactly by `make_dataset.py`.

## Columns

| Column | Meaning |
|---|---|
| order_id | order number |
| order_date | date ordered (always present) |
| ship_date | date shipped (empty if not shipped yet, about 6%) |
| region | North / South / East / West |
| sales_channel | Online / Retail Store / Marketplace / Phone |
| customer_segment | Consumer / Small Business / Enterprise |
| sales_rep | 8 sales reps |
| product_category | Electronics / Furniture / Office Supplies / Appliances |
| product_name | 12 products |
| quantity | units ordered |
| unit_price | list price per unit |
| discount_amount | discount given on the order |
| revenue | amount charged after discount |
| cost | cost of goods |
| shipping_fee | delivery fee |
| is_returned | 1 = returned |
| is_priority | 1 = priority order |
| customer_rating | 1–5 (empty if the customer gave none, about 25%) |

## How to load it

1. Start the backend and the frontend (see the README).
2. In the app, click **Upload**, choose `sales_orders.csv`, and enter **`orders`** as the dataset name. This matters: the table becomes `dataset_orders`, so the word "orders" in questions is understood.
3. Open **Ask AI** and ask the questions below.

Every question below was run through the real API (`/api/ask`, default typed engine) and compared with hand-written SQL. From `backend/`, `PYTHONPATH=. python ../samples/business_sales/check_questions.py` re-runs the check and `python ../samples/business_sales/make_questions_md.py` rebuilds this file.

**WARN** means the answer is correct but rests on an assumption the app states. For example, "Revenue by product category" has no aggregation word, so the app says it summed the revenue.

## Questions that are answered correctly

### Totals

| Question | App decision | Expected answer |
|---|---|---|
| How many orders are there? | ANSWER | 12,000 |
| What is the total revenue? | ANSWER | 10,141,284.12 |
| Total cost | ANSWER | 6,738,121 |
| Total discount amount | ANSWER | 784,199.10 |
| Total quantity | ANSWER | 38,693 |
| Total shipping fee | ANSWER | 105,250.36 |

### Averages and extremes

| Question | App decision | Expected answer |
|---|---|---|
| Average revenue | ANSWER | 845.11 |
| Average customer rating | ANSWER | 3.60 |
| Highest revenue | ANSWER | 13,229.01 |
| Lowest unit price | ANSWER | 12 |
| Average discount amount for Enterprise | ANSWER | 65.08 |

### Breakdowns

| Question | App decision | Expected answer |
|---|---|---|
| Total revenue by region | ANSWER | East: 2,468,462.75; North: 2,633,261.79; South: 2,320,044.42; West: 2,719,515.16 |
| Revenue by product category | WARN | Appliances: 980,441.57; Electronics: 6,076,440.67; Furniture: 2,859,005.61; Office Supplies: 225,396.27 |
| Number of orders by sales channel | ANSWER | Marketplace: 2,987; Online: 3,101; Phone: 2,989; Retail Store: 2,923 |
| Total revenue by customer segment | ANSWER | Consumer: 3,429,032.50; Enterprise: 3,474,282.53; Small Business: 3,237,969.09 |
| Total revenue by sales rep | ANSWER | Alice Moreno: 1,268,659.62; Ben Okafor: 1,355,452.03; Chen Wei: 1,157,382.63; Dana Fischer: 1,305,044.30; Elif Kaya: 1,339,894.56; Farah Haddad: 1,300,820.33; Gus Lindqvist: 1,198,063.99; Hana Sato: 1,215,966.66 |
| Average customer rating by product category | ANSWER | Appliances: 3.66; Electronics: 3.55; Furniture: 3.61; Office Supplies: 3.62 |
| Total quantity by product name | ANSWER | 4K Monitor: 3,361; Air Purifier: 3,271; Bookshelf: 3,252; Coffee Maker: 3,360; Desk Organizer: 3,197; Gel Pens (12): 3,203; Laptop Pro 14: 3,290; Noise-Cancel Headphones: 3,247; Office Chair: 3,128; Printer Paper (box): 3,241; Standing Desk: 3,120; Wireless Mouse: 3,023 |

### Ranking

| Question | App decision | Expected answer |
|---|---|---|
| Top 5 products by revenue | WARN | Laptop Pro 14: 3,991,970.22; Standing Desk: 1,592,222.04; 4K Monitor: 1,251,112.35; Office Chair: 845,025.95; Noise-Cancel Headphones: 751,200.93 |
| Top 3 sales reps by revenue | WARN | Ben Okafor: 1,355,452.03; Elif Kaya: 1,339,894.56; Dana Fischer: 1,305,044.30 |
| Bottom 3 products by quantity | WARN | Wireless Mouse: 3,023; Standing Desk: 3,120; Office Chair: 3,128 |
| Top 1 region by revenue | WARN | West: 2,719,515.16 |

### Filters

| Question | App decision | Expected answer |
|---|---|---|
| Total revenue for Electronics | ANSWER | 6,076,440.67 |
| Total revenue in the West region | ANSWER | 2,719,515.16 |
| Total revenue for Online orders in the North | ANSWER | 702,952.10 |
| Number of orders with quantity of 5 or more | ANSWER | 2,674 |
| Number of orders with revenue over 1000 | ANSWER | 2,954 |
| Total revenue for Furniture by region | ANSWER | East: 771,949.45; North: 670,441.67; South: 663,258.30; West: 753,356.19 |

### Negation, flags and missing values

| Question | App decision | Expected answer |
|---|---|---|
| How many orders were returned? | ANSWER | 777 |
| Total revenue of orders that were not returned | ANSWER | 9,483,566.49 |
| How many priority orders? | ANSWER | 1,843 |
| How many orders have not shipped? | ANSWER | 712 |
| How many orders have no customer rating? | ANSWER | 2,997 |
| Total revenue excluding Marketplace | WARN | 7,583,576.51 |

### Percentages and shares

| Question | App decision | Expected answer |
|---|---|---|
| Percentage of orders that were returned | WARN | 6.47 |
| Share of revenue by region | WARN | East: 24.34; North: 25.97; South: 22.88; West: 26.82 |
| Share of orders by sales channel | WARN | Marketplace: 24.89; Online: 25.84; Phone: 24.91; Retail Store: 24.36 |

### Formulas

| Question | App decision | Expected answer |
|---|---|---|
| Total revenue minus cost | ANSWER | 3,403,163.12 |
| Total quantity times unit price | ANSWER | 10,872,151 |
| Revenue divided by quantity | ANSWER | 262.10 |
| Total discount amount divided by revenue | ANSWER | 0.08 |

### Time

| Question | App decision | Expected answer |
|---|---|---|
| Monthly revenue by order date | WARN | 2024-01: 379,161.60; 2024-02: 404,697.59; 2024-03: 480,111.32; 2024-04: 355,638.96; 2024-05: 393,225.01; 2024-06: 482,214.52; 2024-07: 431,595.25; 2024-08: 456,509.50; 2024-09: 407,760.12; 2024-10: 447,902.43; 2024-11: 458,527.66; 2024-12: 386,396.37 |
| Total revenue for order date in 2024 | ANSWER | 5,083,740.33 |
| Yearly revenue by order date | WARN | 2024: 5,083,740.33; 2025: 5,057,543.79 |

### Distinct counts

| Question | App decision | Expected answer |
|---|---|---|
| Number of distinct products | ANSWER | 12 |
| Number of distinct sales reps | ANSWER | 8 |

## Questions where the app asks you to clarify (intended behaviour)

| Question | Why it asks |
|---|---|
| Total revenue by order date quarter | I need a clarification: words not grounded: quarter, order date |
| Number of orders ordered in March 2025 | I need a clarification: the question gives a period but not which date: order_date, ship_date. The readings give different results — order_date: 484.00; ship_da |
| Monthly revenue | I need a clarification: 'monthly' does not say which date: order_date, ship_date. The readings give different results — order_date: 24 rows; ship_date: 26 rows. |
| Total revenue in 2025 | I need a clarification: the question gives a period but not which date: order_date, ship_date. The readings give different results — order_date: 5,057,543.79; s |
| What is our profit margin? | I need a clarification: no measure could be grounded; words not grounded: profit, margin |
| Which customers are most loyal? | I need a clarification: no measure could be grounded; words not grounded: customers, loyal |
| Total revenue in the last 30 days | I can't answer this safely: relative dates (last/this/next period) are not resolved against a reference date |
| Forecast next month's revenue | This question asks for a forecast or prediction. Forecasting is not implemented in this build — I will not substitute a historical total for a future estimate.  |
| Total revenue in May | I need a clarification: 'May' has no year; which year is meant? |
| Revenue per order | I need a clarification: 'per order' would give one value per dataset_orders row; did you mean the average per order, or the overall total? |
| Delete all orders | This request looks like a destructive data operation (delete / modify / truncate). InsightFlow AI is read-only and will not execute, nor will it reinterpret the |

To get an answer, name the date column ("Monthly revenue by order date", "Total revenue for order date in 2024"), give a year with the month, or use words that are in the data.

## Phrasings the app does not understand yet (it asks instead of guessing)

| Question | Reason | Rephrase as (verified above) |
|---|---|---|
| Total quantity sold | I need a clarification: words not grounded: sold | Total quantity |
| Average discount amount for Enterprise customers | I need a clarification: words not grounded: customers | Average discount amount for Enterprise |
| Which region has the highest revenue? | I need a clarification: words not grounded: region | Top 1 region by revenue |

## Known bug: do not rely on this phrasing

| Question | App answer | Correct answer |
|---|---|---|
| Total revenue excluding Electronics and Furniture | 2,859,005.61 | 1,205,837.84 |

"Excluding A **and** B" excludes only A and then *keeps only* B. The bug is present in the evaluated (frozen) engine as well. Until it is fixed, ask "Total revenue excluding Electronics" and "Total revenue excluding Furniture" separately, or use "Total revenue by product category".
