"""Blind evaluation fixtures, schema version v6.0.

Four deterministic SQLite databases (standard library only):

  food.db       anchor: orders           (food delivery)
  lease.db      anchor: leases           (residential leases / rent payments)
  telecom.db    anchor: monthly_bills    (mobile usage and billing)
  warehouse.db  anchor: inv_moves        (warehouse inventory movements)

Every builder uses its own fixed random seed, so rebuilding always yields
byte-identical data.  Run `python3 fixtures_v6.py` to (re)build data/*.db.
"""
import datetime as dt
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
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = OFF")
    return con, path


def _ts(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _d(d):
    return d.strftime("%Y-%m-%d")


FIRST = ["Aisha", "Ben", "Carla", "Dmitri", "Elena", "Farid", "Grace", "Hiro", "Ines", "Jamal",
         "Kira", "Liam", "Maya", "Noah", "Olu", "Priya", "Quinn", "Rosa", "Sam", "Tara",
         "Umar", "Vera", "Wes", "Xin", "Yara", "Zane"]
LAST = ["O'Brien", "D'Souza", "Nguyen", "Smith", "Garcia", "Kowalski", "Okafor", "Lee", "Patel",
        "Moreau", "Rossi", "Haddad", "Johansson", "Tanaka", "Silva", "O'Neil", "Becker", "Ivanova",
        "Mensah", "Khan", "Lopez", "Fischer", "Park", "Wright"]


def _unique_names(rnd, n):
    pool = [f"{f} {l}" for f in FIRST for l in LAST]
    rnd.shuffle(pool)
    return pool[:n]


# ---------------------------------------------------------------------------
# 1. FOOD DELIVERY
# ---------------------------------------------------------------------------
FOOD_DDL = """
CREATE TABLE restaurants (
    restaurant_id   INTEGER PRIMARY KEY,
    rest_nm         TEXT NOT NULL,
    cuisine         TEXT,
    city            TEXT,
    avg_prep_min    REAL,
    commission_pct  REAL,
    is_partner_plus INTEGER
);
CREATE TABLE couriers (
    courier_id      INTEGER PRIMARY KEY,
    courier_nm      TEXT NOT NULL,
    vehicle_cd      TEXT,
    hire_dt         TEXT,
    courier_rating  REAL
);
CREATE TABLE customers (
    cust_id         INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT,
    signup_date     TEXT,
    loyalty_tier    TEXT,
    home_city       TEXT
);
CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    restaurant_id   INTEGER REFERENCES restaurants(restaurant_id),
    cust_id         INTEGER REFERENCES customers(cust_id),
    courier_id      INTEGER,           -- undeclared FK -> couriers
    order_ts        TEXT,
    dlv_ts          TEXT,
    subtotal_amt    REAL,
    dlv_fee         REAL,
    tip_amt         REAL,
    disc_amt        REAL,
    order_status    TEXT,
    is_late         INTEGER,
    delivered_ok    INTEGER,
    promo_cd        TEXT,
    cust_rating     INTEGER,
    channel         TEXT
);
CREATE TABLE order_items (
    order_id        INTEGER REFERENCES orders(order_id),
    line_no         INTEGER,
    item_nm         TEXT,
    item_cat        TEXT,
    qty             INTEGER,
    unit_price      REAL,
    PRIMARY KEY (order_id, line_no)
);
"""

RESTAURANTS = [
    (1, "Mama's Kitchen", "Italian", "Springfield", 18.5, 15.0, 1),
    (2, "Fish & Chips Co.", "British", "Springfield", 14.0, 18.0, 0),
    (3, "Taco Loco (Downtown)", "Mexican", "Riverton", 11.0, 20.0, 1),
    (4, "Golden Dragon", "Chinese", "Riverton", 16.0, 15.0, 0),
    (5, "Smoky Joe's", "BBQ", "Springfield", 25.0, 22.0, 1),
    (6, "Green Bowl", None, "Lakeside", 9.0, 12.5, 0),
    (7, "Pho Real", "Vietnamese", "Lakeside", 13.0, 17.0, 0),
    (8, "Curry & Co.", "Indian", "Riverton", 20.0, 18.0, 1),
    (9, "Burger Barn", "American", "Springfield", 10.0, 25.0, 0),
    (10, "Sushi Zen", "Japanese", "Lakeside", 22.0, 15.0, 1),
    (11, "Pizza Planet (Westside)", "Italian", "Riverton", 15.0, 20.0, 0),
    (12, "The Daily Grind", None, "Springfield", 7.0, 10.0, 0),
    (13, "Closed Corner Cafe", "French", "Lakeside", 30.0, 15.0, 0),  # no orders
]

COURIERS = [
    (1, "Ravi Menon", "BIKE", "2023-03-01", 4.8),
    (2, "Lucia Ferreira", "CAR", "2022-11-15", 4.6),
    (3, "Tom O'Hara", "SCTR", "2024-01-10", 4.2),
    (4, "Mei Chen", "BIKE", "2023-07-22", 4.9),
    (5, "Kwame Asante", "CAR", "2021-05-05", 4.4),
    (6, "Sofia Brandt", "SCTR", "2024-06-01", 4.7),
    (7, "Diego Ruiz", "BIKE", "2022-02-14", 4.1),
    (8, "Hannah Kim", "CAR", "2024-09-30", 4.5),
    (9, "Yusuf Demir", None, "2025-01-05", 4.0),
    (10, "Anna Novak", "BIKE", "2023-10-12", 4.3),
]

MENU = [  # (item, category, base price)
    ("Margherita Pizza", "MAIN", 12.0), ("Chicken Curry", "MAIN", 13.5),
    ("Beef Burger", "MAIN", 11.0), ("Pad Thai", "MAIN", 12.5),
    ("Salmon Roll (8 pc)", "MAIN", 14.0), ("Mac & Cheese", "MAIN", 9.5),
    ("Pulled Pork Platter", "MAIN", 16.0), ("Veggie Bowl", "MAIN", 10.5),
    ("Garlic Bread", "SIDE", 4.5), ("Fries", "SIDE", 3.5), ("Side Salad", "SIDE", 4.0),
    ("Spring Rolls", "SIDE", 5.0),
    ("Iced Tea", "DRINK", 2.5), ("Soda (Can)", "DRINK", 1.75), ("Mango Lassi", "DRINK", 3.75),
    ("Cold Brew", "DRINK", 4.25),
    ("Brownie", "DESSERT", 3.25), ("Tiramisu", "DESSERT", 5.5),
]


def build_food():
    rnd = random.Random(60601)
    con, path = _fresh("food")
    con.executescript(FOOD_DDL)
    con.executemany("INSERT INTO restaurants VALUES (?,?,?,?,?,?,?)", RESTAURANTS)
    con.executemany("INSERT INTO couriers VALUES (?,?,?,?,?)", COURIERS)

    names = _unique_names(rnd, 150)
    tiers = ["GOLD", "SILVER", "BRONZE", None]
    cities = ["Springfield", "Riverton", "Lakeside"]
    custs = []
    for cid in range(1, 151):
        signup = dt.date(2023, 1, 1) + dt.timedelta(days=rnd.randint(0, 720))
        nm = names[cid - 1]
        custs.append((cid, nm, nm.lower().replace(" ", ".").replace("'", "") + "@example.com",
                      _d(signup), rnd.choices(tiers, [15, 30, 35, 20])[0], rnd.choice(cities)))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", custs)

    rest_w = [10, 9, 11, 8, 7, 9, 6, 8, 12, 6, 10, 5]
    start = dt.date(2025, 1, 1)
    month_end_specials = {50: dt.date(2025, 1, 31), 210: dt.date(2025, 2, 28), 333: dt.date(2025, 3, 31),
                          334: dt.date(2025, 3, 31), 480: dt.date(2025, 4, 30), 777: dt.date(2025, 5, 31),
                          901: dt.date(2025, 3, 31), 1002: dt.date(2025, 4, 30)}
    orders, items = [], []
    for oid in range(1, 1201):
        rid = rnd.choices(range(1, 13), rest_w)[0]
        cid = rnd.randint(1, 140)  # customers 141..150 never order
        if oid in month_end_specials:
            day = month_end_specials[oid]
            ots = dt.datetime(day.year, day.month, day.day, 23, rnd.randint(30, 50), rnd.randint(0, 59))
            status = "DELIVERED"
        else:
            day = start + dt.timedelta(days=rnd.randint(0, 180))
            hour = rnd.choices(range(10, 24), [3, 6, 9, 7, 4, 3, 4, 8, 10, 9, 7, 5, 3, 2])[0]
            ots = dt.datetime(day.year, day.month, day.day, hour, rnd.randint(0, 59), rnd.randint(0, 59))
            status = rnd.choices(["DELIVERED", "CANCELLED", "REFUNDED"], [88, 8, 4])[0]
        promo = rnd.choices([None, "SAVE10", "FREEDEL", "BOGO"], [70, 12, 10, 8])[0]
        nlines = rnd.choices([1, 2, 3, 4], [25, 35, 25, 15])[0]
        picks = rnd.sample(MENU, nlines)
        mult = 1.0 + (rid % 4) * 0.08
        sub = 0.0
        for ln, (nm, cat, price) in enumerate(picks, start=1):
            q = rnd.choices([1, 2, 3], [70, 22, 8])[0]
            up = round(price * mult, 2)
            sub += q * up
            items.append((oid, ln, nm, cat, q, up))
        sub = round(sub, 2)
        fee = 0.0 if promo == "FREEDEL" else rnd.choice([1.99, 2.99, 3.99, 4.99])
        disc = round(sub * 0.10, 2) if promo == "SAVE10" else (round(picks[0][2] * mult, 2) if promo == "BOGO" else 0.0)
        if status == "CANCELLED":
            courier = rnd.choice([None, rnd.randint(1, 10)])
            dts, tip, late, ok, rating = None, None, 0, 0, None
        else:
            courier = rnd.randint(1, 10)
            mins = rnd.randint(18, 80)
            dts = _ts(ots + dt.timedelta(minutes=mins))
            late = 1 if mins > 55 else 0
            r = rnd.random()
            tip = None if r < 0.15 else (0.0 if r < 0.25 else round(rnd.uniform(0.5, 9.0), 2))
            if status == "REFUNDED":
                ok = 0
                rating = rnd.choice([None, 1, 2])
            else:
                ok = 0 if rnd.random() < (0.15 if late else 0.05) else 1
                if rnd.random() < 0.30:
                    rating = None
                else:
                    rating = rnd.choices([1, 2, 3, 4, 5], [5, 8, 15, 32, 40] if not late else [15, 20, 25, 25, 15])[0]
        channel = rnd.choices(["APP", "WEB", "PHONE"], [70, 20, 10])[0]
        orders.append((oid, rid, cid, courier, _ts(ots), dts, sub, fee, tip, disc, status, late, ok,
                       promo, rating, channel))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)
    con.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", items)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 2. RESIDENTIAL LEASES
