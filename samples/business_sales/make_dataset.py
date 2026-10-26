"""Generate sales_orders.csv: 12,000 synthetic e-commerce order rows (seeded, reproducible).
usage: python make_dataset.py   (writes sales_orders.csv next to this script)"""
import csv, datetime as dt, pathlib, random

rng = random.Random(20251026)
OUT = pathlib.Path(__file__).resolve().parent / "sales_orders.csv"
REGIONS = {"North": 1.1, "South": 0.9, "East": 1.0, "West": 1.2}
CHANNELS = ["Online", "Retail Store", "Marketplace", "Phone"]
SEGMENTS = ["Consumer", "Small Business", "Enterprise"]
REPS = ["Alice Moreno", "Ben Okafor", "Chen Wei", "Dana Fischer", "Elif Kaya", "Farah Haddad", "Gus Lindqvist", "Hana Sato"]
PRODUCTS = {  # name: (category, unit price, unit cost)
    "Laptop Pro 14": ("Electronics", 1299.0, 910.0), "Wireless Mouse": ("Electronics", 29.0, 11.0),
    "4K Monitor": ("Electronics", 399.0, 250.0), "Noise-Cancel Headphones": ("Electronics", 249.0, 140.0),
    "Office Chair": ("Furniture", 289.0, 160.0), "Standing Desk": ("Furniture", 549.0, 330.0),
    "Bookshelf": ("Furniture", 139.0, 70.0), "Printer Paper (box)": ("Office Supplies", 39.0, 18.0),
    "Gel Pens (12)": ("Office Supplies", 12.0, 4.0), "Desk Organizer": ("Office Supplies", 24.0, 9.0),
    "Coffee Maker": ("Appliances", 119.0, 64.0), "Air Purifier": ("Appliances", 199.0, 105.0),
}
NAMES = list(PRODUCTS)

rows = []
start = dt.date(2024, 1, 1)
for i in range(1, 12001):
    d = start + dt.timedelta(days=rng.randint(0, 730))           # 2024-01-01 .. 2025-12-31
    if d.month in (11, 12) and rng.random() < 0.3:                 # a little seasonality
        d = d.replace(day=min(28, d.day))
    prod = rng.choice(NAMES); cat, price, cost = PRODUCTS[prod]
    region = rng.choice(list(REGIONS))
    qty = rng.choice([1, 1, 1, 2, 2, 3, 4, 5, 10])
    disc_rate = rng.choice([0, 0, 0, 0.05, 0.10, 0.15, 0.20])
    gross = round(qty * price * REGIONS[region] ** 0.1, 2)
    discount = round(gross * disc_rate, 2)
    revenue = round(gross - discount, 2)
    shipped = rng.random() > 0.06
    ship = d + dt.timedelta(days=rng.randint(1, 7)) if shipped else None
    rows.append({
        "order_id": i, "order_date": d.isoformat(), "ship_date": ship.isoformat() if ship else "",
        "region": region, "sales_channel": rng.choice(CHANNELS), "customer_segment": rng.choice(SEGMENTS),
        "sales_rep": rng.choice(REPS), "product_category": cat, "product_name": prod,
        "quantity": qty, "unit_price": price, "discount_amount": discount, "revenue": revenue,
        "cost": round(qty * cost, 2), "shipping_fee": rng.choice([0.0, 4.99, 9.99, 19.99]),
        "is_returned": int(shipped and rng.random() < 0.07), "is_priority": int(rng.random() < 0.15),
        "customer_rating": rng.choice([1, 2, 3, 3, 4, 4, 4, 5, 5, 5]) if rng.random() > 0.25 else "",
    })
with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f"wrote {OUT} ({len(rows)} rows)")
