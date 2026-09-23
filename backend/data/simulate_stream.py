"""Standalone live-data simulator.

Inserts a small batch of realistic orders every few seconds so any
connected dashboard updates in real time. Run this in a second terminal
while `uvicorn api.main:app` and the frontend are up.

    python data/simulate_stream.py --rate 2 --batch 3

Press Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

# Make backend/insightflow importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from insightflow.execution.executor import get_engine


PRICE_BANDS = {
    "Electronics": (400, 1600, 0.70),
    "Furniture":   (150, 900,  0.65),
    "Office":      (5,   80,   0.55),
    "Software":    (50,  600,  0.35),
}


def run(rate: float, batch: int, seed: int = 1234) -> None:
    rng = random.Random(seed)
    engine = get_engine()
    with engine.connect() as conn:
        customer_ids = [r[0] for r in conn.execute(text(
            "SELECT customer_id FROM customers")).fetchall()]
        products = [(r[0], r[1]) for r in conn.execute(text(
            "SELECT product_id, category FROM products")).fetchall()]
        customers = {r[0]: r[1] for r in conn.execute(text(
            "SELECT customer_id, region_id FROM customers")).fetchall()}

    print(f"Streaming ~{batch} orders every {rate}s. Ctrl-C to stop.", flush=True)
    inserted = 0
    try:
        while True:
            with engine.begin() as conn:
                for _ in range(batch):
                    cust = rng.choice(customer_ids)
                    pid, cat = rng.choice(products)
                    region_id = customers[cust]
                    lo, hi, cost_frac = PRICE_BANDS.get(cat, (10, 100, 0.5))
                    unit_price = rng.uniform(lo, hi)
                    qty = rng.randint(1, 6)
                    revenue = round(unit_price * qty, 2)
                    cost = round(revenue * cost_frac * rng.uniform(0.95, 1.05), 2)
                    discount = round(revenue * rng.uniform(0.0, 0.08), 2)
                    conn.execute(text(
                        "INSERT INTO orders(customer_id, product_id, region_id, "
                        "order_date, quantity, revenue, cost, discount) "
                        "VALUES (:c,:p,:r,'2026-09-30',:q,:rev,:cost,:disc)"
                    ), {"c": cust, "p": pid, "r": region_id,
                        "q": qty, "rev": revenue, "cost": cost, "disc": discount})
                    inserted += 1
            print(f"inserted total={inserted}", flush=True)
            time.sleep(rate)
    except KeyboardInterrupt:
        print(f"\nStopped after {inserted} inserts.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=2.0, help="seconds between batches")
    ap.add_argument("--batch", type=int, default=3, help="orders per batch")
    args = ap.parse_args()
    run(args.rate, args.batch)
