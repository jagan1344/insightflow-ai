"""Development databases for the architecture-recovery work (written by the developer; NOT independent evidence).
Four domains not used in any earlier evaluation: bike sharing, school exams, e-commerce orders, support tickets.
Each has role-playing lookups, one-to-many children, flags of both polarities, NULLs, several date columns and
abbreviated names. `scheme="full"` renames abbreviated columns to spelled-out names (metamorphic variant)."""
from __future__ import annotations

import pathlib
import random
import sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"

RENAME = {  # abbreviated -> spelled-out (metamorphic variant; same data)
    "bikes": {"start_stn_id": "start_station_id", "end_stn_id": "end_station_id", "dur_min": "duration_minutes",
              "dist_km": "distance_km", "fare_amt": "fare_amount", "per_min_rate": "per_minute_rate", "stn_nm": "station_name",
              "dock_cap": "dock_capacity", "rdr_id": "rider_id", "rdr_nm": "rider_name"},
    "school": {"score_pct": "score_percent", "pts_earned": "points_earned", "pts_possible": "points_possible",
               "crs_cd": "course_code", "crs_title": "course_title", "credit_hrs": "credit_hours", "stu_nm": "student_name",
               "tchr_nm": "teacher_name"},
    "shop": {"gross_amt": "gross_amount", "disc_amt": "discount_amount", "ship_fee": "shipping_fee", "refund_amt": "refund_amount",
             "unit_prc": "unit_price", "qty": "quantity", "cust_nm": "customer_name", "ship_dt": "ship_date", "order_dt": "order_date"},
    "support": {"csat_score": "satisfaction_score", "reopen_cnt": "reopen_count", "arr_usd": "annual_revenue_usd",
                "acct_nm": "account_name", "agent_nm": "agent_name", "opened_ts": "opened_at", "closed_ts": "closed_at"},
}


def _mk(name, ddl, scheme):
    DATA.mkdir(exist_ok=True)
    if scheme == "full":
        for a, b in sorted(RENAME[name].items(), key=lambda kv: -len(kv[0])):
            ddl = ddl.replace(a, b)
    p = DATA / f"{name}{'' if scheme == 'abbr' else '_full'}.db"
    p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript(ddl)
    return p, c