# ---------------------------------------------------------------------------
LEASE_DDL = """
CREATE TABLE units (
    unit_id         INTEGER PRIMARY KEY,
    bldg_name       TEXT NOT NULL,
    unit_no         TEXT NOT NULL,
    city            TEXT,
    unit_type       TEXT,
    bedrooms        INTEGER,
    sq_ft           INTEGER,
    mkt_rent_amt    REAL,
    has_parking     INTEGER
);
CREATE TABLE tenants (
    tenant_id       INTEGER PRIMARY KEY,
    tenant_name     TEXT NOT NULL,
    credit_score    INTEGER,
    annual_income   REAL,
    phone           TEXT
);
CREATE TABLE staff (
    staff_id        INTEGER PRIMARY KEY,
    staff_name      TEXT NOT NULL,
    role_title      TEXT,
    office          TEXT,
    commission_rate REAL
);
CREATE TABLE leases (
    lease_id          INTEGER PRIMARY KEY,
    unit_id           INTEGER REFERENCES units(unit_id),
    tenant_id         INTEGER REFERENCES tenants(tenant_id),
    leasing_agent_id  INTEGER,        -- undeclared FK -> staff (role: agent who signed it)
    prop_mgr_id       INTEGER,        -- undeclared FK -> staff (role: managing property manager)
    signed_dt         TEXT,
    start_dt          TEXT,
    end_dt            TEXT,           -- NULL = month-to-month
    term_mos          INTEGER,        -- NULL = month-to-month
    monthly_rent      REAL,
    security_dep      REAL,
    concession_amt    REAL,
    lease_status      TEXT,
    is_renewal        INTEGER,
    pets_ok           INTEGER,
    in_good_standing  INTEGER
);
CREATE TABLE rent_payments (
    pmt_id          INTEGER PRIMARY KEY,
    lease_id        INTEGER REFERENCES leases(lease_id),
    due_dt          TEXT,
    paid_dt         TEXT,
    amt_due         REAL,
    amt_paid        REAL,
    pay_method      TEXT,
    is_late         INTEGER,
    late_fee        REAL
);
"""

