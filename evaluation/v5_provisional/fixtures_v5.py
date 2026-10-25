"""Deterministic SQLite fixtures for the v5 provisional evaluation set.

Four business domains, each with one anchor (fact) table and 2-4 related tables:
  hotel.db      anchor: bookings
  insurance.db  anchor: claims
  energy.db     anchor: bills
  rides.db      anchor: trips

Standard library only. Every builder deletes and recreates its database from a
fixed seed, so results are reproducible across runs and machines.
"""
import datetime as _dt
import os
import random
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


def _fresh(name):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name + ".db")
    if os.path.exists(path):
        os.remove(path)
    return path, sqlite3.connect(path)


def _d(base, days):
    return (base + _dt.timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# 1. Hotel bookings
# ---------------------------------------------------------------------------
def build_hotel():
    path, con = _fresh("hotel")
    rng = random.Random(5101)
    con.executescript(
        """
        CREATE TABLE hotels (
            hotel_id   INTEGER PRIMARY KEY,
            hotel_nm   TEXT NOT NULL,
            city       TEXT NOT NULL,
            star_rtg   INTEGER
        );
        -- hotel_id is a foreign key to hotels but is NOT declared as one
        CREATE TABLE rooms (
            room_id    INTEGER PRIMARY KEY,
            hotel_id   INTEGER NOT NULL,
            room_no    TEXT NOT NULL,
            room_type  TEXT NOT NULL,
            sq_m       REAL NOT NULL,
            base_rate  REAL NOT NULL
        );
        CREATE TABLE guests (
            guest_id     INTEGER PRIMARY KEY,
            guest_nm     TEXT NOT NULL,
            country      TEXT,
            loyalty_tier TEXT
        );
        CREATE TABLE bookings (
            bk_id        INTEGER PRIMARY KEY,
            guest_id     INTEGER NOT NULL REFERENCES guests(guest_id),
            room_id      INTEGER NOT NULL REFERENCES rooms(room_id),
            booked_on    TEXT NOT NULL,
            checkin_dt   TEXT,
            nts_cnt      INTEGER NOT NULL,
            amt          REAL NOT NULL,
            channel      TEXT,
            is_cancelled INTEGER NOT NULL,
            payment_ok   INTEGER NOT NULL,
            special_req  TEXT
        );
        CREATE TABLE booking_addons (
            addon_id   INTEGER PRIMARY KEY,
            bk_id      INTEGER NOT NULL REFERENCES bookings(bk_id),
            addon_type TEXT NOT NULL,
            addon_amt  REAL NOT NULL
        );
        """
    )
    hotels = [
        (1, "Harbour View Hotel", "Lisbon", 4),
        (2, "Captain's Inn", "Porto", 3),
        (3, "Bay & Pier Lodge", "Lisbon", 3),
        (4, "Grand Palace (Annex)", "Madrid", 5),
        (5, "Sierra Mountain Retreat", "Granada", 4),
        (6, "Old Town B&B", "Seville", 2),  # has rooms, never booked
    ]
    con.executemany("INSERT INTO hotels VALUES (?,?,?,?)", hotels)
    room_types = [("Standard", 18, 26, 80), ("Deluxe", 26, 38, 130),
                  ("Suite", 40, 65, 240), ("Family (2+2)", 32, 46, 160)]
    rooms = []
    rid = 100
    for h in hotels:
        for k in range(rng.randint(4, 6)):
            rt, lo, hi, rate = rng.choice(room_types)
            rid += 1
            mult = 0.7 + 0.15 * h[3]
            rooms.append((rid, h[0], "%d%02d" % (h[0], k + 1), rt,
                          round(rng.uniform(lo, hi), 1), round(rate * mult, 2)))
    con.executemany("INSERT INTO rooms VALUES (?,?,?,?,?,?)", rooms)
    countries = ["PT", "ES", "FR", "UK", "US", "DE", None]
    tiers = ["Gold", "Silver", "Bronze", None, None]
    first = ["Ana", "Joao", "Maria", "Luis", "Claire", "Tom", "Sofia", "Pedro", "Emma", "Liam",
             "Noah", "Ines", "Rui", "Sean", "Aoife"]
    last = ["Silva", "Santos", "Garcia", "Martin", "O'Neill", "Smith", "Dubois", "Muller",
            "Costa", "Lopez", "Brown", "Ferreira"]
    guests = []
    for g in range(1, 321):
        guests.append((g, "%s %s #%03d" % (rng.choice(first), rng.choice(last), g),
                       rng.choice(countries), rng.choice(tiers)))
    con.executemany("INSERT INTO guests VALUES (?,?,?,?)", guests)
    bookable = [r for r in rooms if r[1] != 6]
    channels = ["Direct", "Direct", "OTA", "OTA", "OTA", "Corporate", "Travel Agent (Offline)", None]
    reqs = [None, None, None, "Late arrival", "High floor & quiet", "Crib (infant)", "Guest's anniversary"]
    base = _dt.date(2024, 9, 1)
    bookings = []
    for b in range(1, 951):
        r = rng.choice(bookable)
        booked = rng.randint(0, 425)
        lead = rng.randint(0, 120)
        checkin = _d(base, booked + lead) if rng.random() > 0.035 else None
        nts = rng.choices(range(1, 11), weights=[18, 22, 18, 12, 9, 6, 7, 3, 3, 2])[0]
        amt = round(nts * r[5] * rng.uniform(0.85, 1.25), 2)
        bookings.append((b, rng.randint(1, 300), r[0], _d(base, booked), checkin, nts, amt,
                         rng.choice(channels), 1 if rng.random() < 0.13 else 0,
                         0 if rng.random() < 0.09 else 1, rng.choice(reqs)))
    con.executemany("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?)", bookings)
    addon_types = [("Breakfast", 12, 25), ("Parking", 10, 30), ("Spa & Wellness", 40, 120),
                   ("Late check-out", 15, 35)]
    addons = []
    aid = 0
    for b in bookings:
        for _ in range(rng.choices([0, 1, 2, 3], weights=[40, 35, 18, 7])[0]):
            t, lo, hi = rng.choice(addon_types)  # with replacement: duplicates possible
            aid += 1
            addons.append((aid, b[0], t, round(rng.uniform(lo, hi), 2)))
    con.executemany("INSERT INTO booking_addons VALUES (?,?,?,?)", addons)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 2. Insurance claims
# ---------------------------------------------------------------------------
def build_insurance():
    path, con = _fresh("insurance")
    rng = random.Random(5202)
    con.executescript(
        """
        CREATE TABLE products (
            product_cd TEXT PRIMARY KEY,
            product_nm TEXT NOT NULL,
            line_of_bus TEXT NOT NULL
        );
        CREATE TABLE policies (
            policy_no  TEXT PRIMARY KEY,
            holder_nm  TEXT NOT NULL,
            product_cd TEXT NOT NULL REFERENCES products(product_cd),
            prem_amt   REAL NOT NULL,
            deductible REAL NOT NULL,
            start_dt   TEXT NOT NULL,
            region     TEXT
        );
        CREATE TABLE adjusters (
            adj_id  INTEGER PRIMARY KEY,
            adj_nm  TEXT NOT NULL,
            region  TEXT NOT NULL
        );
        -- adj_id references adjusters(adj_id) but is NOT declared as a foreign key
        CREATE TABLE claims (
            claim_id      INTEGER PRIMARY KEY,
            policy_no     TEXT NOT NULL REFERENCES policies(policy_no),
            adj_id        INTEGER,
            loss_dt       TEXT NOT NULL,
            rpt_dt        TEXT NOT NULL,
            closed_dt     TEXT,
            claim_amt     REAL NOT NULL,
            status        TEXT NOT NULL,
            cause         TEXT,
            is_fraud_susp INTEGER NOT NULL,
            docs_ok       INTEGER NOT NULL
        );
        CREATE TABLE claim_payments (
            pmt_id   INTEGER PRIMARY KEY,
            claim_id INTEGER NOT NULL REFERENCES claims(claim_id),
            pmt_dt   TEXT NOT NULL,
            pmt_amt  REAL NOT NULL
        );
        """
    )
    products = [
        ("AUTO", "Auto (Comprehensive)", "Motor"),
        ("AUTO3", "Auto (Third Party)", "Motor"),
        ("HOME", "Home & Contents", "Property"),
        ("RENT", "Renter's Basic", "Property"),
        ("TRVL", "Travel", "Personal"),
        ("PET", "Pet Care", "Personal"),  # policies exist, zero claims
    ]
    con.executemany("INSERT INTO products VALUES (?,?,?)", products)
    prem_rng = {"AUTO": (700, 1900), "AUTO3": (350, 900), "HOME": (500, 2200),
                "RENT": (150, 450), "TRVL": (60, 300), "PET": (200, 600)}
    regions = ["North", "South", "East", "West", None]
    names = ["Murphy", "O'Connor", "Patel", "Nguyen", "Kowalski", "Smith & Sons Ltd",
             "Rossi", "Haddad", "Okafor", "Lindqvist", "Brown (Trust)", "Garcia"]
    pbase = _dt.date(2022, 1, 1)
    policies = []
    for i in range(1, 521):
        pc = rng.choices([p[0] for p in products], weights=[25, 15, 22, 15, 13, 10])[0]
        lo, hi = prem_rng[pc]
        policies.append(("P%05d" % (10000 + i), "%s %03d" % (rng.choice(names), i), pc,
                         round(rng.uniform(lo, hi), 2), rng.choice([250, 500, 1000, 2500]),
                         _d(pbase, rng.randint(0, 900)), rng.choice(regions)))
    con.executemany("INSERT INTO policies VALUES (?,?,?,?,?,?,?)", policies)
    adjusters = [
        (1, "Sean O'Brien", "North"), (2, "Priya Raman", "South"), (3, "Lee & Partners (external)", "East"),
        (4, "Marta Novak", "West"), (5, "Daniel Kim", "North"), (6, "Grace Mbeki", "South"),
        (7, "Tomas Ruiz", "East"), (8, "Hannah Vogel", "West"),
    ]
    con.executemany("INSERT INTO adjusters VALUES (?,?,?)", adjusters)
    claimable = [p for p in policies if p[2] != "PET"]
    causes = ["Collision", "Theft", "Water damage", "Fire", "Storm & Hail", "Medical (abroad)", None]
    sev = {"AUTO": 4000, "AUTO3": 2500, "HOME": 6000, "RENT": 1500, "TRVL": 1200}
    cbase = _dt.date(2024, 7, 1)
    claims, pays = [], []
    pid = 0
    for c in range(1, 1101):
        p = rng.choice(claimable)
        loss = rng.randint(0, 540)
        rpt = loss + rng.choices([0, 1, 3, 7, 20, 45, 75], weights=[10, 25, 20, 20, 12, 8, 5])[0]
        status = rng.choices(["Open", "Closed", "Denied"], weights=[22, 63, 15])[0]
        closed = None if status == "Open" else _d(cbase, rpt + rng.randint(5, 120))
        amt = round(rng.lognormvariate(0, 0.7) * sev[p[2]], 2)
        adj = rng.randint(1, 8) if rng.random() > 0.08 else None
        claims.append((c, p[0], adj, _d(cbase, loss), _d(cbase, rpt), closed, amt, status,
                       rng.choice(causes), 1 if rng.random() < 0.06 else 0,
                       0 if rng.random() < 0.17 else 1))
        if status == "Closed" or (status == "Open" and rng.random() < 0.4):
            n = rng.choices([1, 2, 3], weights=[60, 28, 12])[0]
            for k in range(n):
                pid += 1
                pays.append((pid, c, _d(cbase, rpt + 3 + 20 * k + rng.randint(0, 15)),
                             round(amt * rng.uniform(0.5, 0.95) / n, 2)))
    con.executemany("INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?)", claims)
    con.executemany("INSERT INTO claim_payments VALUES (?,?,?,?)", pays)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 3. Energy utility meter billing
# ---------------------------------------------------------------------------
def build_energy():
    path, con = _fresh("energy")
    rng = random.Random(5303)
    con.executescript(
        """
        CREATE TABLE tariffs (
            tariff_cd    TEXT PRIMARY KEY,
            tariff_nm    TEXT NOT NULL,
            rate_per_kwh REAL NOT NULL
        );
        -- tariff_cd references tariffs(tariff_cd) but is NOT declared as a foreign key
        CREATE TABLE customers (
            cust_id   INTEGER PRIMARY KEY,
            cust_nm   TEXT NOT NULL,
            segment   TEXT,
            tariff_cd TEXT NOT NULL,
            city      TEXT NOT NULL
        );
        CREATE TABLE meters (
            meter_id   TEXT PRIMARY KEY,
            cust_id    INTEGER NOT NULL REFERENCES customers(cust_id),
            meter_type TEXT NOT NULL,
            install_dt TEXT
        );
        CREATE TABLE customer_programs (
            cust_id     INTEGER NOT NULL REFERENCES customers(cust_id),
            program_nm  TEXT NOT NULL,
            enrolled_dt TEXT,
            PRIMARY KEY (cust_id, program_nm)
        );
        CREATE TABLE bills (
            bill_id      INTEGER PRIMARY KEY,
            meter_id     TEXT NOT NULL REFERENCES meters(meter_id),
            period_start TEXT NOT NULL,
            due_dt       TEXT NOT NULL,
            paid_dt      TEXT,
            kwh          REAL NOT NULL,
            amt          REAL NOT NULL,
            late_fee     REAL,
            meter_ok     INTEGER NOT NULL,
            is_estimated INTEGER NOT NULL
        );
        """
    )
    tariffs = [
        ("RES-STD", "Residential Standard", 0.21),
        ("TOU", "Time-of-Use (TOU)", 0.18),
        ("GRN", "Green Saver's Plan", 0.24),
        ("COM", "Commercial Flat", 0.17),
        ("AGR", "Farm & Rural", 0.15),
        ("EVN", "EV Night Owl", 0.12),  # no customers -> zero bills
    ]
    con.executemany("INSERT INTO tariffs VALUES (?,?,?)", tariffs)
    rate = {t[0]: t[2] for t in tariffs}
    cities = ["Riverton", "Saint-Jean d'Arc", "Lakeside", "Millbrook", "Port Ash"]
    seg_tariff = {"Residential": ["RES-STD", "RES-STD", "TOU", "GRN"],
                  "Commercial": ["COM", "COM", "TOU"],
                  "Small Biz & Farm": ["AGR", "COM", "GRN"],
                  None: ["RES-STD", "TOU", "GRN", "AGR"]}
    snames = ["Acme", "Baker's Dozen", "Cole", "Delta", "Evans", "Fern & Co", "Grove", "Hill (Est.)",
              "Iris", "Jansen", "Kaur", "Lowe"]
    customers = []
    for c in range(1, 241):
        seg = rng.choices(["Residential", "Commercial", "Small Biz & Farm", None], weights=[60, 18, 12, 10])[0]
        customers.append((c, "%s %03d" % (rng.choice(snames), c), seg, rng.choice(seg_tariff[seg]),
                          rng.choice(cities)))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)
    mtypes = ["Smart", "Smart", "Analog", "Smart (3-phase)"]
    meters = []
    for c in customers:
        n = 1 if rng.random() < 0.8 else 2
        for k in range(n):
            mt = rng.choice(mtypes)
            inst = _d(_dt.date(2015, 1, 1), rng.randint(0, 3000)) if rng.random() > 0.15 else None
            meters.append(("M-%04d-%d" % (c[0], k + 1), c[0], mt, inst))
    con.executemany("INSERT INTO meters VALUES (?,?,?,?)", meters)
    programs = ["Budget Billing", "Solar Rebate", "Paperless", "Senior Discount"]
    cp = []
    for c in customers:
        for pg in programs:
            if rng.random() < 0.3:
                ed = _d(_dt.date(2020, 1, 1), rng.randint(0, 1500)) if rng.random() > 0.2 else None
                cp.append((c[0], pg, ed))
    con.executemany("INSERT INTO customer_programs VALUES (?,?,?)", cp)
    cust = {c[0]: c for c in customers}
    months = ["%d-%02d-01" % (y, m) for y in (2024, 2025) for m in range(1, 13)]
    bills = []
    bid = 0
    unbilled = set(m[0] for m in meters[::37])  # a few meters never billed
    billable = [m for m in meters if m[0] not in unbilled]
    while bid < 1250:
        m = rng.choice(billable)
        mon = rng.choice(months)
        c = cust[m[1]]
        base_kwh = 900 if c[2] == "Commercial" else (600 if c[2] == "Small Biz & Farm" else 320)
        mm = int(mon[5:7])
        season = 1.25 if mm in (1, 2, 7, 8, 12) else 1.0
        kwh = round(base_kwh * season * rng.uniform(0.5, 1.6), 1)
        amt = round(kwh * rate[c[3]] + 9.5, 2)
        y, mo = int(mon[:4]), int(mon[5:7])
        nxt = _dt.date(y + (mo == 12), mo % 12 + 1, 1)
        due = nxt + _dt.timedelta(days=14)
        r = rng.random()
        if r < 0.10:
            paid = None
        elif r < 0.25:
            paid = (due + _dt.timedelta(days=rng.randint(1, 40))).isoformat()
        else:
            paid = (due - _dt.timedelta(days=rng.randint(0, 13))).isoformat()
        late = round(rng.uniform(5, 25), 2) if (paid is None or paid > due.isoformat()) and rng.random() < 0.8 else None
        bid += 1
        bills.append((bid, m[0], mon, due.isoformat(), paid, kwh, amt, late,
                      0 if rng.random() < 0.07 else 1, 1 if rng.random() < 0.15 else 0))
    con.executemany("INSERT INTO bills VALUES (?,?,?,?,?,?,?,?,?,?)", bills)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 4. Ride-hailing trips