def build_bikes(scheme="abbr"):
    p, c = _mk("bikes", """
    CREATE TABLE stations (station_id INTEGER PRIMARY KEY, stn_nm TEXT NOT NULL, district TEXT, dock_cap INTEGER NOT NULL);
    CREATE TABLE bikes (bike_id INTEGER PRIMARY KEY, bike_type TEXT NOT NULL, model_yr INTEGER NOT NULL, in_service INTEGER NOT NULL);
    CREATE TABLE riders (rdr_id INTEGER PRIMARY KEY, rdr_nm TEXT NOT NULL, plan_type TEXT, signup_dt TEXT NOT NULL);
    CREATE TABLE rentals (rental_id INTEGER PRIMARY KEY, bike_id INTEGER NOT NULL REFERENCES bikes(bike_id),
        rdr_id INTEGER REFERENCES riders(rdr_id), start_stn_id INTEGER NOT NULL, end_stn_id INTEGER,
        start_ts TEXT NOT NULL, end_ts TEXT, dur_min INTEGER NOT NULL, dist_km REAL NOT NULL, per_min_rate REAL NOT NULL,
        fare_amt REAL NOT NULL, helmet_used INTEGER NOT NULL, gps_ok INTEGER NOT NULL);
    CREATE TABLE rental_issues (issue_id INTEGER PRIMARY KEY, rental_id INTEGER NOT NULL REFERENCES rentals(rental_id),
        issue_type TEXT NOT NULL, resolved INTEGER NOT NULL);
    """, scheme)
    rng = random.Random(911)
    st = [(1, "Harbor Point", "Waterfront", 20), (2, "Old Mill Sq", "Downtown", 15), (3, "Union & 5th", "Downtown", 25),
          (4, "Elm Park", "Northside", 12), (5, "Rail Yard (East)", None, 18), (6, "Closed Depot", "Northside", 10)]
    c.executemany("INSERT INTO stations VALUES (?,?,?,?)", st)
    bikes = [(i, rng.choice(["electric", "classic", "cargo"]), rng.choice([2021, 2022, 2023, 2024]), int(rng.random() > 0.1)) for i in range(1, 61)]
    c.executemany("INSERT INTO bikes VALUES (?,?,?,?)", bikes)
    riders = [(i, f"Rider {i:03d}", rng.choice(["annual", "monthly", "pay-as-you-go", None]), f"{rng.choice([2023, 2024, 2025])}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}") for i in range(1, 151)]
    c.executemany("INSERT INTO riders VALUES (?,?,?,?)", riders)
    rent, iss, k = [], [], 0
    for r in range(1, 901):
        m = rng.randint(1, 12); d = rng.randint(1, 26); h = rng.randint(6, 21)
        dur = rng.randint(3, 75); s = rng.randint(1, 5); e = None if rng.random() < 0.06 else rng.randint(1, 5)
        rate = rng.choice([0.15, 0.2, 0.25])
        end_ts = None if e is None else f"2025-{m:02d}-{d + (1 if h + dur // 60 >= 24 else 0):02d} {min(23, h + dur // 60):02d}:30:00"
        rent.append((r, rng.randint(1, 60), None if rng.random() < 0.12 else rng.randint(1, 150), s, e,
                     f"2025-{m:02d}-{d:02d} {h:02d}:05:00", end_ts, dur, round(dur * rng.uniform(0.15, 0.3), 2), rate,
                     round(1.0 + dur * rate, 2), int(rng.random() < 0.55), int(rng.random() > 0.08)))
        for _ in range(rng.choice([0, 0, 0, 0, 1, 1, 2])):
            k += 1
            iss.append((k, r, rng.choice(["flat tire", "brake", "lock", "app"]), int(rng.random() < 0.7)))
    c.executemany("INSERT INTO rentals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rent)
    c.executemany("INSERT INTO rental_issues VALUES (?,?,?,?)", iss)
    c.commit(); c.close(); return p


def build_school(scheme="abbr"):
    p, c = _mk("school", """
    CREATE TABLE students (student_id INTEGER PRIMARY KEY, stu_nm TEXT NOT NULL, grade_lvl INTEGER NOT NULL, homeroom TEXT, is_ell INTEGER NOT NULL);
    CREATE TABLE courses (crs_cd TEXT PRIMARY KEY, crs_title TEXT NOT NULL, dept TEXT NOT NULL, credit_hrs REAL NOT NULL);
    CREATE TABLE teachers (teacher_id INTEGER PRIMARY KEY, tchr_nm TEXT NOT NULL, dept TEXT NOT NULL);
    CREATE TABLE exam_results (result_id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(student_id),
        crs_cd TEXT NOT NULL REFERENCES courses(crs_cd), grader_id INTEGER NOT NULL, proctor_id INTEGER,
        exam_dt TEXT NOT NULL, graded_dt TEXT, score_pct REAL, pts_earned REAL, pts_possible REAL NOT NULL,
        is_retake INTEGER NOT NULL, absent INTEGER NOT NULL);
    CREATE TABLE accommodations (accom_id INTEGER PRIMARY KEY, result_id INTEGER NOT NULL REFERENCES exam_results(result_id), accom_type TEXT NOT NULL);
    """, scheme)
    rng = random.Random(4242)
    c.executemany("INSERT INTO students VALUES (?,?,?,?,?)", [(i, f"Student {i:03d}", rng.choice([9, 10, 11, 12]), rng.choice(["A-1", "B-2", "C-3", None]), int(rng.random() < 0.15)) for i in range(1, 181)])
    crs = [("MATH101", "Algebra I", "Math", 1.0), ("MATH201", "Geometry", "Math", 1.0), ("SCI110", "Biology", "Science", 1.0),
           ("SCI210", "Chemistry", "Science", 1.5), ("ENG100", "English Composition", "English", 1.0), ("ART090", "Studio Art", "Arts", 0.5)]
    c.executemany("INSERT INTO courses VALUES (?,?,?,?)", crs)
    c.executemany("INSERT INTO teachers VALUES (?,?,?)", [(1, "Ms. Ortiz", "Math"), (2, "Mr. Chen", "Science"), (3, "Dr. Patel", "Science"),
                                                         (4, "Mrs. O'Hara", "English"), (5, "Mr. Banks", "Math"), (6, "Ms. Kim", "Arts")])
    res, acc, k = [], [], 0
    for r in range(1, 1101):
        absent = int(rng.random() < 0.05); poss = rng.choice([50.0, 100.0])
        earned = None if absent else round(rng.uniform(0.3, 1.0) * poss, 1)
        m = rng.choice([1, 2, 3, 5, 6, 10, 11, 12]); y = 2024 if m >= 10 else 2025
        res.append((r, rng.randint(1, 180), rng.choice([x[0] for x in crs[:5]]), rng.randint(1, 6), None if rng.random() < 0.1 else rng.randint(1, 6),
                    f"{y}-{m:02d}-{rng.randint(1, 25):02d}", None if absent or rng.random() < 0.07 else f"{y}-{m:02d}-{rng.randint(26, 28):02d}",
                    None if earned is None else round(100 * earned / poss, 1), earned, poss, int(rng.random() < 0.12), absent))
        if rng.random() < 0.18:
            k += 1; acc.append((k, r, rng.choice(["extra time", "separate room", "reader"])))
            if rng.random() < 0.3:
                k += 1; acc.append((k, r, "extra time"))
    c.executemany("INSERT INTO exam_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", res)
    c.executemany("INSERT INTO accommodations VALUES (?,?,?)", acc)
    c.commit(); c.close(); return p


def build_shop(scheme="abbr"):
    p, c = _mk("shop", """
    CREATE TABLE customers (cust_id INTEGER PRIMARY KEY, cust_nm TEXT NOT NULL, region TEXT, segment TEXT NOT NULL, joined_dt TEXT NOT NULL);
    CREATE TABLE orders (order_id INTEGER PRIMARY KEY, cust_id INTEGER NOT NULL REFERENCES customers(cust_id),
        order_dt TEXT NOT NULL, ship_dt TEXT, ship_mode TEXT NOT NULL, promo_cd TEXT, gross_amt REAL NOT NULL,
        disc_amt REAL NOT NULL, ship_fee REAL NOT NULL, is_gift INTEGER NOT NULL, paid_ok INTEGER NOT NULL);
    CREATE TABLE order_lines (line_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
        sku TEXT NOT NULL, product_cat TEXT NOT NULL, qty INTEGER NOT NULL, unit_prc REAL NOT NULL);
    CREATE TABLE returns (return_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
        reason TEXT NOT NULL, refund_amt REAL NOT NULL);
    """, scheme)
    rng = random.Random(777)
    c.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", [(i, f"Customer {i:03d}" if i != 7 else "D'Angelo & Sons", rng.choice(["West", "East", "Central", None]),
                                                                rng.choice(["Consumer", "Small Business", "Enterprise"]), f"{rng.choice([2022, 2023, 2024])}-{rng.randint(1, 12):02d}-01") for i in range(1, 121)])
    orders, lines, rets, k, rk = [], [], [], 0, 0
    for o in range(1, 1001):
        m = rng.randint(1, 12); d = rng.randint(1, 25)
        shipped = rng.random() > 0.08
        gross = round(rng.uniform(15, 600), 2)
        orders.append((o, rng.randint(1, 120), f"2025-{m:02d}-{d:02d}", f"2025-{m:02d}-{min(28, d + rng.randint(1, 3)):02d}" if shipped else None,
                       rng.choice(["Standard", "Express", "Pickup"]), rng.choice([None, None, None, "SPRING10", "VIP20"]), gross,
                       round(gross * rng.choice([0, 0, 0.1, 0.2]), 2), rng.choice([0.0, 4.99, 9.99]), int(rng.random() < 0.1), int(rng.random() > 0.04)))
        for _ in range(rng.randint(1, 4)):
            k += 1; lines.append((k, o, f"SKU-{rng.randint(100, 140)}", rng.choice(["Apparel", "Home", "Electronics", "Toys"]), rng.randint(1, 5), round(rng.uniform(3, 150), 2)))
        if shipped and rng.random() < 0.09:
            rk += 1; rets.append((rk, o, rng.choice(["damaged", "wrong size", "changed mind"]), round(gross * rng.uniform(0.2, 1.0), 2)))
    c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)", orders)
    c.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?,?)", lines)
    c.executemany("INSERT INTO returns VALUES (?,?,?,?)", rets)
    c.commit(); c.close(); return p


