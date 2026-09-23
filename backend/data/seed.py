"""Build and seed the InsightFlow demo SQLite database.

Deterministic: uses random.Random(42). Generates ~220 orders per month for
Jan-Sep 2026, scaled by a monthly factor that engineers a clear revenue dip
in July 2026 concentrated in the East region and Furniture category.

Usage:
    python data/seed.py
"""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema.sql"
DB_PATH = ROOT / "insightflow.db"


REGIONS = ["North", "South", "East", "West"]
CATEGORIES = {
    "Electronics": ["Laptop", "Monitor", "Headphones"],
    "Furniture":   ["Desk", "Chair", "Bookshelf"],
    "Office":      ["Notebook", "Pen Set", "Stapler"],
    "Software":    ["OS License", "Office Suite", "Antivirus"],
}
SEGMENTS = ["SMB", "Enterprise", "Consumer"]

# Price/cost bands per category (unit price range, cost fraction)
PRICE_BANDS = {
    "Electronics": (400, 1600, 0.70),
    "Furniture":   (150, 900,  0.65),
    "Office":      (5,   80,   0.55),
    "Software":    (50,  600,  0.35),
}

# Monthly demand factor (2026). July engineered to drop — driven mostly
# by heavy targeted suppression of Furniture + East (see loop below).
MONTH_FACTOR = {
    1: 1.00, 2: 0.95, 3: 1.05, 4: 1.10, 5: 1.15,
    6: 1.20, 7: 0.90,  # <-- flat July effect is mild; the targeted drops do the work
    8: 1.15, 9: 1.10,
}

ORDERS_PER_MONTH_BASE = 220


def month_days(year: int, month: int) -> list[date]:
    d = date(year, month, 1)
    days = []
    while d.month == month:
        days.append(d)
        d += timedelta(days=1)
    return days


def build() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    rng = random.Random(42)

    # regions
    region_rows = [(i + 1, name) for i, name in enumerate(REGIONS)]
    conn.executemany("INSERT INTO regions(region_id, region_name) VALUES (?,?)", region_rows)

    # products
    product_rows = []
    pid = 1
    for cat, names in CATEGORIES.items():
        for name in names:
            product_rows.append((pid, name, cat))
            pid += 1
    conn.executemany(
        "INSERT INTO products(product_id, product_name, category) VALUES (?,?,?)",
        product_rows,
    )

    # customers ~60
    customer_rows = []
    for cid in range(1, 61):
        region_id = rng.randint(1, len(REGIONS))
        segment = rng.choice(SEGMENTS)
        customer_rows.append((cid, f"Customer {cid:03d}", region_id, segment))
    conn.executemany(
        "INSERT INTO customers(customer_id, customer_name, region_id, segment) VALUES (?,?,?,?)",
        customer_rows,
    )

    # orders
    products_by_id = {pid: (name, cat) for pid, name, cat in product_rows}
    customers_by_id = {cid: (name, rid, seg) for cid, name, rid, seg in customer_rows}
    product_ids = list(products_by_id.keys())
    customer_ids = list(customers_by_id.keys())

    order_rows = []
    oid = 1
    for month, factor in MONTH_FACTOR.items():
        n_orders = int(ORDERS_PER_MONTH_BASE * factor)
        days = month_days(2026, month)
        for _ in range(n_orders):
            d = rng.choice(days)
            product_id = rng.choice(product_ids)
            _, cat = products_by_id[product_id]

            # In July, extra-suppress Furniture and East region orders
            customer_id = rng.choice(customer_ids)
            _, region_id, _ = customers_by_id[customer_id]

            if month == 7:
                # Heavy targeted suppression so Furniture and East drive the dip.
                if cat == "Furniture" and rng.random() < 0.80:
                    continue
                if region_id == 3 and rng.random() < 0.65:
                    continue

            lo, hi, cost_frac = PRICE_BANDS[cat]
            unit_price = rng.uniform(lo, hi)
            qty = rng.randint(1, 6)

            revenue = round(unit_price * qty, 2)
            cost = round(revenue * cost_frac * rng.uniform(0.95, 1.05), 2)
            discount = round(revenue * rng.uniform(0.0, 0.08), 2)

            order_rows.append((
                oid, customer_id, product_id, region_id,
                d.isoformat(), qty, revenue, cost, discount,
            ))
            oid += 1

    conn.executemany(
        "INSERT INTO orders(order_id, customer_id, product_id, region_id, "
        "order_date, quantity, revenue, cost, discount) VALUES (?,?,?,?,?,?,?,?,?)",
        order_rows,
    )

    conn.commit()

    # verification
    cur = conn.execute("SELECT COUNT(*) FROM orders")
    n = cur.fetchone()[0]
    print(f"Seeded {DB_PATH}  ({n} orders, {len(customer_rows)} customers, "
          f"{len(product_rows)} products, {len(region_rows)} regions)")

    print("\nMonthly revenue (2026):")
    cur = conn.execute(
        "SELECT substr(order_date,1,7) AS m, ROUND(SUM(revenue),2) "
        "FROM orders GROUP BY m ORDER BY m"
    )
    for m, rev in cur.fetchall():
        print(f"  {m}: {rev:>12,.2f}")

    conn.close()


if __name__ == "__main__":
    build()
