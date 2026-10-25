"""Round-6 sealed schemas: airline (abbreviated column names, 0/1 flags,
role-playing airports), saas (billing, trial flag, two own dates, fan-out child),
farm (sensor readings + harvests, NULL sensors, zero-activity farm).
Written after the backend freeze at 78d906b."""
from __future__ import annotations
import pathlib, random, sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"


def _mk(path, ddl):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.unlink(missing_ok=True)
    c = sqlite3.connect(str(path)); c.executescript(ddl); return path, c


AIR = """
CREATE TABLE airports (apt_cd TEXT PRIMARY KEY, apt_nm TEXT NOT NULL, ctry TEXT NOT NULL);
CREATE TABLE carriers (carr_cd TEXT PRIMARY KEY, carr_nm TEXT NOT NULL, alliance TEXT);
CREATE TABLE flights (flt_id INTEGER PRIMARY KEY, carr_cd TEXT NOT NULL, orig_cd TEXT NOT NULL, dest_cd TEXT NOT NULL,
  dep_dt TEXT NOT NULL, arr_dt TEXT, pax_cnt INTEGER NOT NULL, fare_amt REAL NOT NULL, is_cancelled INTEGER NOT NULL, is_delayed INTEGER NOT NULL);
"""


def build_air(path=None):
    path, c = _mk(path or DATA / "airline.db", AIR)
    rng = random.Random(2468)
    apts = [("JFK", "John F. Kennedy Intl", "USA"), ("LHR", "London Heathrow", "UK"), ("NRT", "Narita", "Japan"),
            ("CDG", "Paris Charles de Gaulle", "France"), ("SYD", "Sydney Kingsford Smith", "Australia"), ("XXX", "Unused Airstrip", "Nowhere")]
    c.executemany("INSERT INTO airports VALUES (?,?,?)", apts)
    c.executemany("INSERT INTO carriers VALUES (?,?,?)", [("AA", "American Air", "Oneworld"), ("BA", "British Skies", "Oneworld"),
        ("JL", "Japan Wings", "Oneworld"), ("AF", "Air France-KLM", "SkyTeam"), ("QF", "Qantas & Co.", None), ("ZZ", "Ghost Air", None)])
    fl = []
    codes = ["JFK", "LHR", "NRT", "CDG", "SYD"]
    for f in range(1, 701):
        o, d = rng.sample(codes, 2)
        m = rng.randint(1, 12); day = rng.randint(1, 27)
        canc = 1 if rng.random() < 0.07 else 0
        fl.append((f, rng.choice(["AA", "BA", "JL", "AF", "QF"]), o, d, f"2025-{m:02d}-{day:02d} {rng.randint(0, 23):02d}:15:00",
                   None if canc else f"2025-{m:02d}-{day:02d} 23:59:00", rng.randint(0, 300), round(rng.uniform(80, 1800), 2),
                   canc, 1 if rng.random() < 0.2 else 0))
    c.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?)", fl)
    c.commit(); c.close(); return path


SAAS = """
CREATE TABLE plans (plan_id INTEGER PRIMARY KEY, plan_name TEXT NOT NULL, monthly_price REAL NOT NULL);
CREATE TABLE accounts (acct_id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, industry TEXT, country TEXT NOT NULL);
CREATE TABLE subscriptions (sub_id INTEGER PRIMARY KEY, acct_id INTEGER NOT NULL REFERENCES accounts(acct_id),
  plan_id INTEGER NOT NULL REFERENCES plans(plan_id), started TEXT NOT NULL, ended TEXT, seats INTEGER NOT NULL, is_trial INTEGER NOT NULL);
CREATE TABLE invoices (inv_id INTEGER PRIMARY KEY, sub_id INTEGER NOT NULL REFERENCES subscriptions(sub_id),
  issued_on TEXT NOT NULL, paid_on TEXT, total_usd REAL NOT NULL);
CREATE TABLE support_tickets (tk_id INTEGER PRIMARY KEY, acct_id INTEGER NOT NULL REFERENCES accounts(acct_id),
  opened_on TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL);
"""


