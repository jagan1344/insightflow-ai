"""Held-out development check (written by the developer AFTER tuning on dev_questions.py, BEFORE any engine run on
these items; committed before the first run). Provisional: same author as the engine, so NOT independent evidence.
Two schemas never used during development (library loans, clinic appointments) plus new phrasings on the four dev
schemas. Reference SQL written by hand from the schema."""
from __future__ import annotations

import random
import sqlite3

from dev_schemas import DATA


def build_library():
    p = DATA / "library.db"
    p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE branches (branch_id INTEGER PRIMARY KEY, branch_nm TEXT NOT NULL, borough TEXT NOT NULL);
    CREATE TABLE members (mbr_no INTEGER PRIMARY KEY, mbr_nm TEXT NOT NULL, mbr_type TEXT NOT NULL, yr_joined INTEGER NOT NULL);
    CREATE TABLE titles (isbn TEXT PRIMARY KEY, title_nm TEXT NOT NULL, genre TEXT NOT NULL, pg_cnt INTEGER NOT NULL);
    CREATE TABLE loans (loan_id INTEGER PRIMARY KEY, mbr_no INTEGER NOT NULL REFERENCES members(mbr_no),
        isbn TEXT NOT NULL REFERENCES titles(isbn), checkout_branch_id INTEGER NOT NULL, return_branch_id INTEGER,
        checkout_dt TEXT NOT NULL, due_dt TEXT NOT NULL, returned_dt TEXT, renewal_cnt INTEGER NOT NULL,
        late_fee_amt REAL NOT NULL, is_digital INTEGER NOT NULL);
    CREATE TABLE holds (hold_id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(loan_id), hold_status TEXT NOT NULL);
    """)
    rng = random.Random(31337)
    c.executemany("INSERT INTO branches VALUES (?,?,?)", [(1, "Central", "Midtown"), (2, "Riverside", "West"), (3, "Hillcrest", "North"), (4, "Bayview", "West")])
    c.executemany("INSERT INTO members VALUES (?,?,?,?)", [(i, f"Member {i:03d}", rng.choice(["adult", "student", "senior"]), rng.choice([2019, 2021, 2023, 2024])) for i in range(1, 201)])
    genres = ["mystery", "history", "science", "poetry", "children"]
    titles = [(f"978-{i:05d}", f"Title {i}", rng.choice(genres), rng.randint(80, 900)) for i in range(1, 121)]
    c.executemany("INSERT INTO titles VALUES (?,?,?,?)", titles)
    loans, holds, k = [], [], 0
    for i in range(1, 1201):
        m = rng.randint(1, 12); d = rng.randint(1, 14)
        returned = rng.random() > 0.1
        loans.append((i, rng.randint(1, 200), rng.choice(titles)[0], rng.randint(1, 4), rng.randint(1, 4) if returned else None,
                      f"2025-{m:02d}-{d:02d}", f"2025-{m:02d}-{d + 14:02d}", f"2025-{m:02d}-{d + rng.randint(3, 14):02d}" if returned else None,
                      rng.choice([0, 0, 1, 2]), rng.choice([0.0, 0.0, 0.0, 0.5, 1.25, 3.0]), int(rng.random() < 0.2)))
        if rng.random() < 0.15:
            k += 1; holds.append((k, i, rng.choice(["waiting", "fulfilled", "cancelled"])))
    c.executemany("INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?,?)", loans)
    c.executemany("INSERT INTO holds VALUES (?,?,?)", holds)
    c.commit(); c.close(); return p


def build_clinic():
    p = DATA / "clinic.db"
    p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""
    CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, pt_nm TEXT NOT NULL, insurer TEXT, birth_yr INTEGER NOT NULL);
    CREATE TABLE staff (staff_id INTEGER PRIMARY KEY, staff_nm TEXT NOT NULL, role TEXT NOT NULL);
    CREATE TABLE clinics (clinic_id INTEGER PRIMARY KEY, clinic_nm TEXT NOT NULL, city TEXT NOT NULL);
    CREATE TABLE appointments (appt_id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(patient_id),
        clinic_id INTEGER NOT NULL REFERENCES clinics(clinic_id), booked_by_staff_id INTEGER NOT NULL, seen_by_staff_id INTEGER,
        appt_dt TEXT NOT NULL, checkin_ts TEXT, visit_type TEXT NOT NULL, wait_mins INTEGER, copay_amt REAL NOT NULL,
        billed_amt REAL NOT NULL, no_show INTEGER NOT NULL, is_telehealth INTEGER NOT NULL);
    CREATE TABLE procedures (proc_id INTEGER PRIMARY KEY, appt_id INTEGER NOT NULL REFERENCES appointments(appt_id), proc_cd TEXT NOT NULL, proc_fee REAL NOT NULL);
    """)
    rng = random.Random(2718)
    c.executemany("INSERT INTO patients VALUES (?,?,?,?)", [(i, f"Patient {i:03d}", rng.choice(["Acme Health", "Unity Care", None]), rng.randint(1940, 2015)) for i in range(1, 251)])
    c.executemany("INSERT INTO staff VALUES (?,?,?)", [(1, "Dr. Amari", "physician"), (2, "Dr. Brook", "physician"), (3, "N. Cole", "nurse"),
                                                     (4, "R. Diaz", "receptionist"), (5, "Dr. Evans", "physician")])
    c.executemany("INSERT INTO clinics VALUES (?,?,?)", [(1, "Northgate Clinic", "Avon"), (2, "Lakeside Clinic", "Avon"), (3, "Summit Clinic", "Brill")])
    ap, pr, k = [], [], 0
    for i in range(1, 1001):
        m = rng.randint(1, 12); d = rng.randint(1, 28)
        ns = int(rng.random() < 0.1)
        ap.append((i, rng.randint(1, 250), rng.randint(1, 3), rng.randint(1, 5), None if ns else rng.choice([1, 2, 3, 5]),
                   f"2025-{m:02d}-{d:02d}", None if ns else f"2025-{m:02d}-{d:02d} 09:{rng.randint(10, 59)}:00",
                   rng.choice(["checkup", "follow-up", "urgent"]), None if ns else rng.randint(0, 60), rng.choice([0.0, 20.0, 35.0]),
                   round(rng.uniform(60, 400), 2), ns, int(rng.random() < 0.25)))
        if not ns:
            for _ in range(rng.choice([0, 1, 1, 2])):
                k += 1; pr.append((k, i, rng.choice(["X-RAY", "LAB", "EKG", "VAX"]), rng.choice([25.0, 60.0, 140.0])))
    c.executemany("INSERT INTO appointments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ap)
    c.executemany("INSERT INTO procedures VALUES (?,?,?,?)", pr)
    c.commit(); c.close(); return p


ANCHOR = {"library": "loans", "clinic": "appointments", "bikes": "rentals", "school": "exam_results", "shop": "orders", "support": "tickets"}

Q = {
    "library": [
        ("LB01", "How many loans were made?", "answer", "SELECT COUNT(*) FROM loans", "scalar"),
        ("LB02", "Total late fees", "answer", "SELECT SUM(late_fee_amt) FROM loans", "scalar"),
        ("LB03", "Loans by genre", "answer", "SELECT t.genre, COUNT(*) FROM loans l JOIN titles t ON t.isbn=l.isbn GROUP BY 1", "rowset"),
        ("LB04", "How many loans have not been returned?", "answer", "SELECT COUNT(*) FROM loans WHERE returned_dt IS NULL", "scalar"),
        ("LB05", "Number of digital loans", "answer", "SELECT COUNT(*) FROM loans WHERE is_digital=1", "scalar"),
        ("LB06", "Total late fee amount by member type", "answer",
         "SELECT m.mbr_type, SUM(l.late_fee_amt) FROM loans l JOIN members m ON m.mbr_no=l.mbr_no GROUP BY 1", "rowset"),
        ("LB07", "How many loans were never renewed?", "answer", "SELECT COUNT(*) FROM loans WHERE renewal_cnt=0", "scalar"),
        ("LB08", "How many loans had a hold?", "answer",
         "SELECT COUNT(*) FROM loans l WHERE EXISTS (SELECT 1 FROM holds h WHERE h.loan_id=l.loan_id)", "scalar"),
        ("LB09", "Loans by checkout branch", "answer",
         "SELECT b.branch_nm, COUNT(*) FROM loans l JOIN branches b ON b.branch_id=l.checkout_branch_id GROUP BY 1", "rowset"),
        ("LB10", "Loans by branch", "clarify", None, None),
        ("LB11", "Monthly loans", "answer", "SELECT strftime('%Y-%m', checkout_dt), COUNT(*) FROM loans GROUP BY 1", "rowset"),
        ("LB12", "Top 3 genres by number of loans", "answer",
         "SELECT t.genre, COUNT(*) FROM loans l JOIN titles t ON t.isbn=l.isbn GROUP BY 1 ORDER BY 2 DESC LIMIT 3", "ordered"),
        ("LB13", "Average late fee for mystery loans", "answer",
         "SELECT AVG(l.late_fee_amt) FROM loans l JOIN titles t ON t.isbn=l.isbn WHERE t.genre='mystery'", "scalar"),
        ("LB14", "Percentage of loans that were digital", "answer", "SELECT 100.0*SUM(is_digital)/COUNT(*) FROM loans", "scalar"),
        ("LB15", "How many loans had a waiting hold?", "answer",
         "SELECT COUNT(*) FROM loans l WHERE EXISTS (SELECT 1 FROM holds h WHERE h.loan_id=l.loan_id AND h.hold_status='waiting')", "scalar"),
        ("LB16", "Number of members who borrowed", "answer", "SELECT COUNT(DISTINCT mbr_no) FROM loans", "scalar"),
        ("LB17", "Loans returned to Riverside", "answer",
         "SELECT COUNT(*) FROM loans l JOIN branches b ON b.branch_id=l.return_branch_id WHERE b.branch_nm='Riverside'", "scalar"),
        ("LB18", "Average page count", "either", "SELECT AVG(pg_cnt) FROM titles", "scalar"),
        ("LB19", "Which members are the most avid readers?", "clarify", None, None),
        ("LB20", "Total late fees in the first half of 2025", "answer",
         "SELECT SUM(late_fee_amt) FROM loans WHERE checkout_dt >= '2025-01-01' AND checkout_dt < '2025-07-01'", "scalar"),
        ("LB21", "Late fees for loans with 2 or more renewals", "answer", "SELECT SUM(late_fee_amt) FROM loans WHERE renewal_cnt >= 2", "scalar"),
        ("LB22", "How many loans are overdue today?", "unsupported", None, None),
    ],
    "clinic": [
        ("CL01", "How many appointments were there?", "answer", "SELECT COUNT(*) FROM appointments", "scalar"),
        ("CL02", "Total billed amount by clinic", "answer",
         "SELECT c.clinic_nm, SUM(a.billed_amt) FROM appointments a JOIN clinics c ON c.clinic_id=a.clinic_id GROUP BY 1", "rowset"),
        ("CL03", "Average wait in minutes by visit type", "answer", "SELECT visit_type, AVG(wait_mins) FROM appointments GROUP BY 1", "rowset"),
        ("CL04", "How many appointments were no-shows?", "answer", "SELECT COUNT(*) FROM appointments WHERE no_show=1", "scalar"),
        ("CL05", "How many patients had no insurer?", "either",
         "SELECT COUNT(DISTINCT a.patient_id) FROM appointments a JOIN patients p ON p.patient_id=a.patient_id WHERE p.insurer IS NULL", "scalar"),
        ("CL06", "Number of telehealth appointments by city", "answer",
         "SELECT c.city, COUNT(*) FROM appointments a JOIN clinics c ON c.clinic_id=a.clinic_id WHERE a.is_telehealth=1 GROUP BY 1", "rowset"),
        ("CL07", "Appointments seen by each staff member", "answer",
         "SELECT s.staff_nm, COUNT(*) FROM appointments a JOIN staff s ON s.staff_id=a.seen_by_staff_id GROUP BY 1", "rowset"),
        ("CL08", "Appointments by staff", "clarify", None, None),
        ("CL09", "Appointments booked by R. Diaz", "answer",
         "SELECT COUNT(*) FROM appointments a JOIN staff s ON s.staff_id=a.booked_by_staff_id WHERE s.staff_nm='R. Diaz'", "scalar"),
        ("CL10", "How many appointments had a procedure?", "answer",
         "SELECT COUNT(*) FROM appointments a WHERE EXISTS (SELECT 1 FROM procedures p WHERE p.appt_id=a.appt_id)", "scalar"),
        ("CL11", "How many appointments included an EKG?", "answer",
         "SELECT COUNT(*) FROM appointments a WHERE EXISTS (SELECT 1 FROM procedures p WHERE p.appt_id=a.appt_id AND p.proc_cd='EKG')", "scalar"),
        ("CL12", "Total billed amount minus copay amount", "answer", "SELECT SUM(billed_amt)-SUM(copay_amt) FROM appointments", "scalar"),
        ("CL13", "Monthly billed amount", "answer", "SELECT strftime('%Y-%m', appt_dt), SUM(billed_amt) FROM appointments GROUP BY 1", "rowset"),
        ("CL14", "How many appointments have no check-in time?", "answer", "SELECT COUNT(*) FROM appointments WHERE checkin_ts IS NULL", "scalar"),
        ("CL15", "Average wait for urgent visits", "answer", "SELECT AVG(wait_mins) FROM appointments WHERE visit_type='urgent'", "scalar"),
        ("CL16", "Share of appointments by visit type", "answer",
         "SELECT visit_type, 100.0*COUNT(*)/(SELECT COUNT(*) FROM appointments) FROM appointments GROUP BY 1", "rowset"),
        ("CL17", "Appointments with a wait over 45 minutes", "answer", "SELECT COUNT(*) FROM appointments WHERE wait_mins > 45", "scalar"),
        ("CL18", "Top 2 clinics by billed amount", "answer",
         "SELECT c.clinic_nm, SUM(a.billed_amt) FROM appointments a JOIN clinics c ON c.clinic_id=a.clinic_id GROUP BY 1 ORDER BY 2 DESC LIMIT 2", "ordered"),
        ("CL19", "Percentage of appointments that were no-shows", "answer", "SELECT 100.0*SUM(no_show)/COUNT(*) FROM appointments", "scalar"),
        ("CL20", "Which doctors are most efficient?", "clarify", None, None),
        ("CL21", "Billed amount for patients insured by Unity Care", "answer",
         "SELECT SUM(a.billed_amt) FROM appointments a JOIN patients p ON p.patient_id=a.patient_id WHERE p.insurer='Unity Care'", "scalar"),
        ("CL22", "Expected billed amount next quarter", "unsupported", None, None),
    ],
    "bikes": [
        ("HB01", "Average distance by bike type", "answer",
         "SELECT b.bike_type, AVG(r.dist_km) FROM rentals r JOIN bikes b ON b.bike_id=r.bike_id GROUP BY 1", "rowset"),
        ("HB02", "Number of rentals without GPS problems", "answer", "SELECT COUNT(*) FROM rentals WHERE gps_ok=1", "scalar"),
        ("HB03", "How many rentals had an unresolved issue?", "answer",
         "SELECT COUNT(*) FROM rentals r WHERE EXISTS (SELECT 1 FROM rental_issues i WHERE i.rental_id=r.rental_id AND i.resolved=0)", "scalar"),
        ("HB04", "Fare collected per start station", "answer",
         "SELECT s.stn_nm, SUM(r.fare_amt) FROM rentals r JOIN stations s ON s.station_id=r.start_stn_id GROUP BY 1", "rowset"),
        ("HB05", "Rentals in March 2025 by bike type", "answer",
         "SELECT b.bike_type, COUNT(*) FROM rentals r JOIN bikes b ON b.bike_id=r.bike_id WHERE r.start_ts >= '2025-03-01' AND r.start_ts < '2025-04-01' GROUP BY 1", "rowset"),
    ],
    "school": [
        ("HS01", "Number of retakes by course", "answer",
         "SELECT c.crs_title, COUNT(*) FROM exam_results e JOIN courses c ON c.crs_cd=e.crs_cd WHERE e.is_retake=1 GROUP BY 1", "rowset"),
        ("HS02", "Lowest score in Biology", "answer",
         "SELECT MIN(e.score_pct) FROM exam_results e JOIN courses c ON c.crs_cd=e.crs_cd WHERE c.crs_title='Biology'", "scalar"),
        ("HS03", "How many exams were taken by students in homeroom B-2?", "answer",
         "SELECT COUNT(*) FROM exam_results e JOIN students s ON s.student_id=e.student_id WHERE s.homeroom='B-2'", "scalar"),
        ("HS04", "Exams without a separate room accommodation", "answer",
         "SELECT COUNT(*) FROM exam_results e WHERE NOT EXISTS (SELECT 1 FROM accommodations a WHERE a.result_id=e.result_id AND a.accom_type='separate room')", "scalar"),
    ],
    "shop": [
        ("HP01", "Total refund amount", "either", "SELECT SUM(refund_amt) FROM returns", "scalar"),
        ("HP02", "Number of orders by region", "answer",
         "SELECT c.region, COUNT(*) FROM orders o JOIN customers c ON c.cust_id=o.cust_id GROUP BY 1", "rowset"),
        ("HP03", "Average discount for Enterprise customers", "answer",
         "SELECT AVG(o.disc_amt) FROM orders o JOIN customers c ON c.cust_id=o.cust_id WHERE c.segment='Enterprise'", "scalar"),
        ("HP04", "How many unpaid gift orders?", "answer", "SELECT COUNT(*) FROM orders WHERE is_gift=1 AND paid_ok=0", "scalar"),
        ("HP05", "Orders returned as damaged", "answer",
         "SELECT COUNT(*) FROM orders o WHERE EXISTS (SELECT 1 FROM returns r WHERE r.order_id=o.order_id AND r.reason='damaged')", "scalar"),
    ],
    "support": [
        ("HT01", "Average satisfaction by priority", "clarify", None, None),   # 'satisfaction' is not a schema word in the abbr scheme
        ("HT02", "Number of chat tickets that missed the SLA", "answer", "SELECT COUNT(*) FROM tickets WHERE channel='chat' AND sla_met=0", "scalar"),
        ("HT03", "Tickets tagged outage by month", "answer",
         "SELECT strftime('%Y-%m', opened_ts), COUNT(*) FROM tickets t WHERE EXISTS (SELECT 1 FROM ticket_tags g WHERE g.ticket_id=t.ticket_id AND g.tag='outage') GROUP BY 1", "rowset"),
        ("HT04", "How many tickets did Cho Lee resolve?", "answer",
         "SELECT COUNT(*) FROM tickets t JOIN agents a ON a.agent_id=t.resolved_by_agent_id WHERE a.agent_nm='Cho Lee'", "scalar"),
        ("HT05", "Total reopen count for Silver accounts", "answer",
         "SELECT SUM(t.reopen_cnt) FROM tickets t JOIN accounts a ON a.acct_id=t.acct_id WHERE a.tier='Silver'", "scalar"),
    ],
}
