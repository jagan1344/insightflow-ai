-- InsightFlow demo sales star schema
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS regions;

CREATE TABLE regions (
    region_id   INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region_id     INTEGER NOT NULL REFERENCES regions(region_id),
    segment       TEXT NOT NULL
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    region_id   INTEGER NOT NULL REFERENCES regions(region_id),
    order_date  TEXT NOT NULL,   -- ISO date YYYY-MM-DD
    quantity    INTEGER NOT NULL,
    revenue     REAL NOT NULL,
    cost        REAL NOT NULL,
    discount    REAL NOT NULL DEFAULT 0
);

CREATE INDEX idx_orders_date     ON orders(order_date);
CREATE INDEX idx_orders_region   ON orders(region_id);
CREATE INDEX idx_orders_product  ON orders(product_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);