BUILDINGS = [("St. Mary's Lofts", "Springfield", 1.00), ("Oak & Elm Residences", "Springfield", 1.08),
             ("Harbor View (North)", "Bayport", 1.25), ("Harbor View (South)", "Bayport", 1.15),
             ("Cedar Ridge", "Hillcrest", 0.90), ("The Foundry", "Hillcrest", 1.02)]
UNIT_SPECS = {"STUDIO": (0, 400, 550, 1150), "1BR": (1, 600, 800, 1450), "2BR": (2, 850, 1100, 1850),
              "3BR": (3, 1150, 1400, 2300), "TH": (3, 1500, 1800, 2700)}
STAFF = [(1, "Paula Grant", "Leasing Agent", "NORTH", 0.030),
         (2, "Marcus Webb", "Leasing Agent", "SOUTH", 0.025),
         (3, "Chloe Dubois", "Leasing Agent & PM", "NORTH", 0.020),
         (4, "Raj Iyer", "Leasing Agent & PM", "SOUTH", 0.020),
         (5, "Nora O'Connell", "Leasing Agent & PM", "NORTH", 0.015),
         (6, "Victor Hale", "Property Manager", "SOUTH", 0.0),
         (7, "Janet Ross", "Property Manager", "NORTH", 0.0),
         (8, "Owen Pike", "Leasing Agent", "SOUTH", 0.030)]  # no leases in either role


def _add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
    return dt.date(y, mo, min(d.day, last))


