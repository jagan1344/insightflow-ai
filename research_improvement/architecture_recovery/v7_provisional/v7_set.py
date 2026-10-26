"""v7 PROVISIONAL evaluation set — written by the same developer as the engine (not external, not human-adjudicated).
Written after the engine was frozen and before any engine run on it; its sha256 is recorded in V7_MANIFEST.sha256 in
the commit that precedes the first run. Three domains never used anywhere in this repository: parking citations,
ferry sailings, bakery production. Questions are phrased the way a user would ask, including words the schema does
not contain; they were not filtered for what the engine supports. Reference SQL written by hand from the schema.

expect: 'answer' (reference SQL), 'clarify' / 'unsupported' (should not be answered), 'either' (asking is fine; an
answer must match the reference)."""
from __future__ import annotations

import pathlib
import random
import sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"


def build_parking():
    DATA.mkdir(exist_ok=True)
    p = DATA / "parking.db"; p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE areas (area_id INTEGER PRIMARY KEY, area_nm TEXT NOT NULL, borough TEXT NOT NULL, meter_rate REAL NOT NULL);
    CREATE TABLE officers (badge_no INTEGER PRIMARY KEY, officer_nm TEXT NOT NULL, unit TEXT NOT NULL);
    CREATE TABLE citations (citation_id INTEGER PRIMARY KEY, area_id INTEGER NOT NULL REFERENCES areas(area_id),
        badge_no INTEGER NOT NULL REFERENCES officers(badge_no), issued_dt TEXT NOT NULL, paid_dt TEXT,
        violation TEXT NOT NULL, fine_amt REAL NOT NULL, late_fee_amt REAL NOT NULL, plate_state TEXT,
        is_towed INTEGER NOT NULL, contested INTEGER NOT NULL);
    CREATE TABLE appeals (appeal_id INTEGER PRIMARY KEY, citation_id INTEGER NOT NULL REFERENCES citations(citation_id),
        outcome TEXT NOT NULL, hearing_dt TEXT NOT NULL);
    """)
    rng = random.Random(6061)
    c.executemany("INSERT INTO areas VALUES (?,?,?,?)", [(1, "Old Town", "Central", 2.5), (2, "Harbourfront", "East", 3.0),
                                                        (3, "Mill Lane", "West", 1.5), (4, "Station Plaza", "Central", 3.5)])
    c.executemany("INSERT INTO officers VALUES (?,?,?)", [(101, "K. Osei", "Day"), (102, "L. Varga", "Day"), (103, "M. Quist", "Night"), (104, "N. Roy", "Night")])
    cit, app, k = [], [], 0
    for i in range(1, 1501):
        m = rng.randint(1, 12); d = rng.randint(1, 25)
        paid = rng.random() > 0.25
        fine = rng.choice([35.0, 50.0, 75.0, 120.0])
        cit.append((i, rng.randint(1, 4), rng.choice([101, 102, 103, 104]), f"2025-{m:02d}-{d:02d}",
                    f"2025-{m:02d}-{d + rng.randint(1, 3):02d}" if paid else None,
                    rng.choice(["expired meter", "no permit", "hydrant", "double parked"]), fine,
                    0.0 if paid else rng.choice([0.0, 15.0, 25.0]), rng.choice(["NY", "NJ", "CT", None]),
                    int(rng.random() < 0.05), int(rng.random() < 0.12)))
        if cit[-1][-1] == 1 and rng.random() < 0.8:
            k += 1; app.append((k, i, rng.choice(["upheld", "dismissed", "reduced"]), f"2025-{m:02d}-{min(28, d + 3):02d}"))
    c.executemany("INSERT INTO citations VALUES (?,?,?,?,?,?,?,?,?,?,?)", cit)
    c.executemany("INSERT INTO appeals VALUES (?,?,?,?)", app)
    c.commit(); c.close(); return p


def build_ferry():
    DATA.mkdir(exist_ok=True)
    p = DATA / "ferry.db"; p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE terminals (terminal_cd TEXT PRIMARY KEY, terminal_nm TEXT NOT NULL, island TEXT NOT NULL);
    CREATE TABLE vessels (vessel_id INTEGER PRIMARY KEY, vessel_nm TEXT NOT NULL, pax_capacity INTEGER NOT NULL, built_yr INTEGER NOT NULL);
    CREATE TABLE sailings (sailing_id INTEGER PRIMARY KEY, vessel_id INTEGER NOT NULL REFERENCES vessels(vessel_id),
        dep_terminal_cd TEXT NOT NULL, arr_terminal_cd TEXT NOT NULL, sched_dep_ts TEXT NOT NULL, actual_dep_ts TEXT,
        pax_count INTEGER NOT NULL, vehicle_count INTEGER NOT NULL, fuel_litres REAL NOT NULL, ticket_rev REAL NOT NULL,
        delay_mins INTEGER, cancelled INTEGER NOT NULL);
    CREATE TABLE incidents (incident_id INTEGER PRIMARY KEY, sailing_id INTEGER NOT NULL REFERENCES sailings(sailing_id),
        severity TEXT NOT NULL);
    """)
    rng = random.Random(4127)
    terms = [("NTH", "North Quay", "Mainland"), ("STH", "South Pier", "Mainland"), ("BRK", "Brackwater", "Isle of Brack"), ("FEN", "Fenmouth", "Fen Island")]
    c.executemany("INSERT INTO terminals VALUES (?,?,?)", terms)
    c.executemany("INSERT INTO vessels VALUES (?,?,?,?)", [(1, "MV Petrel", 400, 2004), (2, "MV Gannet", 650, 2012), (3, "MV Tern", 250, 1998)])
    sl, inc, k = [], [], 0
    for i in range(1, 1201):
        m = rng.randint(1, 12); d = rng.randint(1, 28)
        a, b = rng.sample([t[0] for t in terms], 2)
        canc = int(rng.random() < 0.06)
        delay = None if canc else rng.choice([0, 0, 0, 5, 10, 25, 60])
        pax = 0 if canc else rng.randint(20, 380)
        sl.append((i, rng.randint(1, 3), a, b, f"2025-{m:02d}-{d:02d} {rng.choice([7, 10, 13, 16, 19]):02d}:00:00",
                   None if canc else f"2025-{m:02d}-{d:02d} 08:{rng.randint(0, 59):02d}:00", pax, 0 if canc else rng.randint(0, 60),
                   0.0 if canc else round(rng.uniform(300, 1200), 1), 0.0 if canc else round(pax * rng.uniform(8, 15), 2), delay, canc))
        if not canc and rng.random() < 0.07:
            k += 1; inc.append((k, i, rng.choice(["minor", "major"])))
    c.executemany("INSERT INTO sailings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", sl)
    c.executemany("INSERT INTO incidents VALUES (?,?,?)", inc)
    c.commit(); c.close(); return p


