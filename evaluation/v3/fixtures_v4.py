"""Additional unfamiliar relational schemas (round 4). Kept separate from
fixtures.py so FINAL_SEAL.txt (schema C seal) stays verifiable.

D "retail"  : header/detail (orders -> order_lines), measure expressions
              (qty*price), header-level money (shipping_fee) that duplicates
              when joined to lines, guest orders (NULL customer), two date
              columns on the HEADER (not on the line anchor), category tree.
E "hr"      : bridge table WITH a measure (assignments.hours), department
              reachable two ways (employee's dept vs project's dept),
              self-reference (manager_id) that must NOT be guessed,
              NULL bonus, hire dates across years.
"""
from __future__ import annotations

import json
import pathlib
import random
import sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"

D_DDL = """
CREATE TABLE categories (category_id INTEGER PRIMARY KEY, category_name TEXT NOT NULL, parent_id INTEGER);
CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL,
  category_id INTEGER REFERENCES categories(category_id), list_price REAL NOT NULL);
CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, customer_name TEXT NOT NULL, segment TEXT, city TEXT);
CREATE TABLE stores (store_id INTEGER PRIMARY KEY, store_name TEXT NOT NULL, region TEXT NOT NULL);
CREATE TABLE orders (order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, ship_date TEXT,
  customer_id INTEGER REFERENCES customers(customer_id), store_id INTEGER NOT NULL REFERENCES stores(store_id),
  shipping_fee REAL NOT NULL);
CREATE TABLE order_lines (line_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
  product_id INTEGER NOT NULL REFERENCES products(product_id), qty INTEGER NOT NULL,
  unit_price REAL NOT NULL, discount REAL);
"""
D_EDGES = {
    ("products", "category_id", "categories", "category_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "store_id", "stores", "store_id"),
    ("order_lines", "order_id", "orders", "order_id"),
    ("order_lines", "product_id", "products", "product_id"),
}
D_METRICS = {"tables": {"order_lines": {"metrics": [
    {"id": "gross_sales", "name": "Gross Sales", "expression": "SUM(qty * unit_price)",
     "synonyms": ["gross revenue"], "unit": "currency"},
    {"id": "net_sales", "name": "Net Sales",
     "expression": "SUM(qty * unit_price * (1 - COALESCE(discount, 0)))",
     "synonyms": ["net revenue"], "unit": "currency"}]}}}


def build_d(path=None):
    path = pathlib.Path(path or DATA / "retail.db"); path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(5150)
    c = sqlite3.connect(str(path)); c.executescript(D_DDL)
    c.executemany("INSERT INTO categories VALUES (?,?,?)", [
        (1, "Home & Garden", None), (2, "Electronics", None), (3, "Kids' Toys", None),
        (4, "Garden Tools", 1), (5, "Kitchenware", 1), (6, "Audio (Hi-Fi)", 2), (7, "Clearance", None)])  # 7 empty
    prods = [(1, "Pruning Shears", 4, 24.5), (2, "Chef Knife 8\"", 5, 89.0), (3, "Bluetooth Speaker", 6, 129.0),
             (4, "Building Blocks Set", 3, 39.99), (5, "Headphones", 6, 199.0), (6, "Watering Can", 4, 15.0),
             (7, "Cast Iron Pan", 5, 54.0), (8, "Robot Kit", 3, 79.0)]
    c.executemany("INSERT INTO products VALUES (?,?,?,?)", prods)
    c.executemany("INSERT INTO customers VALUES (?,?,?,?)", [
        (i, f"Cust {i:03d}", rng.choice(["Retail", "Wholesale", None]), rng.choice(["Austin", "Boston", "Denver", "Reno"]))
        for i in range(1, 61)])
    c.executemany("INSERT INTO stores VALUES (?,?,?)", [
        (1, "Downtown Flagship", "East"), (2, "Mall of the North", "North"),
        (3, "Online Store", "Online"), (4, "Closed Outlet", "East")])             # 4: no orders
    orders, lines, lid = [], [], 1
    for o in range(1, 401):
        m = rng.randint(1, 12)
        od = f"2025-{m:02d}-{rng.randint(1, 27):02d}"
        sd = None if rng.random() < 0.1 else f"2025-{m:02d}-28"
        cust = None if rng.random() < 0.15 else rng.randint(1, 60)
        orders.append((o, od, sd, cust, rng.choice([1, 2, 3]), round(rng.uniform(3, 15), 2)))
        for _ in range(rng.randint(1, 4)):
            p = rng.choice(prods)
            lines.append((lid, o, p[0], rng.randint(1, 5), p[3], None if rng.random() < 0.6 else round(rng.choice([0.05, 0.1, 0.2]), 2)))
            lid += 1
    c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    c.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?,?)", lines)
    c.commit(); c.close()
    (DATA / "retail.metrics.json").write_text(json.dumps(D_METRICS))
    return path


