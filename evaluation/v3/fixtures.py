"""Independent relational fixtures for multi-table generalization tests.

Nothing here imports the production planner. Each builder writes a
deterministic SQLite file and returns a frozen ground-truth manifest of
the relationships that really exist (and decoys that must NOT be joined).

Schema A "clinic": snake_case, FOREIGN KEYs declared, bridge table,
  role-ambiguous path (clinic via doctor vs via patient home clinic),
  nullable FKs, duplicate-looking clinic names, two date columns,
  a clinic/insurer with zero fact rows, NULL measure values.
Schema B "logistics": different naming (_key/_ref/_no), NO declared FKs
  (relationships only inferable), role-playing dimension (origin/dest hub),
  one-to-many child table (parcels), bridge (shipment_tags), and decoys:
  same-named non-key columns and small-int columns that coincide with
  unrelated key ranges.
"""
from __future__ import annotations

import pathlib
import random
import sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------- A -----
A_DDL = """
CREATE TABLE clinics (clinic_id INTEGER PRIMARY KEY, clinic_name TEXT NOT NULL, city TEXT NOT NULL);
CREATE TABLE insurers (insurer_id INTEGER PRIMARY KEY, insurer_name TEXT NOT NULL);
CREATE TABLE doctors (doctor_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, specialty TEXT NOT NULL,
  clinic_id INTEGER REFERENCES clinics(clinic_id));
CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, patient_name TEXT NOT NULL,
  insurer_id INTEGER REFERENCES insurers(insurer_id),
  home_clinic_id INTEGER REFERENCES clinics(clinic_id));
CREATE TABLE procedures (procedure_id INTEGER PRIMARY KEY, procedure_name TEXT NOT NULL, category TEXT NOT NULL);
CREATE TABLE visits (visit_id INTEGER PRIMARY KEY, visit_date TEXT NOT NULL, discharge_date TEXT,
  patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
  doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id),
  fee REAL NOT NULL, copay REAL);
CREATE TABLE visit_procedures (visit_id INTEGER NOT NULL REFERENCES visits(visit_id),
  procedure_id INTEGER NOT NULL REFERENCES procedures(procedure_id), units INTEGER NOT NULL,
  PRIMARY KEY (visit_id, procedure_id));
"""

A_EDGES = {  # (child_table, child_col, parent_table, parent_col)
    ("doctors", "clinic_id", "clinics", "clinic_id"),
    ("patients", "insurer_id", "insurers", "insurer_id"),
    ("patients", "home_clinic_id", "clinics", "clinic_id"),
    ("visits", "patient_id", "patients", "patient_id"),
    ("visits", "doctor_id", "doctors", "doctor_id"),
    ("visit_procedures", "visit_id", "visits", "visit_id"),
    ("visit_procedures", "procedure_id", "procedures", "procedure_id"),
}
A_DECOYS: set = set()