def build_support(scheme="abbr"):
    p, c = _mk("support", """
    CREATE TABLE accounts (acct_id INTEGER PRIMARY KEY, acct_nm TEXT NOT NULL, tier TEXT NOT NULL, arr_usd REAL NOT NULL);
    CREATE TABLE agents (agent_id INTEGER PRIMARY KEY, agent_nm TEXT NOT NULL, team TEXT NOT NULL);
    CREATE TABLE tickets (ticket_id INTEGER PRIMARY KEY, acct_id INTEGER NOT NULL REFERENCES accounts(acct_id),
        opened_by_agent_id INTEGER NOT NULL, resolved_by_agent_id INTEGER, opened_ts TEXT NOT NULL, closed_ts TEXT,
        priority TEXT NOT NULL, channel TEXT NOT NULL, csat_score INTEGER, sla_met INTEGER NOT NULL, reopen_cnt INTEGER NOT NULL);
    CREATE TABLE ticket_tags (tag_id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id), tag TEXT NOT NULL);
    """, scheme)
    rng = random.Random(5150)
    c.executemany("INSERT INTO accounts VALUES (?,?,?,?)", [(i, f"Acct {i:02d}" if i != 3 else "Blue Sky (EU)", rng.choice(["Gold", "Silver", "Bronze"]), round(rng.uniform(5000, 250000), 2)) for i in range(1, 41)])
    ags = [(1, "Ava Moss", "Tier 1"), (2, "Ben Ruiz", "Tier 1"), (3, "Cho Lee", "Tier 2"), (4, "Dee Park", "Tier 2"), (5, "Eli Stone", "Escalations")]
    c.executemany("INSERT INTO agents VALUES (?,?,?)", ags)
    tk, tags, k = [], [], 0
    for t in range(1, 801):
        m = rng.randint(1, 12); d = rng.randint(1, 25)
        closed = rng.random() > 0.12
        tk.append((t, rng.randint(1, 40), rng.randint(1, 5), rng.randint(1, 5) if closed else None, f"2025-{m:02d}-{d:02d} 09:00:00",
                   f"2025-{m:02d}-{min(28, d + rng.randint(0, 3)):02d} 17:00:00" if closed else None, rng.choice(["P1", "P2", "P3", "P4"]),
                   rng.choice(["email", "chat", "phone"]), (rng.randint(1, 5) if closed and rng.random() > 0.3 else None), int(rng.random() > 0.2), rng.choice([0, 0, 0, 1, 2])))
        for tag in rng.sample(["billing", "login", "bug", "feature request", "outage"], rng.choice([0, 1, 1, 2])):
            k += 1; tags.append((k, t, tag))
    c.executemany("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)", tk)
    c.executemany("INSERT INTO ticket_tags VALUES (?,?,?)", tags)
    c.commit(); c.close(); return p


BUILD = {"bikes": build_bikes, "school": build_school, "shop": build_shop, "support": build_support}


def build_all(scheme="abbr"):
    return {k: f(scheme) for k, f in BUILD.items()}