E_DDL = """
CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, dept_name TEXT NOT NULL, cost_center TEXT);
CREATE TABLE employees (emp_id INTEGER PRIMARY KEY, emp_name TEXT NOT NULL,
  dept_id INTEGER REFERENCES departments(dept_id), manager_id INTEGER, hire_date TEXT NOT NULL,
  salary REAL NOT NULL, bonus REAL, status TEXT NOT NULL);
CREATE TABLE projects (project_id INTEGER PRIMARY KEY, project_name TEXT NOT NULL,
  dept_id INTEGER REFERENCES departments(dept_id));
CREATE TABLE assignments (assign_id INTEGER PRIMARY KEY, emp_id INTEGER NOT NULL REFERENCES employees(emp_id),
  project_id INTEGER NOT NULL REFERENCES projects(project_id), week_start TEXT NOT NULL, hours REAL NOT NULL);
"""
E_EDGES = {
    ("employees", "dept_id", "departments", "dept_id"),
    ("projects", "dept_id", "departments", "dept_id"),
    ("assignments", "emp_id", "employees", "emp_id"),
    ("assignments", "project_id", "projects", "project_id"),
}


def build_e(path=None):
    path = pathlib.Path(path or DATA / "hr.db"); path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(8128)
    c = sqlite3.connect(str(path)); c.executescript(E_DDL)
    c.executemany("INSERT INTO departments VALUES (?,?,?)", [
        (1, "Engineering", "CC-100"), (2, "Sales & Marketing", "CC-200"), (3, "Human Resources", "CC-300"),
        (4, "Legal", "CC-400"), (5, "R&D Lab (Intl.)", "CC-500")])                  # 5: no employees
    c.executemany("INSERT INTO projects VALUES (?,?,?)", [
        (1, "Apollo", 1), (2, "Beacon", 1), (3, "Campaign Q3", 2), (4, "Compliance Audit", 4),
        (5, "Skunkworks", 5), (6, "Onboarding Revamp", 3)])
    emps = []
    for i in range(1, 61):
        dept = None if i in (59, 60) else rng.choice([1, 1, 2, 3, 4])              # 5 never used
        mgr = None if i <= 5 else rng.randint(1, 5)
        hire = f"{rng.choice([2021, 2022, 2023, 2024])}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        emps.append((i, "Dana Reyes" if i == 1 else f"Employee {i:02d}", dept, mgr, hire,
                     round(rng.uniform(45000, 160000), 2),
                     None if rng.random() < 0.4 else round(rng.uniform(1000, 15000), 2),
                     rng.choice(["Active", "Active", "Active", "On Leave", "Terminated"])))
    c.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?)", emps)
    asg, aid = [], 1
    for _ in range(700):
        e = rng.randint(1, 60); p = rng.randint(1, 6)
        asg.append((aid, e, p, f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 27):02d}", round(rng.uniform(2, 40), 1)))
        aid += 1
    c.executemany("INSERT INTO assignments VALUES (?,?,?,?,?)", asg)
    c.commit(); c.close()
    return path


if __name__ == "__main__":
    print(build_d()); print(build_e())