def build_a(path=None) -> pathlib.Path:
    path = pathlib.Path(path or DATA / "clinic.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(7001)
    c = sqlite3.connect(str(path))
    c.executescript(A_DDL)
    c.executemany("INSERT INTO clinics VALUES (?,?,?)", [
        (1, "St. Mary's Clinic", "Springfield"), (2, "Saint Mary's Clinic", "Portland"),
        (3, "Riverside Health & Wellness", "Springfield"), (4, "Lakeview Clinic", "Portland"),
        (5, "Old Mill Annex", "Springfield")])           # 5: no doctors, no visits
    c.executemany("INSERT INTO insurers VALUES (?,?)", [
        (1, "Blue Shield"), (2, "Aetna"), (3, "United Health"),
        (4, "Medicaid (State)"), (5, "Pacific Mutual")])   # 5: no patients
    specs = ["Cardiology", "Pediatrics", "Ear, Nose & Throat", "General Practice"]
    docs = []
    for i in range(1, 13):
        clinic = None if i in (11, 12) else rng.choice([1, 2, 3, 4])   # locums
        docs.append((i, f"Dr. {chr(64 + i)}. Okafor-{i}", specs[i % 4], clinic))
    c.executemany("INSERT INTO doctors VALUES (?,?,?,?)", docs)
    pats = []
    for i in range(1, 81):
        ins = None if i % 8 == 0 else rng.choice([1, 2, 3, 4])
        pats.append((i, f"Patient {i:03d}", ins, rng.choice([1, 2, 3, 4])))
    c.executemany("INSERT INTO patients VALUES (?,?,?,?)", pats)
    procs = [(1, "X-Ray", "Imaging"), (2, "MRI", "Imaging"), (3, "Blood Panel", "Lab"),
             (4, "ECG", "Cardiac"), (5, "Flu Shot", "Preventive"), (6, "Cast Fitting", "Ortho"),
             (7, "Allergy Test", "Lab"), (8, "Consultation", "General")]
    c.executemany("INSERT INTO procedures VALUES (?,?,?)", procs)
    visits, vp = [], []
    for v in range(1, 601):
        m = rng.randint(1, 12)
        d = f"2025-{m:02d}-{rng.randint(1, 28):02d}"
        dis = None if rng.random() < 0.15 else f"2025-{m:02d}-28"
        fee = round(rng.uniform(40, 900), 2)
        copay = None if rng.random() < 0.2 else round(fee * rng.uniform(0.05, 0.3), 2)
        visits.append((v, d, dis, rng.randint(1, 80), rng.randint(1, 12), fee, copay))
        for p in rng.sample(range(1, 9), rng.randint(0, 3)):
            vp.append((v, p, rng.randint(1, 4)))
    c.executemany("INSERT INTO visits VALUES (?,?,?,?,?,?,?)", visits)
    c.executemany("INSERT INTO visit_procedures VALUES (?,?,?)", vp)
    c.commit(); c.close()
    return path


# ---------------------------------------------------------------- B -----
B_DDL = """
CREATE TABLE carriers (carrier_key INTEGER PRIMARY KEY, carrier_label TEXT NOT NULL, mode TEXT NOT NULL, region_code TEXT);
CREATE TABLE hubs (hub_key INTEGER PRIMARY KEY, hub_label TEXT NOT NULL, region_code TEXT, country TEXT NOT NULL);
CREATE TABLE customers (cust_key INTEGER PRIMARY KEY, cust_label TEXT NOT NULL, tier TEXT);
CREATE TABLE tags (tag_key INTEGER PRIMARY KEY, tag_label TEXT NOT NULL);
CREATE TABLE shipments (shp_no INTEGER PRIMARY KEY, ship_dt TEXT NOT NULL, delivered_dt TEXT,
  origin_hub INTEGER NOT NULL, dest_hub INTEGER NOT NULL, carrier_ref INTEGER, cust_ref INTEGER NOT NULL,
  priority_code INTEGER NOT NULL, weight_kg REAL NOT NULL, freight_usd REAL NOT NULL, insured_usd REAL);
CREATE TABLE parcels (parcel_id INTEGER PRIMARY KEY, shp_no INTEGER NOT NULL, parcel_kg REAL NOT NULL);
CREATE TABLE shipment_tags (shp_no INTEGER NOT NULL, tag_key INTEGER NOT NULL, PRIMARY KEY (shp_no, tag_key));
"""

B_EDGES = {
    ("shipments", "origin_hub", "hubs", "hub_key"),
    ("shipments", "dest_hub", "hubs", "hub_key"),
    ("shipments", "carrier_ref", "carriers", "carrier_key"),
    ("shipments", "cust_ref", "customers", "cust_key"),
    ("parcels", "shp_no", "shipments", "shp_no"),
    ("shipment_tags", "shp_no", "shipments", "shp_no"),
    ("shipment_tags", "tag_key", "tags", "tag_key"),
}
# Looks relational but is NOT: same column name / values coincide with a key range.
B_DECOYS = {
    ("hubs", "region_code", "carriers", "region_code"),
    ("carriers", "region_code", "hubs", "region_code"),
    ("shipments", "priority_code", "carriers", "carrier_key"),
    ("shipments", "priority_code", "tags", "tag_key"),
    ("shipments", "priority_code", "hubs", "hub_key"),
}


def build_b(path=None) -> pathlib.Path:
    path = pathlib.Path(path or DATA / "logistics.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(9002)
    c = sqlite3.connect(str(path))
    c.executescript(B_DDL)
    c.executemany("INSERT INTO carriers VALUES (?,?,?,?)", [
        (1, "Blue Jay Freight", "Road", "NA-E"), (2, "Trans-Pacific Air", "Air", "AP"),
        (3, "O'Brien & Sons", "Road", "NA-W"), (4, "Nordic Sea Lines", "Sea", "EU"),
        (5, "Sky Cargo (Intl)", "Air", "EU"), (6, "Dormant Haulage", "Road", "AF")])  # 6: no shipments
    c.executemany("INSERT INTO hubs VALUES (?,?,?,?)", [
        (1, "Port of Rotterdam", "EU", "Netherlands"), (2, "Chicago O'Hare Hub", "NA-E", "USA"),
        (3, "Singapore Changi", "AP", "Singapore"), (4, "Los Angeles Gateway", "NA-W", "USA"),
        (5, "Hamburg Terminal", "EU", "Germany"), (6, "Lagos Depot", "AF", "Nigeria")])
    c.executemany("INSERT INTO customers VALUES (?,?,?)", [
        (i, f"Customer {chr(64 + (i % 26) or 26)}{i}", rng.choice(["Gold", "Silver", None]))
        for i in range(1, 41)])
    c.executemany("INSERT INTO tags VALUES (?,?)", [
        (1, "Fragile"), (2, "Perishable"), (3, "Hazmat / Class 3"), (4, "High-value"), (5, "Oversize")])
    ships, parcels, st = [], [], []
    pid = 1
    for s in range(1, 501):
        m = rng.randint(1, 12)
        d = f"2025-{m:02d}-{rng.randint(1, 27):02d}"
        deliv = None if rng.random() < 0.1 else f"2025-{m:02d}-28"
        o, de = rng.sample([1, 2, 3, 4, 5, 6], 2)
        carrier = None if rng.random() < 0.08 else rng.choice([1, 2, 3, 4, 5])
        w = round(rng.uniform(1, 500), 1)
        freight = round(w * rng.uniform(1.5, 6), 2)
        ins = None if rng.random() < 0.3 else round(freight * rng.uniform(2, 10), 2)
        ships.append((s, d, deliv, o, de, carrier, rng.randint(1, 40), rng.randint(1, 5), w, freight, ins))
        for _ in range(rng.randint(1, 4)):
            parcels.append((pid, s, round(w / 3, 1))); pid += 1
        for t in rng.sample(range(1, 6), rng.randint(0, 3)):
            st.append((s, t))
    c.executemany("INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?,?,?)", ships)
    c.executemany("INSERT INTO parcels VALUES (?,?,?)", parcels)
    c.executemany("INSERT INTO shipment_tags VALUES (?,?)", st)
    c.commit(); c.close()
    return path


if __name__ == "__main__":
    print(build_a()); print(build_b())
