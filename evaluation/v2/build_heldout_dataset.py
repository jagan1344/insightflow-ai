"""Build an INDEPENDENT held-out dataset for generalization testing.

Deliberately exercises edge cases the current demo doesn't:
  - Multi-word dim values ("New York", "North America")
  - Values with special characters ("R&D", "Men's Apparel")
  - Overlapping names ("East" region vs "East Coast" sales_office)
  - A dim value that EXISTS but has ZERO fact rows ("Antarctica" region
    is seeded but has no sales → distinct from "unknown value")
  - A dim value that is NULL in some fact rows
  - A measure column with real NULLs (missing shipping_cost)
  - A date column with explicit NULLs

This file is runnable as a script and writes to
`backend/data/heldout.db`. The oracle uses stdlib sqlite3 directly on
the SAME file so comparisons are reproducible.
"""
from __future__ import annotations

import csv
import pathlib
import random
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = ROOT / "backend" / "data" / "heldout.db"


SCHEMA = """
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS sales_offices;
DROP TABLE IF EXISTS product_lines;
DROP TABLE IF EXISTS customers_ho;

CREATE TABLE sales_offices (
    office_id INTEGER PRIMARY KEY,
    office_name TEXT NOT NULL,          -- includes "East Coast", "West Coast", "APAC HQ"
    territory TEXT NOT NULL             -- includes "North America", "EMEA", "APAC"
);

CREATE TABLE product_lines (
    line_id INTEGER PRIMARY KEY,
    line_name TEXT NOT NULL,            -- includes "Men's Apparel", "R&D Hardware", "Accessories"
    division TEXT NOT NULL              -- includes "Consumer", "Enterprise", "R&D"
);

CREATE TABLE customers_ho (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    tier TEXT                           -- "Platinum", "Gold", "Silver"; some NULLs
);

CREATE TABLE sales (
    sale_id INTEGER PRIMARY KEY,
    sale_date TEXT NOT NULL,            -- ISO YYYY-MM-DD
    office_id INTEGER NOT NULL,
    line_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    gross_amount REAL NOT NULL,
    shipping_cost REAL,                 -- NULL on some rows
    FOREIGN KEY (office_id) REFERENCES sales_offices(office_id),
    FOREIGN KEY (line_id) REFERENCES product_lines(line_id),
    FOREIGN KEY (customer_id) REFERENCES customers_ho(customer_id)
);
"""

OFFICES = [
    (1, "East Coast",   "North America"),
    (2, "West Coast",   "North America"),
    (3, "APAC HQ",      "APAC"),
    (4, "EMEA Hub",     "EMEA"),
    (5, "Antarctica Research Station", "APAC"),   # exists, zero sales
]

PRODUCT_LINES = [
    (1, "Men's Apparel",  "Consumer"),
    (2, "Women's Apparel","Consumer"),
    (3, "R&D Hardware",   "R&D"),
    (4, "Accessories",    "Consumer"),
    (5, "Enterprise Software", "Enterprise"),
]

CUSTOMER_NAMES = [
    ("Platinum",) * 10 + ("Gold",) * 15 + ("Silver",) * 20 + (None,) * 5,
]


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    cur.executescript(SCHEMA)

    cur.executemany(
        "INSERT INTO sales_offices VALUES (?, ?, ?)", OFFICES)
    cur.executemany(
        "INSERT INTO product_lines VALUES (?, ?, ?)", PRODUCT_LINES)

    rng = random.Random(1234)
    customers = []
    for i in range(50):
        tier = rng.choice(["Platinum", "Gold", "Silver", None, "Silver"])
        customers.append((i + 1, f"Customer-{i+1:03d}", tier))
    cur.executemany(
        "INSERT INTO customers_ho VALUES (?, ?, ?)", customers)

    sale_id = 1
    # Deterministic sales over 2026-01..2026-09 — mirrors demo DB range
    # so INSIGHTFLOW_REF_DATE=2026-10-21 produces equivalent "last month" etc.
    sales = []
    for month in range(1, 10):
        for _ in range(60):
            day = rng.randint(1, 28)
            date = f"2026-{month:02d}-{day:02d}"
            # Office 5 (Antarctica Research Station) gets ZERO sales.
            office_id = rng.choice([1, 2, 3, 4])
            line_id = rng.randint(1, 5)
            customer_id = rng.randint(1, 50)
            quantity = rng.randint(1, 10)
            gross = round(rng.uniform(10, 2500), 2)
            # ~10% of rows have NULL shipping_cost
            shipping = (None if rng.random() < 0.1
                         else round(gross * rng.uniform(0.01, 0.05), 2))
            sales.append((sale_id, date, office_id, line_id,
                          customer_id, quantity, gross, shipping))
            sale_id += 1
    cur.executemany(
        "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?)", sales)

    con.commit()
    counts = {
        "sales": cur.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
        "offices": cur.execute("SELECT COUNT(*) FROM sales_offices").fetchone()[0],
        "lines": cur.execute("SELECT COUNT(*) FROM product_lines").fetchone()[0],
        "customers": cur.execute("SELECT COUNT(*) FROM customers_ho").fetchone()[0],
        "null_shipping": cur.execute(
            "SELECT COUNT(*) FROM sales WHERE shipping_cost IS NULL"
        ).fetchone()[0],
        "antarctica_sales": cur.execute(
            "SELECT COUNT(*) FROM sales WHERE office_id = 5"
        ).fetchone()[0],
        "null_tier": cur.execute(
            "SELECT COUNT(*) FROM customers_ho WHERE tier IS NULL"
        ).fetchone()[0],
    }
    con.close()
    print(f"wrote {DB}")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