def build_lease():
    rnd = random.Random(60602)
    con, path = _fresh("lease")
    con.executescript(LEASE_DDL)

    units = []
    uid = 0
    for bname, city, factor in BUILDINGS:
        for k in range(18):
            uid += 1
            utype = rnd.choices(list(UNIT_SPECS), [15, 30, 30, 15, 10])[0]
            beds, lo, hi, base = UNIT_SPECS[utype]
            sqft = rnd.randint(lo, hi)
            if uid == 9:  # deliberately exactly on a round threshold
                utype, beds, sqft, base = "2BR", 2, 900, 1850
            rent = round(base * factor * rnd.uniform(0.95, 1.05) / 5) * 5
            units.append((uid, bname, f"{(k // 6) + 1}{'ABCDEF'[k % 6]}", city, utype, beds, sqft,
                          float(rent), rnd.choice([0, 1])))
    units.append((uid + 1, "Cedar Ridge", "PH1", "Hillcrest", "3BR", 3, 1600, 2600.0, 1))  # never leased
    con.executemany("INSERT INTO units VALUES (?,?,?,?,?,?,?,?,?)", units)

    tnames = _unique_names(rnd, 560)
    tenants = []
    for tid in range(1, 561):
        cs = None if rnd.random() < 0.10 else rnd.randint(540, 820)
        inc = None if rnd.random() < 0.20 else float(rnd.randint(28, 160) * 1000)
        tenants.append((tid, tnames[tid - 1], cs, inc, f"555-{rnd.randint(1000000, 9999999)}"))
    con.executemany("INSERT INTO tenants VALUES (?,?,?,?,?)", tenants)
    con.executemany("INSERT INTO staff VALUES (?,?,?,?,?)", STAFF)

    cutoff = dt.date(2025, 6, 30)
    leases, pays = [], []
    lid = 0
    next_tenant = 1
    for (u_id, bname, unit_no, city, utype, beds, sqft, mkt, park) in units[:-1]:
        start = dt.date(2019, 1, 1) + dt.timedelta(days=rnd.randint(0, 300))
        tenant = None
        renewal = 0
        mgr = rnd.choice([3, 4, 5, 6, 7])
        while start <= cutoff:
            lid += 1
            if tenant is None or not renewal:
                if next_tenant <= 560 and rnd.random() < 0.85:
                    tenant = next_tenant
                    next_tenant += 1
                else:
                    tenant = rnd.randint(1, max(1, next_tenant - 1))
            mtm = start.year >= 2023 and rnd.random() < 0.08
            term = None if mtm else rnd.choices([6, 12, 24], [15, 70, 15])[0]
            end = None if mtm else _add_months(start, term) - dt.timedelta(days=1)
            signed = start - dt.timedelta(days=rnd.randint(5, 60))
            yrs = (start.year - 2019) + start.month / 12.0
            rent = float(round(mkt * (1 + 0.03 * yrs) * rnd.uniform(0.93, 1.05) / 5) * 5)
            dep = float(round(rent * rnd.choice([1.0, 1.5, 2.0])))
            r = rnd.random()
            conc = None if r < 0.70 else (0.0 if r < 0.80 else float(rnd.randint(2, 16) * 50))
            agent = rnd.choices([1, 2, 3, 4, 5], [30, 25, 15, 15, 15])[0]
            if rnd.random() < 0.15:
                mgr = rnd.choice([3, 4, 5, 6, 7])
            pets = 1 if rnd.random() < 0.4 else 0
            good = 0 if rnd.random() < 0.10 else 1
            # decide what happens next
            nxt_renew = rnd.random() < 0.35
            terminated = rnd.random() < 0.08
            if end is None or end >= cutoff:
                status = "ACTIVE"
            elif terminated:
                status = "TERMINATED"
            elif nxt_renew:
                status = "RENEWED"
            else:
                status = "EXPIRED"
            leases.append([lid, u_id, tenant, agent, mgr, _d(signed), _d(start), _d(end) if end else None,
                           term, rent, dep, conc, status, renewal, pets, good])
            # rent payments from 2024-07 onward
            m = dt.date(max(start, dt.date(2024, 7, 1)).year, max(start, dt.date(2024, 7, 1)).month, 1)
            if m < start:
                m = _add_months(m, 1)
            last_m = min(end or cutoff, cutoff)
            while m <= last_m:
                rr = rnd.random()
                late_fee = 0.0
                if m >= dt.date(2025, 5, 1) and rr < 0.06:
                    paid, amt, meth, late = None, None, None, 1 if m < dt.date(2025, 6, 1) else 0
                elif rr < 0.18:
                    paid = m + dt.timedelta(days=rnd.randint(6, 40))
                    amt, meth, late = rent, rnd.choice(["ACH", "CHECK", "CARD"]), 1
                    late_fee = rnd.choice([50.0, 75.0])
                else:
                    paid = m + dt.timedelta(days=rnd.randint(-4, 4))
                    amt = rent if rnd.random() > 0.03 else round(rent * 0.5, 2)
                    meth = rnd.choices(["ACH", "CHECK", "CARD", None], [60, 15, 20, 5])[0]
                    late = 0
                pays.append((None, lid, _d(m), _d(paid) if paid else None, rent, amt, meth, late, late_fee))
                m = _add_months(m, 1)
            if end is None:
                break
            if status == "RENEWED":
                renewal = 1
                start = end + dt.timedelta(days=1)
            else:
                renewal = 0
                start = end + dt.timedelta(days=rnd.randint(1, 75))
            if status == "TERMINATED":
                pass
    # the lease status/renewal of a follow-on lease is recorded on the follow-on row itself
    con.executemany("INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", leases)
    con.executemany("INSERT INTO rent_payments VALUES (?,?,?,?,?,?,?,?,?)", pays)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 3. MOBILE TELECOM
