"""Round-5 sealed schemas (H events, I manufacturing, J bank). Written after
the code freeze at dd6ea56; no implementation decision used them."""
from __future__ import annotations
import pathlib, random, sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"


def _mk(path, ddl):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    c = sqlite3.connect(str(path)); c.executescript(ddl)
    return path, c


H_DDL = """
CREATE TABLE venues (venue_id INTEGER PRIMARY KEY, venue_name TEXT NOT NULL, city TEXT NOT NULL);
CREATE TABLE artists (artist_id INTEGER PRIMARY KEY, artist_name TEXT NOT NULL, music_genre TEXT);
CREATE TABLE buyers (buyer_id INTEGER PRIMARY KEY, buyer_name TEXT NOT NULL, membership TEXT);
CREATE TABLE events (event_id INTEGER PRIMARY KEY, event_name TEXT NOT NULL, venue_id INTEGER REFERENCES venues(venue_id),
  artist_id INTEGER REFERENCES artists(artist_id), event_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE tickets (ticket_id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(event_id),
  buyer_id INTEGER REFERENCES buyers(buyer_id), purchased_on TEXT NOT NULL, price REAL NOT NULL, refunded INTEGER NOT NULL);
"""


def build_h(path=None):
    path, c = _mk(path or DATA / "events.db", H_DDL)
    rng = random.Random(777)
    c.executemany("INSERT INTO venues VALUES (?,?,?)", [(1, "The Grand Hall", "Chicago"), (2, "Blue Note Café", "New York"),
        (3, "Sunset Amphitheater", "Los Angeles"), (4, "Old Mill Barn", "Chicago"), (5, "Harbor Dome", "Seattle")])  # 5 unused
    c.executemany("INSERT INTO artists VALUES (?,?,?)", [(1, "The Rolling Pins", "Rock"), (2, "DJ Álvaro", "Electronic"),
        (3, "Miles & the Quartet", "Jazz"), (4, "Anna K.", None), (5, "O'Malley Brothers", "Folk")])
    c.executemany("INSERT INTO buyers VALUES (?,?,?)", [(i, f"Buyer {i:03d}", rng.choice(["VIP", "Standard", None])) for i in range(1, 81)])
    evs = []
    for e in range(1, 31):
        evs.append((e, f"Show {e:02d}", rng.choice([1, 2, 3, 4]), rng.randint(1, 5),
                    f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", rng.choice(["Held", "Held", "Cancelled", "Scheduled"])))
    c.executemany("INSERT INTO events VALUES (?,?,?,?,?,?)", evs)
    tk = []
    for t in range(1, 601):
        tk.append((t, rng.randint(1, 30), None if rng.random() < 0.1 else rng.randint(1, 80),
                   f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", round(rng.uniform(15, 220), 2), 1 if rng.random() < 0.08 else 0))
    c.executemany("INSERT INTO tickets VALUES (?,?,?,?,?,?)", tk)
    c.commit(); c.close(); return path


I_DDL = """
CREATE TABLE plants (plant_id INTEGER PRIMARY KEY, plant_name TEXT NOT NULL, country TEXT NOT NULL);
CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, product_family TEXT NOT NULL);
CREATE TABLE machines (machine_id INTEGER PRIMARY KEY, machine_label TEXT NOT NULL, plant_id INTEGER NOT NULL);
CREATE TABLE work_orders (wo_id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, machine_id INTEGER NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, units_planned INTEGER NOT NULL, units_good INTEGER NOT NULL, units_scrap INTEGER);
CREATE TABLE defects (defect_id INTEGER PRIMARY KEY, wo_id INTEGER NOT NULL, defect_type TEXT NOT NULL, severity INTEGER NOT NULL);
"""


def build_i(path=None):
    path, c = _mk(path or DATA / "factory.db", I_DDL)
    rng = random.Random(909)
    c.executemany("INSERT INTO plants VALUES (?,?,?)", [(1, "Plant Alpha", "Germany"), (2, "Plant Beta (East)", "Poland"),
        (3, "Plant Gamma", "Mexico"), (4, "Plant Delta", "Vietnam")])        # 4 has a machine, no work
    c.executemany("INSERT INTO products VALUES (?,?,?)", [(1, "Widget A-100", "Widgets"), (2, "Widget B-200", "Widgets"),
        (3, "Gizmo X", "Gizmos"), (4, "Gear 5\" Heavy", "Gears"), (5, "Gear 3\" Light", "Gears")])
    c.executemany("INSERT INTO machines VALUES (?,?,?)", [(1, "Press 1", 1), (2, "Press 2", 1), (3, "Lathe 1", 2),
        (4, "Mill 1", 3), (5, "Mill 2", 3), (6, "Idle Robot", 4)])
    wo = []
    for w in range(1, 401):
        planned = rng.randint(50, 500); good = int(planned * rng.uniform(0.8, 1.0))
        scrap = None if rng.random() < 0.2 else planned - good
        m = rng.randint(1, 5)
        st = f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 27):02d} {rng.randint(0, 23):02d}:00:00"
        fin = None if rng.random() < 0.15 else st.replace(" ", "T")[:10] + " 23:59:59"
        wo.append((w, rng.randint(1, 5), m, st, fin, planned, good, scrap))
    c.executemany("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?)", wo)
    c.executemany("INSERT INTO defects VALUES (?,?,?,?)", [
        (d, rng.randint(1, 400), rng.choice(["Crack", "Burr", "Misalignment", "Discoloration"]), rng.randint(1, 5)) for d in range(1, 301)])
    c.commit(); c.close(); return path


J_DDL = """
CREATE TABLE branches (branch_code TEXT PRIMARY KEY, branch_name TEXT NOT NULL, region TEXT NOT NULL);
CREATE TABLE customers (cust_no INTEGER PRIMARY KEY, full_name TEXT NOT NULL, segment TEXT, home_branch TEXT);
CREATE TABLE accounts (acct_id INTEGER PRIMARY KEY, cust_no INTEGER NOT NULL, acct_type TEXT NOT NULL,
  opened_on TEXT NOT NULL, closed_on TEXT, balance REAL NOT NULL);
CREATE TABLE transactions (txn_id INTEGER PRIMARY KEY, acct_id INTEGER NOT NULL, txn_date TEXT NOT NULL,
  amount REAL NOT NULL, txn_type TEXT NOT NULL, channel TEXT);
"""


def build_j(path=None):
    path, c = _mk(path or DATA / "bank.db", J_DDL)
    rng = random.Random(1212)
    c.executemany("INSERT INTO branches VALUES (?,?,?)", [("NYC1", "Wall Street Branch", "Northeast"), ("BOS2", "Back Bay", "Northeast"),
        ("SFO3", "Mission & 3rd", "West"), ("AUS4", "Congress Ave", "South"), ("DEN5", "Closed Branch", "West")])  # DEN5 empty
    c.executemany("INSERT INTO customers VALUES (?,?,?,?)", [
        (i, f"Customer {i:03d}", rng.choice(["Premier", "Basic", None]), rng.choice(["NYC1", "BOS2", "SFO3", "AUS4", None])) for i in range(1, 61)])
    c.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?)", [
        (a, rng.randint(1, 60), rng.choice(["Checking", "Savings", "Money Market"]), f"{rng.choice([2022, 2023, 2024])}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
         None if rng.random() < 0.85 else "2025-02-01", round(rng.uniform(100, 50000), 2)) for a in range(1, 101)])
    c.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?)", [
        (t, rng.randint(1, 100), f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", round(rng.uniform(5, 3000), 2),
         rng.choice(["Deposit", "Withdrawal", "Fee", "Transfer"]), rng.choice(["ATM", "Online", "Branch", None])) for t in range(1, 801)])
    c.commit(); c.close(); return path


if __name__ == "__main__":
    print(build_h(), build_i(), build_j())