# ---------------------------------------------------------------------------
def build_rides():
    path, con = _fresh("rides")
    rng = random.Random(5404)
    con.executescript(
        """
        CREATE TABLE zones (
            zone_cd TEXT PRIMARY KEY,
            zone_nm TEXT NOT NULL,
            borough TEXT NOT NULL
        );
        CREATE TABLE drivers (
            driver_id   INTEGER PRIMARY KEY,
            driver_nm   TEXT NOT NULL,
            vehicle_cls TEXT NOT NULL,
            rating      REAL NOT NULL,
            join_dt     TEXT NOT NULL
        );
        CREATE TABLE driver_languages (
            driver_id INTEGER NOT NULL REFERENCES drivers(driver_id),
            lang      TEXT NOT NULL,
            PRIMARY KEY (driver_id, lang)
        );
        CREATE TABLE riders (
            rider_id   INTEGER PRIMARY KEY,
            signup_dt  TEXT NOT NULL,
            rider_tier TEXT
        );
        -- pickup_zone_cd and dropoff_zone_cd both reference zones(zone_cd);
        -- neither is declared as a foreign key.
        CREATE TABLE trips (
            trip_id         INTEGER PRIMARY KEY,
            driver_id       INTEGER NOT NULL REFERENCES drivers(driver_id),
            rider_id        INTEGER NOT NULL REFERENCES riders(rider_id),
            pickup_zone_cd  TEXT NOT NULL,
            dropoff_zone_cd TEXT NOT NULL,
            req_ts          TEXT NOT NULL,
            status          TEXT NOT NULL,
            fare_amt        REAL NOT NULL,
            tip_amt         REAL,
            dist_km         REAL NOT NULL,
            dur_min         INTEGER NOT NULL,
            is_surge        INTEGER NOT NULL,
            payment_ok      INTEGER NOT NULL,
            pay_method      TEXT
        );
        """
    )
    zones = [
        ("Z01", "Downtown Core", "Central"), ("Z02", "Airport (JFK)", "Queens"),
        ("Z03", "St. Mary's Park", "Bronx"), ("Z04", "Arts & Theatre District", "Central"),
        ("Z05", "Harbourfront", "South"), ("Z06", "University Hill", "North"),
        ("Z07", "Tech Park", "North"), ("Z08", "Old Mill (Closed)", "South"),  # zero trips
    ]
    con.executemany("INSERT INTO zones VALUES (?,?,?)", zones)
    first = ["Ahmed", "Bianca", "Carlos", "Dmitri", "Elif", "Farah", "Gus", "Hiro", "Ivy", "Jamal",
             "Kofi", "Lena", "Mateo", "Nadia", "Omar"]
    last = ["D'Souza", "Ng", "Ortiz", "Petrov", "Quinn", "Reyes", "Sato", "Tran", "Usman", "Vance"]
    classes = ["Economy", "Economy", "Comfort", "XL", "Green (EV)"]
    drivers = []
    for d in range(1, 61):
        drivers.append((d, "%s %s (%02d)" % (rng.choice(first), rng.choice(last), d), rng.choice(classes),
                        round(rng.uniform(4.2, 5.0), 2), _d(_dt.date(2019, 1, 1), rng.randint(0, 1800))))
    con.executemany("INSERT INTO drivers VALUES (?,?,?,?,?)", drivers)
    langs = ["English", "Spanish", "Arabic", "Mandarin", "French"]
    dl = []
    for d in drivers:
        ls = {"English"} if rng.random() < 0.85 else set()
        for lg in langs[1:]:
            if rng.random() < 0.22:
                ls.add(lg)
        if not ls:
            ls.add(rng.choice(langs[1:]))
        for lg in sorted(ls):
            dl.append((d[0], lg))
    con.executemany("INSERT INTO driver_languages VALUES (?,?)", dl)
    riders = []
    for r in range(1, 451):
        riders.append((r, _d(_dt.date(2021, 1, 1), rng.randint(0, 1400)), rng.choice(["Plus", "Basic", "Basic", None])))
    con.executemany("INSERT INTO riders VALUES (?,?,?)", riders)
    zc = [z[0] for z in zones[:7]]
    zw = [26, 14, 10, 16, 12, 11, 11]
    t0 = _dt.datetime(2025, 1, 1)
    trips = []
    for t in range(1, 1451):
        pu = rng.choices(zc, weights=zw)[0]
        do = rng.choices(zc, weights=zw[::-1])[0]
        ts = t0 + _dt.timedelta(minutes=rng.randint(0, 9 * 30 * 24 * 60))
        status = rng.choices(["completed", "cancelled_rider", "cancelled_driver"], weights=[85, 10, 5])[0]
        dist = round(rng.uniform(1.0, 6.0) + (14 if "Z02" in (pu, do) else 0) * rng.random(), 2)
        dur = int(dist * rng.uniform(2.0, 3.5) + rng.randint(2, 8))
        surge = 1 if rng.random() < 0.18 else 0
        if status == "completed":
            fare = round((2.5 + 1.3 * dist + 0.3 * dur) * (1.6 if surge else 1.0), 2)
            tip = rng.choice([None, None, 0.0, round(fare * rng.uniform(0.05, 0.25), 2)])
            pm = rng.choice(["Card", "Card", "Card", "Wallet", "Cash", None])
            pok = 0 if rng.random() < 0.05 else 1
        else:
            fare = 5.0 if status == "cancelled_rider" and rng.random() < 0.5 else 0.0
            tip = None
            pm = rng.choice(["Card", "Wallet", None])
            pok = 1
        trips.append((t, rng.randint(1, 60), rng.randint(1, 420), pu, do, ts.strftime("%Y-%m-%d %H:%M:%S"),
                      status, fare, tip, dist, dur, surge, pok, pm))
    con.executemany("INSERT INTO trips VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", trips)
    con.commit()
    con.close()
    return path


def build_all():
    return {"hotel": build_hotel(), "insurance": build_insurance(),
            "energy": build_energy(), "rides": build_rides()}


if __name__ == "__main__":
    for k, v in build_all().items():
        print(k, v)