# ---------------------------------------------------------------------------
TEL_DDL = """
CREATE TABLE plans (
    plan_cd         TEXT PRIMARY KEY,
    plan_name       TEXT NOT NULL,
    data_cap_gb     REAL,            -- NULL = unlimited
    list_mrc        REAL,
    is_5g           INTEGER
);
CREATE TABLE subscribers (
    sub_id          INTEGER PRIMARY KEY,
    msisdn          TEXT,
    cust_name       TEXT NOT NULL,
    region          TEXT,
    acct_type       TEXT,
    activation_dt   TEXT,
    churn_dt        TEXT,
    credit_class    TEXT,
    port_in         INTEGER
);
CREATE TABLE addons (
    addon_id        INTEGER PRIMARY KEY,
    addon_name      TEXT,
    monthly_fee     REAL
);
CREATE TABLE sub_addons (
    sub_id          INTEGER REFERENCES subscribers(sub_id),
    addon_id        INTEGER REFERENCES addons(addon_id),
    added_dt        TEXT,
    PRIMARY KEY (sub_id, addon_id)
);
CREATE TABLE monthly_bills (
    bill_id         INTEGER PRIMARY KEY,
    sub_id          INTEGER,          -- undeclared FK -> subscribers
    plan_cd         TEXT,             -- undeclared FK -> plans (text key)
    bill_period     TEXT,             -- 'YYYY-MM' usage month
    stmt_dt         TEXT,             -- statement issue date (month after period)
    due_dt          TEXT,
    paid_dt         TEXT,
    mrc_amt         REAL,
    ovg_amt         REAL,
    roam_amt        REAL,
    tax_amt         REAL,
    data_mb         INTEGER,
    voice_min       INTEGER,
    sms_cnt         INTEGER,
    is_disputed     INTEGER,
    cap_ok          INTEGER           -- 1 = usage stayed within data allowance
);
CREATE TABLE bill_adjustments (
    adj_id          INTEGER PRIMARY KEY,
    bill_id         INTEGER REFERENCES monthly_bills(bill_id),
    adj_amt         REAL,
    reason_cd       TEXT,
    created_dt      TEXT
);
"""

PLANS = [("UNL-MAX", "Unlimited Max", None, 85.0, 1),
         ("UNL-STD", "Unlimited Standard", None, 65.0, 1),
         ("BAS-5G", "Basic 5GB", 5.0, 35.0, 1),
         ("BAS-2G", "Basic 2GB", 2.0, 25.0, 0),
         ("PRE-10", "Prepaid 10", 10.0, 30.0, 0),
         ("FAM-SHR", "Family Share (4 lines)", 40.0, 140.0, 1),
         ("LGC-TT", "Legacy Talk & Text", 0.5, 15.0, 0)]  # no bills
ADDONS = [(1, "Intl Roaming Pass", 10.0), (2, "Cloud 100GB", 3.0), (3, "Device Protection", 12.0),
          (4, "HD Streaming", 5.0), (5, "Hotspot+", 8.0)]