def build_saas(path=None):
    path, c = _mk(path or DATA / "saas.db", SAAS)
    rng = random.Random(1357)
    c.executemany("INSERT INTO plans VALUES (?,?,?)", [(1, "Starter", 29.0), (2, "Team", 99.0), (3, "Enterprise (Annual)", 499.0), (4, "Legacy", 15.0)])
    c.executemany("INSERT INTO accounts VALUES (?,?,?,?)", [(i, f"Company {i:02d}", rng.choice(["Software", "Retail", "Health", None]),
        rng.choice(["USA", "Germany", "India", "Brazil"])) for i in range(1, 41)])
    subs = []
    for s in range(1, 81):
        subs.append((s, rng.randint(1, 40), rng.choice([1, 2, 3]), f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                     None if rng.random() < 0.8 else "2025-03-31", rng.randint(1, 50), 1 if rng.random() < 0.15 else 0))
    c.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?)", subs)
    inv = []
    for i in range(1, 501):
        m = rng.randint(1, 12)
        inv.append((i, rng.randint(1, 80), f"2025-{m:02d}-{rng.randint(1, 20):02d}",
                    None if rng.random() < 0.2 else f"2025-{m:02d}-{rng.randint(21, 28):02d}", round(rng.uniform(10, 5000), 2)))
    c.executemany("INSERT INTO invoices VALUES (?,?,?,?,?)", inv)
    c.executemany("INSERT INTO support_tickets VALUES (?,?,?,?,?)", [
        (t, rng.randint(1, 40), f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", rng.choice(["High", "Low", "Medium"]),
         rng.choice(["Open", "Closed", "Pending"])) for t in range(1, 121)])
    c.commit(); c.close(); return path


FARM = """
CREATE TABLE farms (farm_id INTEGER PRIMARY KEY, farm_name TEXT NOT NULL, region TEXT NOT NULL);
CREATE TABLE fields (field_id INTEGER PRIMARY KEY, farm_id INTEGER NOT NULL REFERENCES farms(farm_id), crop TEXT NOT NULL, acres REAL NOT NULL);
CREATE TABLE readings (rd_id INTEGER PRIMARY KEY, field_id INTEGER NOT NULL REFERENCES fields(field_id),
  taken_at TEXT NOT NULL, moisture REAL NOT NULL, temp_c REAL, sensor_ok INTEGER NOT NULL);
CREATE TABLE harvests (hv_id INTEGER PRIMARY KEY, field_id INTEGER NOT NULL REFERENCES fields(field_id),
  harvest_date TEXT NOT NULL, yield_tons REAL NOT NULL);
"""


def build_farm(path=None):
    path, c = _mk(path or DATA / "farm.db", FARM)
    rng = random.Random(8642)
    c.executemany("INSERT INTO farms VALUES (?,?,?)", [(1, "Sunny Acres", "Midwest"), (2, "O'Neil Family Farm", "South"),
        (3, "Riverbend (North)", "Midwest"), (4, "Fallow Ridge", "West")])        # 4 has no fields in use
    c.executemany("INSERT INTO fields VALUES (?,?,?,?)", [(1, 1, "Corn", 120.5), (2, 1, "Soy", 80.0), (3, 2, "Cotton", 200.0),
        (4, 3, "Corn", 95.0), (5, 3, "Wheat", 60.0), (6, 4, "Fallow", 30.0)])
    rd = []
    for r in range(1, 901):
        rd.append((r, rng.randint(1, 5), f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 27):02d} {rng.randint(0, 23):02d}:00:00",
                   round(rng.uniform(5, 45), 1), None if rng.random() < 0.15 else round(rng.uniform(-5, 38), 1), 0 if rng.random() < 0.1 else 1))
    c.executemany("INSERT INTO readings VALUES (?,?,?,?,?,?)", rd)
    c.executemany("INSERT INTO harvests VALUES (?,?,?,?)", [(h, rng.randint(1, 5), f"2025-{rng.randint(6, 11):02d}-{rng.randint(1, 28):02d}",
        round(rng.uniform(5, 90), 2)) for h in range(1, 61)])
    c.commit(); c.close(); return path


if __name__ == "__main__":
    print(build_air(), build_saas(), build_farm())