def build_bakery():
    DATA.mkdir(exist_ok=True)
    p = DATA / "bakery.db"; p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE recipes (recipe_id INTEGER PRIMARY KEY, recipe_nm TEXT NOT NULL, category TEXT NOT NULL, is_gluten_free INTEGER NOT NULL);
    CREATE TABLE bakers (baker_id INTEGER PRIMARY KEY, baker_nm TEXT NOT NULL, shift TEXT NOT NULL);
    CREATE TABLE batches (batch_id INTEGER PRIMARY KEY, recipe_id INTEGER NOT NULL REFERENCES recipes(recipe_id),
        mixed_by_baker_id INTEGER NOT NULL, checked_by_baker_id INTEGER, bake_dt TEXT NOT NULL, units_made INTEGER NOT NULL,
        units_wasted INTEGER NOT NULL, flour_kg REAL NOT NULL, unit_cost REAL NOT NULL, oven_temp_c INTEGER NOT NULL,
        passed_qc INTEGER NOT NULL);
    CREATE TABLE complaints (complaint_id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL REFERENCES batches(batch_id), reason TEXT NOT NULL);
    """)
    rng = random.Random(8080)
    c.executemany("INSERT INTO recipes VALUES (?,?,?,?)", [(1, "Sourdough Loaf", "bread", 0), (2, "Rye Loaf", "bread", 0), (3, "Almond Croissant", "pastry", 0),
                                                          (4, "Flourless Brownie", "cake", 1), (5, "Lemon Tart", "pastry", 0), (6, "Rice Bread", "bread", 1)])
    c.executemany("INSERT INTO bakers VALUES (?,?,?)", [(1, "Ines", "early"), (2, "Joon", "early"), (3, "Kofi", "late"), (4, "Lena", "late")])
    bt, cp, k = [], [], 0
    for i in range(1, 901):
        m = rng.randint(1, 12); d = rng.randint(1, 28)
        made = rng.randint(20, 200)
        bt.append((i, rng.randint(1, 6), rng.randint(1, 4), None if rng.random() < 0.15 else rng.randint(1, 4), f"2025-{m:02d}-{d:02d}",
                   made, rng.randint(0, made // 8), round(made * rng.uniform(0.05, 0.12), 2), round(rng.uniform(0.4, 2.2), 2),
                   rng.choice([180, 200, 220, 240]), int(rng.random() > 0.09)))
        if rng.random() < 0.06:
            k += 1; cp.append((k, i, rng.choice(["burnt", "underbaked", "foreign object", "stale"])))
    c.executemany("INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?,?)", bt)
    c.executemany("INSERT INTO complaints VALUES (?,?,?)", cp)
    c.commit(); c.close(); return p


BUILD = {"parking": build_parking, "ferry": build_ferry, "bakery": build_bakery}
ANCHOR = {"parking": "citations", "ferry": "sailings", "bakery": "batches"}

Q = {
    "parking": [
        ("PK01", "How many citations were issued?", "answer", "SELECT COUNT(*) FROM citations", "scalar"),
        ("PK02", "Total fines", "answer", "SELECT SUM(fine_amt) FROM citations", "scalar"),
        ("PK03", "Total fine amount by area", "answer",
         "SELECT a.area_nm, SUM(c.fine_amt) FROM citations c JOIN areas a ON a.area_id=c.area_id GROUP BY 1", "rowset"),
        ("PK04", "How many citations are still unpaid?", "answer", "SELECT COUNT(*) FROM citations WHERE paid_dt IS NULL", "scalar"),
        ("PK05", "Number of citations by violation", "answer", "SELECT violation, COUNT(*) FROM citations GROUP BY 1", "rowset"),
        ("PK06", "How many cars were towed?", "answer", "SELECT COUNT(*) FROM citations WHERE is_towed=1", "scalar"),
        ("PK07", "Citations written by each officer", "answer",
         "SELECT o.officer_nm, COUNT(*) FROM citations c JOIN officers o ON o.badge_no=c.badge_no GROUP BY 1", "rowset"),
        ("PK08", "Total late fees for the Night unit", "answer",
         "SELECT SUM(c.late_fee_amt) FROM citations c JOIN officers o ON o.badge_no=c.badge_no WHERE o.unit='Night'", "scalar"),
        ("PK09", "How many citations were appealed?", "answer",
         "SELECT COUNT(*) FROM citations c WHERE EXISTS (SELECT 1 FROM appeals a WHERE a.citation_id=c.citation_id)", "scalar"),
        ("PK10", "How many citations had an appeal that was dismissed?", "answer",
         "SELECT COUNT(*) FROM citations c WHERE EXISTS (SELECT 1 FROM appeals a WHERE a.citation_id=c.citation_id AND a.outcome='dismissed')", "scalar"),
        ("PK11", "Monthly fine amount", "either", "SELECT substr(issued_dt,1,7), SUM(fine_amt) FROM citations GROUP BY 1", "rowset"),
        ("PK12", "Fines issued in March 2025", "answer",
         "SELECT SUM(fine_amt) FROM citations WHERE issued_dt >= '2025-03-01' AND issued_dt < '2025-04-01'", "scalar"),
        ("PK13", "Number of citations issued in the second quarter of 2025", "answer",
         "SELECT COUNT(*) FROM citations WHERE issued_dt >= '2025-04-01' AND issued_dt < '2025-07-01'", "scalar"),
        ("PK14", "Citations with no plate state recorded", "answer", "SELECT COUNT(*) FROM citations WHERE plate_state IS NULL", "scalar"),
        ("PK15", "Average fine for hydrant violations", "answer", "SELECT AVG(fine_amt) FROM citations WHERE violation='hydrant'", "scalar"),
        ("PK16", "Total fine amount plus late fee amount", "answer", "SELECT SUM(fine_amt)+SUM(late_fee_amt) FROM citations", "scalar"),
        ("PK17", "Share of citations by borough", "answer",
         "SELECT a.borough, 100.0*COUNT(*)/(SELECT COUNT(*) FROM citations) FROM citations c JOIN areas a ON a.area_id=c.area_id GROUP BY 1", "rowset"),
        ("PK18", "Percentage of citations that were contested", "answer", "SELECT 100.0*SUM(contested)/COUNT(*) FROM citations", "scalar"),
        ("PK19", "Top 2 areas by total fines", "answer",
         "SELECT a.area_nm, SUM(c.fine_amt) FROM citations c JOIN areas a ON a.area_id=c.area_id GROUP BY 1 ORDER BY 2 DESC LIMIT 2", "ordered"),
        ("PK20", "Number of fines over 100 dollars", "answer", "SELECT COUNT(*) FROM citations WHERE fine_amt > 100", "scalar"),
        ("PK21", "How much revenue did parking enforcement bring in?", "clarify", None, None),
        ("PK22", "Which officers are the strictest?", "clarify", None, None),
        ("PK23", "Average meter rate", "either", "SELECT AVG(meter_rate) FROM areas", "scalar"),
        ("PK24", "How many citations will be paid next month?", "unsupported", None, None),
        ("PK25", "Citations from New Jersey plates that were not paid", "answer",
         "SELECT COUNT(*) FROM citations WHERE plate_state='NJ' AND paid_dt IS NULL", "scalar"),
    ],
    "ferry": [
        ("FR01", "How many sailings were there?", "answer", "SELECT COUNT(*) FROM sailings", "scalar"),
        ("FR02", "Total passengers carried", "answer", "SELECT SUM(pax_count) FROM sailings", "scalar"),
        ("FR03", "Total ticket revenue by vessel", "answer",
         "SELECT v.vessel_nm, SUM(s.ticket_rev) FROM sailings s JOIN vessels v ON v.vessel_id=s.vessel_id GROUP BY 1", "rowset"),
        ("FR04", "How many sailings were cancelled?", "answer", "SELECT COUNT(*) FROM sailings WHERE cancelled=1", "scalar"),
        ("FR05", "Average delay in minutes", "answer", "SELECT AVG(delay_mins) FROM sailings", "scalar"),
        ("FR06", "Sailings by departure terminal", "answer",
         "SELECT t.terminal_nm, COUNT(*) FROM sailings s JOIN terminals t ON t.terminal_cd=s.dep_terminal_cd GROUP BY 1", "rowset"),
        ("FR07", "Passengers by terminal", "clarify", None, None),
        ("FR08", "Total passengers arriving at Brackwater", "answer",
         "SELECT SUM(s.pax_count) FROM sailings s JOIN terminals t ON t.terminal_cd=s.arr_terminal_cd WHERE t.terminal_nm='Brackwater'", "scalar"),
        ("FR09", "How many sailings had an incident?", "answer",
         "SELECT COUNT(*) FROM sailings s WHERE EXISTS (SELECT 1 FROM incidents i WHERE i.sailing_id=s.sailing_id)", "scalar"),
        ("FR10", "Sailings with a major incident", "answer",
         "SELECT COUNT(*) FROM sailings s WHERE EXISTS (SELECT 1 FROM incidents i WHERE i.sailing_id=s.sailing_id AND i.severity='major')", "scalar"),
        ("FR11", "Fuel used per passenger", "answer", "SELECT SUM(fuel_litres)*1.0/SUM(pax_count) FROM sailings", "scalar"),
        ("FR12", "Total ticket revenue in July 2025", "either",
         "SELECT SUM(ticket_rev) FROM sailings WHERE sched_dep_ts >= '2025-07-01' AND sched_dep_ts < '2025-08-01'", "scalar"),
        ("FR13", "Monthly passengers", "either", "SELECT substr(sched_dep_ts,1,7), SUM(pax_count) FROM sailings GROUP BY 1", "rowset"),
        ("FR14", "Sailings that never actually departed", "answer", "SELECT COUNT(*) FROM sailings WHERE actual_dep_ts IS NULL", "scalar"),
        ("FR15", "Average passengers per sailing on the MV Gannet", "answer",
         "SELECT AVG(s.pax_count) FROM sailings s JOIN vessels v ON v.vessel_id=s.vessel_id WHERE v.vessel_nm='MV Gannet'", "scalar"),
        ("FR16", "Sailings delayed more than 20 minutes", "answer", "SELECT COUNT(*) FROM sailings WHERE delay_mins > 20", "scalar"),
        ("FR17", "Top 2 vessels by passengers carried", "answer",
         "SELECT v.vessel_nm, SUM(s.pax_count) FROM sailings s JOIN vessels v ON v.vessel_id=s.vessel_id GROUP BY 1 ORDER BY 2 DESC LIMIT 2", "ordered"),
        ("FR18", "Percentage of sailings cancelled", "answer", "SELECT 100.0*SUM(cancelled)/COUNT(*) FROM sailings", "scalar"),
        ("FR19", "Total vehicles carried from the mainland", "either",
         "SELECT SUM(s.vehicle_count) FROM sailings s JOIN terminals t ON t.terminal_cd=s.dep_terminal_cd WHERE t.island='Mainland'", "scalar"),
        ("FR20", "How punctual is the fleet?", "clarify", None, None),
        ("FR21", "Average vessel capacity", "either", "SELECT AVG(pax_capacity) FROM vessels", "scalar"),
        ("FR22", "Load factor by vessel", "clarify", None, None),
        ("FR23", "Number of sailings with no delay recorded", "answer", "SELECT COUNT(*) FROM sailings WHERE delay_mins IS NULL", "scalar"),
        ("FR24", "Revenue per sailing", "either", "SELECT AVG(ticket_rev) FROM sailings", "scalar"),
        ("FR25", "Ticket revenue by departure island", "answer",
         "SELECT t.island, SUM(s.ticket_rev) FROM sailings s JOIN terminals t ON t.terminal_cd=s.dep_terminal_cd GROUP BY 1", "rowset"),
    ],
    "bakery": [
        ("BA01", "How many batches were baked?", "answer", "SELECT COUNT(*) FROM batches", "scalar"),
        ("BA02", "Total units made", "answer", "SELECT SUM(units_made) FROM batches", "scalar"),
        ("BA03", "Units wasted by recipe", "answer",
         "SELECT r.recipe_nm, SUM(b.units_wasted) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id GROUP BY 1", "rowset"),
        ("BA04", "How many batches failed QC?", "answer", "SELECT COUNT(*) FROM batches WHERE passed_qc=0", "scalar"),
        ("BA05", "Total flour used in kg", "answer", "SELECT SUM(flour_kg) FROM batches", "scalar"),
        ("BA06", "Units made by category", "answer",
         "SELECT r.category, SUM(b.units_made) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id GROUP BY 1", "rowset"),
        ("BA07", "Batches mixed by each baker", "answer",
         "SELECT k.baker_nm, COUNT(*) FROM batches b JOIN bakers k ON k.baker_id=b.mixed_by_baker_id GROUP BY 1", "rowset"),
        ("BA08", "Batches by baker", "clarify", None, None),
        ("BA09", "How many batches were not checked?", "answer", "SELECT COUNT(*) FROM batches WHERE checked_by_baker_id IS NULL", "scalar"),
        ("BA10", "Total production cost", "clarify", None, None),     # units_made * unit_cost is one reading; not stated
        ("BA11", "Total units made times unit cost", "answer", "SELECT SUM(units_made*unit_cost) FROM batches", "scalar"),
        ("BA12", "Units wasted divided by units made", "answer", "SELECT SUM(units_wasted)*1.0/SUM(units_made) FROM batches", "scalar"),
        ("BA13", "How many batches got a complaint?", "answer",
         "SELECT COUNT(*) FROM batches b WHERE EXISTS (SELECT 1 FROM complaints c WHERE c.batch_id=b.batch_id)", "scalar"),
        ("BA14", "Batches with a burnt complaint", "answer",
         "SELECT COUNT(*) FROM batches b WHERE EXISTS (SELECT 1 FROM complaints c WHERE c.batch_id=b.batch_id AND c.reason='burnt')", "scalar"),
        ("BA15", "Units made of gluten-free recipes", "answer",
         "SELECT SUM(b.units_made) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id WHERE r.is_gluten_free=1", "scalar"),
        ("BA16", "Monthly units made", "answer", "SELECT substr(bake_dt,1,7), SUM(units_made) FROM batches GROUP BY 1", "rowset"),
        ("BA17", "Units made in the first half of 2025", "answer",
         "SELECT SUM(units_made) FROM batches WHERE bake_dt >= '2025-01-01' AND bake_dt < '2025-07-01'", "scalar"),
        ("BA18", "Average oven temperature for Sourdough Loaf batches", "answer",
         "SELECT AVG(b.oven_temp_c) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id WHERE r.recipe_nm='Sourdough Loaf'", "scalar"),
        ("BA19", "Top 3 recipes by units wasted", "answer",
         "SELECT r.recipe_nm, SUM(b.units_wasted) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id GROUP BY 1 ORDER BY 2 DESC LIMIT 3", "ordered"),
        ("BA20", "Percentage of batches that passed QC", "answer", "SELECT 100.0*SUM(passed_qc)/COUNT(*) FROM batches", "scalar"),
        ("BA21", "Which bakers are most careful?", "clarify", None, None),
        ("BA22", "Batches baked at 240 degrees or more", "answer", "SELECT COUNT(*) FROM batches WHERE oven_temp_c >= 240", "scalar"),
        ("BA23", "Batches checked by Lena", "answer",
         "SELECT COUNT(*) FROM batches b JOIN bakers k ON k.baker_id=b.checked_by_baker_id WHERE k.baker_nm='Lena'", "scalar"),
        ("BA24", "Waste rate by shift", "clarify", None, None),
        ("BA25", "Batches without any complaint for pastry recipes", "answer",
         "SELECT COUNT(*) FROM batches b JOIN recipes r ON r.recipe_id=b.recipe_id WHERE r.category='pastry' AND NOT EXISTS (SELECT 1 FROM complaints c WHERE c.batch_id=b.batch_id)", "scalar"),
    ],
}