def build_telecom():
    rnd = random.Random(60603)
    con, path = _fresh("telecom")
    con.executescript(TEL_DDL)
    con.executemany("INSERT INTO plans VALUES (?,?,?,?,?)", PLANS)
    con.executemany("INSERT INTO addons VALUES (?,?,?)", ADDONS)
    plan = {p[0]: p for p in PLANS}

    names = _unique_names(rnd, 220)
    subs, sub_plan, sub_addons = [], {}, []
    for sid in range(1, 221):
        acct = rnd.choices(["POSTPAID", "PREPAID", "BUSINESS"], [60, 25, 15])[0]
        region = rnd.choices(["NORTH", "SOUTH", "EAST", "WEST", None], [28, 25, 22, 19, 6])[0]
        act = dt.date(2020, 1, 1) + dt.timedelta(days=rnd.randint(0, 1950))
        churn = None
        if rnd.random() < 0.10:
            churn = dt.date(2025, 1, 15) + dt.timedelta(days=rnd.randint(0, 150))
            if churn <= act:
                churn = None
        cc = rnd.choices(["A", "B", "C", None], [40, 30, 15, 15])[0]
        subs.append((sid, f"+1555{rnd.randint(1000000, 9999999)}", names[sid - 1], region, acct, _d(act),
                     _d(churn) if churn else None, cc, rnd.choice([0, 1])))
        if acct == "PREPAID":
            sub_plan[sid] = "PRE-10"
        elif acct == "BUSINESS":
            sub_plan[sid] = rnd.choice(["UNL-MAX", "UNL-STD", "FAM-SHR"])
        else:
            sub_plan[sid] = rnd.choices(["UNL-MAX", "UNL-STD", "BAS-5G", "BAS-2G", "FAM-SHR"], [20, 30, 25, 15, 10])[0]
        for aid in rnd.sample(range(1, 6), rnd.choices([0, 1, 2, 3], [40, 35, 18, 7])[0]):
            sub_addons.append((sid, aid, _d(act + dt.timedelta(days=rnd.randint(0, 200)))))
    con.executemany("INSERT INTO subscribers VALUES (?,?,?,?,?,?,?,?,?)", subs)
    con.executemany("INSERT INTO sub_addons VALUES (?,?,?)", sub_addons)

    bills, adjs = [], []
    bid = 0
    for s in subs:
        sid, act, churn = s[0], dt.date.fromisoformat(s[5]), (dt.date.fromisoformat(s[6]) if s[6] else None)
        pcd = sub_plan[sid]
        for mo in range(1, 7):
            first = dt.date(2025, mo, 1)
            last = _add_months(first, 1) - dt.timedelta(days=1)
            if act > last or (churn and churn < first):
                continue
            if mo == 4 and rnd.random() < 0.06 and pcd in ("BAS-2G", "BAS-5G", "UNL-STD"):
                pcd = {"BAS-2G": "BAS-5G", "BAS-5G": "UNL-STD", "UNL-STD": "UNL-MAX"}[pcd]
            bid += 1
            p = plan[pcd]
            cap = p[2]
            mrc = p[3]
            if act > first:  # prorated first bill
                mrc = round(mrc * ((last - act).days + 1) / last.day, 2)
            if cap is None:
                mb = rnd.randint(2000, 90000)
            else:
                mb = int(cap * 1024 * rnd.uniform(0.25, 1.35))
            within = 1 if (cap is None or mb <= cap * 1024) else 0
            ovg = 0.0 if within else float(-(-(mb - cap * 1024) // 1024) * 10)
            r = rnd.random()
            roam = None if r < 0.75 else (0.0 if r < 0.85 else round(rnd.uniform(5, 80), 2))
            tax = round(0.08 * (mrc + ovg + (roam or 0)), 2)
            stmt = _add_months(first, 1) + dt.timedelta(days=rnd.randint(0, 2))
            due = stmt + dt.timedelta(days=21)
            rr = rnd.random()
            if rr < (0.20 if mo >= 5 else 0.04):
                paid = None
            elif rr < 0.30:
                paid = due + dt.timedelta(days=rnd.randint(1, 30))
            else:
                paid = stmt + dt.timedelta(days=rnd.randint(2, 21))
            disputed = 1 if rnd.random() < 0.04 else 0
            bills.append((bid, sid, pcd, f"2025-{mo:02d}", _d(stmt), _d(due), _d(paid) if paid else None, mrc,
                          ovg, roam, tax, mb, rnd.randint(20, 1500), rnd.randint(0, 600), disputed, within))
            if rnd.random() < 0.12:
                for _ in range(rnd.choices([1, 2, 3], [65, 25, 10])[0]):
                    adjs.append((None, bid, -round(rnd.uniform(2, 25), 2),
                                 rnd.choices(["OUTAGE", "GOODWILL", "BILLERR"], [45, 35, 20])[0],
                                 _d(stmt + dt.timedelta(days=rnd.randint(1, 40)))))
    con.executemany("INSERT INTO monthly_bills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", bills)
    con.executemany("INSERT INTO bill_adjustments VALUES (?,?,?,?,?)", adjs)
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------------------
# 4. WAREHOUSE INVENTORY MOVEMENTS
# ---------------------------------------------------------------------------
WH_DDL = """
CREATE TABLE items (
    sku_cd          TEXT PRIMARY KEY,
    item_desc       TEXT NOT NULL,
    category        TEXT,
    uom             TEXT,
    unit_wt_kg      REAL,
    std_cost        REAL,
    reorder_pt      INTEGER
);
CREATE TABLE locations (
    loc_id          INTEGER PRIMARY KEY,
    loc_code        TEXT,
    loc_name        TEXT,
    zone            TEXT,
    max_units       INTEGER
);
CREATE TABLE operators (
    operator_id     INTEGER PRIMARY KEY,
    op_name         TEXT,
    shift           TEXT,
    hourly_rate     REAL,
    hire_dt         TEXT,
    forklift_cert   INTEGER
);
CREATE TABLE inv_moves (
    move_id         INTEGER PRIMARY KEY,
    sku_cd          TEXT,             -- undeclared FK -> items
    move_type       TEXT,             -- RCPT, PUTAWAY, PICK, XFER, ADJ, RTN
    from_loc        INTEGER,          -- undeclared FK -> locations (source)
    to_loc          INTEGER,          -- undeclared FK -> locations (destination)
    qty             INTEGER,
    unit_cost       REAL,
    move_ts         TEXT,
    posted_dt       TEXT,
    operator_id     INTEGER REFERENCES operators(operator_id),
    is_damaged      INTEGER,
    scan_ok         INTEGER,          -- 1 = barcode scan succeeded
    ref_doc         TEXT,
    reason_txt      TEXT
);
CREATE TABLE move_exceptions (
    exc_id          INTEGER PRIMARY KEY,
    move_id         INTEGER REFERENCES inv_moves(move_id),
    exc_cd          TEXT,
    units_affected  INTEGER,
    logged_ts       TEXT
);
"""

ITEM_NAMES = [
    ("Nuts & Bolts Kit", "HARDWARE", "BX"), ("Hex Key Set", "HARDWARE", "EA"), ("Wood Screws 4cm", "HARDWARE", "BX"),
    ("Door Hinge (Brass)", "HARDWARE", "EA"), ("Wall Anchors", "HARDWARE", "BX"), ("Cabinet Pull", "HARDWARE", "EA"),
    ("Steel Bracket L", "HARDWARE", "EA"), ("Padlock 40mm", "HARDWARE", "EA"), ("Chain 5m", "HARDWARE", "EA"),
    ("Hand Saw", "HARDWARE", "EA"), ("Claw Hammer", "HARDWARE", "EA"), ("Tape Measure 8m", "HARDWARE", "EA"),
    ("Cable (3m)", "ELECTRICAL", "EA"), ("LED Bulb 9W", "ELECTRICAL", "CS"), ("Extension Lead 4-way", "ELECTRICAL", "EA"),
    ("Wire Nuts", "ELECTRICAL", "BX"), ("Light Switch", "ELECTRICAL", "EA"), ("Circuit Breaker 20A", "ELECTRICAL", "EA"),
    ("Junction Box", "ELECTRICAL", "EA"), ("Fuse Pack", "ELECTRICAL", "BX"), ("Battery AA (24)", "ELECTRICAL", "CS"),
    ("Smoke Alarm", "ELECTRICAL", "EA"), ("Work Light", "ELECTRICAL", "EA"), ("USB Charger", "ELECTRICAL", "EA"),
    ("O'Cedar Mop", "CLEANING", "EA"), ("Bleach 5L", "CLEANING", "EA"), ("Microfiber Cloths", "CLEANING", "BX"),
    ("Floor Cleaner 2L", "CLEANING", "EA"), ("Bucket 12L", "CLEANING", "EA"), ("Rubber Gloves (L)", "CLEANING", "BX"),
    ("Trash Bags 50ct", "CLEANING", "CS"), ("Glass Cleaner", "CLEANING", "EA"), ("Scrub Brush", "CLEANING", "EA"),
    ("Sponge 10pk", "CLEANING", "BX"), ("Degreaser 1L", "CLEANING", "EA"), ("Broom & Dustpan", "CLEANING", "EA"),
    ("Cardboard Box M", "PACKAGING", "CS"), ("Cardboard Box L", "PACKAGING", "CS"), ("Bubble Wrap Roll", "PACKAGING", "EA"),
    ("Packing Tape", "PACKAGING", "CS"), ("Stretch Film", "PACKAGING", "EA"), ("Void Fill Peanuts", "PACKAGING", "KG"),
    ("Mailer Bags", "PACKAGING", "CS"), ("Label Roll 4x6", "PACKAGING", "EA"), ("Corner Protectors", "PACKAGING", "BX"),
    ("Pallet 1200x1000", "PACKAGING", "EA"), ("Strapping Kit", "PACKAGING", "EA"), ("Desiccant Packs", "PACKAGING", "BX"),
    ("Misc Spare Part A", None, "EA"), ("Misc Spare Part B", None, "EA"), ("Sample Kit", None, "BX"),
    ("Promo Display", None, "EA"), ("Ladder 6ft", "HARDWARE", "EA"), ("Safety Vest", None, "EA"),
    ("Hard Hat", None, "EA"), ("Ear Plugs (200)", None, "BX"), ("Toolbox Steel", "HARDWARE", "EA"),
    ("Paint Roller", "CLEANING", "EA"), ("Drum Pump", "HARDWARE", "EA"),
]
LOCATIONS = [(1, "RCV-01", "Receiving Dock 1", "RCV", 5000), (2, "RCV-02", "Receiving Dock 2", "RCV", 5000),
             (3, "A-01", "Aisle A Bay 1", "STO", 2000), (4, "A-02", "Aisle A Bay 2", "STO", 2000),
             (5, "B-01", "Aisle B Bay 1", "STO", 2500), (6, "B-02", "Aisle B Bay 2", "STO", 2500),
             (7, "C-01", "Aisle C Bay 1", "STO", 1500), (8, "OVF-Y", "Overflow (Yard)", "STO", 8000),
             (9, "QA-H", "Quality Hold", "QA", 500), (10, "RET-C", "Returns Cage", "QA", 800),
             (11, "PK-S", "Pack & Ship Station", "SHP", 1000), (12, "SHP-D", "Shipping Dock", "SHP", 4000),
             (13, "MZ-01", "Mezzanine M-01", "STO", 600)]  # never used
OPERATORS = [(1, "Liam O'Reilly", "DAY", 21.5, "2021-04-01", 1), (2, "Fatima Zahra", "DAY", 22.0, "2020-09-14", 1),
             (3, "Chen Wei", "NIGHT", 24.0, "2022-01-03", 1), (4, "Grace Mbeki", "SWING", 22.75, "2023-05-20", 0),
             (5, "Pedro Alves", "NIGHT", 23.5, "2019-11-11", 1), (6, "Hanna Lindqvist", "DAY", 20.0, "2024-02-26", 0),
             (7, "Joe Bianchi", "SWING", 21.0, "2022-08-08", 1), (8, "Amara Obi", "NIGHT", 24.5, "2021-12-01", 1),
             (9, "Kenji Sato", "DAY", 21.25, "2023-03-15", 0), (10, "Ruth Adler", "SWING", 22.0, "2020-06-30", 1),
             (11, "Sven Karlsson", "DAY", 20.5, "2025-01-20", 0)]


def build_warehouse():
    rnd = random.Random(60604)
    con, path = _fresh("warehouse")
    con.executescript(WH_DDL)
    items = []
    for i, (nm, cat, uom) in enumerate(ITEM_NAMES):
        wt = round(rnd.uniform(0.1, 18.0), 2)
        if nm == "Chain 5m":
            wt = 10.0  # exactly on a round threshold
        items.append((f"SKU-{1001 + i}", nm, cat, uom, wt, round(rnd.uniform(1.5, 95.0), 2), rnd.randint(10, 200)))
    items.append(("SKU-1999", "Pallet Wrap (Blue)", "PACKAGING", "EA", 2.4, 18.5, 20))  # never moved
    con.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?)", items)
    con.executemany("INSERT INTO locations VALUES (?,?,?,?,?)", LOCATIONS)
    con.executemany("INSERT INTO operators VALUES (?,?,?,?,?,?)", OPERATORS)

    item_w = [rnd.randint(1, 10) for _ in range(len(ITEM_NAMES))]
    storage = [3, 4, 5, 6, 7, 8]
    moves, excs = [], []
    for mid in range(1, 1401):
        it = rnd.choices(items[:-1], item_w)[0]
        mtype = rnd.choices(["RCPT", "PUTAWAY", "PICK", "XFER", "ADJ", "RTN"], [20, 18, 35, 12, 8, 7])[0]
        reason = None
        ref = None
        if mtype == "RCPT":
            frm, to, qty = None, rnd.choice([1, 2]), rnd.randint(10, 200)
            ref = f"PO-{rnd.randint(40000, 49999)}"
        elif mtype == "PUTAWAY":
            frm, to, qty = rnd.choice([1, 2]), rnd.choice(storage), rnd.randint(10, 150)
        elif mtype == "PICK":
            frm, to, qty = rnd.choice(storage), rnd.choice([11, 11, 12]), rnd.randint(1, 30)
            ref = f"SO-{rnd.randint(70000, 79999)}"
        elif mtype == "XFER":
            frm = rnd.choice(storage + [9])
            to = rnd.choice([l for l in storage + [9] if l != frm])
            qty = rnd.randint(5, 80)
            reason = rnd.choice(["Replenishment", "Replenishment", "QA release", None])
        elif mtype == "ADJ":
            if rnd.random() < 0.5:
                frm, to = rnd.choice(storage), None
            else:
                frm, to = None, rnd.choice(storage)
            qty = rnd.randint(1, 25)
            reason = rnd.choice(["Cycle count", "Cycle count", "Damage write-off", "Found stock"])
        else:  # RTN
            frm, to, qty = None, 10, rnd.randint(1, 12)
            ref = f"RMA-{rnd.randint(1000, 9999)}"
        day = dt.date(2025, 1, 1) + dt.timedelta(days=rnd.randint(0, 180))
        ts = dt.datetime(day.year, day.month, day.day, rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59))
        posted = day + dt.timedelta(days=rnd.choices([0, 1, 2, 3, 4], [55, 25, 10, 6, 4])[0])
        op = None if (mtype == "ADJ" and rnd.random() < 0.5) else rnd.randint(1, 11)
        dmg_p = {"RCPT": 0.06, "RTN": 0.25}.get(mtype, 0.01)
        dmg = 1 if rnd.random() < dmg_p else 0
        scan = 0 if rnd.random() < 0.06 else 1
        moves.append((mid, it[0], mtype, frm, to, qty, round(it[5] * rnd.uniform(0.95, 1.05), 2), _ts(ts), _d(posted),
                       op, dmg, scan, ref, reason))
        if rnd.random() < 0.12:
            for _ in range(rnd.choices([1, 2, 3], [60, 30, 10])[0]):
                excs.append((None, mid, rnd.choice(["SHORT", "OVER", "DMG", "MISLBL"]), rnd.randint(1, 5),
                             _ts(ts + dt.timedelta(minutes=rnd.randint(5, 600)))))
    con.executemany("INSERT INTO inv_moves VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", moves)
    con.executemany("INSERT INTO move_exceptions VALUES (?,?,?,?,?)", excs)
    con.commit()
    con.close()
    return path


BUILDERS = {"food": build_food, "lease": build_lease, "telecom": build_telecom, "warehouse": build_warehouse}


def db_path(name):
    return os.path.join(DATA_DIR, name + ".db")


def build_all():
    return {name: fn() for name, fn in BUILDERS.items()}


if __name__ == "__main__":
    for n, p in build_all().items():
        print(n, p)
