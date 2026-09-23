"""Upload endpoint: replace / append the demo `orders` table from a CSV.

Design goals
------------
- Keep the shipped KPI semantic layer intact — the columns InsightFlow's
  KPIs read (`revenue`, `cost`, `discount`, `quantity`, `order_date`,
  `region_id`, `product_id`, `customer_id`) are what we insert into.
- Let a user upload a CSV with human-readable dimension columns
  (`region`, `category`, `product`, `customer`, `segment`) and upsert
  them into the dim tables so the dashboard breakdowns still work.
- Never let a CSV be a SQL-injection vector: values are always bound
  parameters; the CSV is never concatenated into SQL text.
- After a successful upload trigger a `mark_changed()` so every open
  dashboard sees the new data over WebSocket without a refresh.

Accepted CSV columns (case-insensitive; header row required)
-----------------------------------------------------------
Required:
    revenue      float
Optional (with defaults):
    order_date   YYYY-MM-DD, MM/DD/YYYY, or DD-MM-YYYY   (default: today)
    quantity     int                                    (default: 1)
    cost         float                                  (default: 0.0)
    discount     float                                  (default: 0.0)
Dimension names (strings — upserted into dim tables):
    region, category, product, customer, segment
Aliases accepted:
    date              → order_date
    product_name      → product
    customer_name     → customer
    sales, amount     → revenue

Limits
------
- 5 MB file cap.
- 50,000 row cap.
- Row is skipped (and its 1-based index recorded) if revenue is missing
  or unparseable.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import text

from insightflow.execution.executor import get_engine, reset_engine
from insightflow.knowledge.schema_agent import refresh_schema

from . import realtime


router = APIRouter()

MAX_FILE_BYTES = 5 * 1024 * 1024        # 5 MB
MAX_ROWS       = 50_000

# --- column aliasing ---
ALIAS = {
    "date": "order_date",
    "orderdate": "order_date",
    "sales": "revenue",
    "amount": "revenue",
    "gross_revenue": "revenue",
    "product_name": "product",
    "productname": "product",
    "customer_name": "customer",
    "customername": "customer",
    "categoryname": "category",
    "regionname": "region",
    "qty": "quantity",
    "units": "quantity",
}

DIM_COLS = ("region", "category", "product", "customer", "segment")


class UploadResponse(BaseModel):
    ok: bool
    rows_inserted: int
    rows_skipped: int
    skipped_row_indices: list[int]
    columns_recognized: list[str]
    dims_upserted: dict[str, int]     # e.g. {"regions": 5, "products": 12, ...}
    mode: str                          # "replace" | "append"
    detail: str = ""


# ---------------------------------------------------------------------------

def _norm_header(h: str) -> str:
    key = h.strip().lower().replace(" ", "_")
    return ALIAS.get(key, key)


def _parse_date(v: str) -> Optional[str]:
    v = (v or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    # last resort — pandas-style ISO with time
    try:
        return datetime.fromisoformat(v).date().isoformat()
    except ValueError:
        return None


def _parse_float(v: str) -> Optional[float]:
    v = (v or "").strip().replace(",", "").replace("$", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_int(v: str) -> Optional[int]:
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


# ---------------------------------------------------------------------------

def _upsert_dim(conn, table: str, id_col: str, name_col: str,
                names: set[str], cache: dict[str, int],
                extra_cols: dict[str, str] | None = None) -> int:
    """Insert any missing rows; return the number of new rows inserted."""
    if not names:
        return 0
    # Load existing
    existing = {r[0]: r[1] for r in conn.execute(text(
        f"SELECT {name_col}, {id_col} FROM {table}"
    )).fetchall()}
    cache.update(existing)
    new = names - set(existing.keys())
    if not new:
        return 0
    # Figure out next id
    max_id = conn.execute(text(f"SELECT COALESCE(MAX({id_col}),0) FROM {table}")).scalar()
    inserted = 0
    for name in sorted(new):
        max_id = int(max_id) + 1
        cols = [id_col, name_col]
        vals = {"id": max_id, "name": name}
        placeholders = [":id", ":name"]
        if extra_cols:
            for c, v in extra_cols.items():
                cols.append(c)
                vals[c] = v
                placeholders.append(f":{c}")
        conn.execute(text(
            f"INSERT INTO {table}({', '.join(cols)}) "
            f"VALUES ({', '.join(placeholders)})"
        ), vals)
        cache[name] = max_id
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------

@router.post("/api/upload/orders", response_model=UploadResponse)
async def upload_orders(
    file: UploadFile = File(..., description="CSV file to load into `orders`."),
    mode: str = Query("replace", pattern="^(replace|append)$",
                      description="`replace` clears orders first; `append` keeps existing rows."),
):
    if not file.filename or not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    body = await file.read()
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (>{MAX_FILE_BYTES} bytes)")
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        text_body = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text_body = body.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="File is not UTF-8 or Latin-1 text")

    reader = csv.reader(io.StringIO(text_body))
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    headers = [_norm_header(h) for h in header]
    if "revenue" not in headers:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain a `revenue` column (aliases: sales, amount)"
        )

    col_idx = {name: i for i, name in enumerate(headers)}

    # Row parse
    parsed_rows: list[dict] = []
    skipped: list[int] = []
    seen_dims: dict[str, set[str]] = {c: set() for c in DIM_COLS}

    row_num = 1  # header is row 1
    for row in reader:
        row_num += 1
        if row_num - 1 > MAX_ROWS + 1:   # +1 because header
            skipped.append(row_num)
            continue
        if not any((cell or "").strip() for cell in row):
            continue  # blank line

        def cell(name: str) -> str:
            i = col_idx.get(name)
            return row[i] if i is not None and i < len(row) else ""

        rev = _parse_float(cell("revenue"))
        if rev is None:
            skipped.append(row_num)
            continue

        d = _parse_date(cell("order_date")) or date.today().isoformat()
        qty = _parse_int(cell("quantity"))
        if qty is None:
            qty = 1
        cost = _parse_float(cell("cost"))
        if cost is None:
            cost = 0.0
        disc = _parse_float(cell("discount"))
        if disc is None:
            disc = 0.0

        item = {
            "order_date": d, "quantity": max(0, qty),
            "revenue": max(0.0, rev), "cost": max(0.0, cost),
            "discount": max(0.0, disc),
        }
        for c in DIM_COLS:
            v = (cell(c) or "").strip()
            if v:
                item[c] = v
                seen_dims[c].add(v)
        parsed_rows.append(item)

    if not parsed_rows:
        raise HTTPException(status_code=400, detail="No valid rows parsed")

    engine = get_engine()
    dims_inserted: dict[str, int] = {}

    with engine.begin() as conn:
        # Upsert dim rows
        region_cache: dict[str, int] = {}
        product_cache: dict[str, int] = {}   # keyed by product NAME
        customer_cache: dict[str, int] = {}
        # regions
        dims_inserted["regions"] = _upsert_dim(
            conn, "regions", "region_id", "region_name",
            seen_dims["region"], region_cache,
        )
        # For products we need a category. If a row provides a category,
        # ensure the (product, category) pair exists; if not, default
        # category to "Uploaded".
        # We look up products by name, but store their category.
        # First, collect (name -> category) pairs from parsed rows.
        product_categories: dict[str, str] = {}
        for item in parsed_rows:
            if "product" in item:
                product_categories[item["product"]] = item.get("category", "Uploaded")
        # Load existing product->id map
        for pid, pname in conn.execute(text("SELECT product_id, product_name FROM products")).fetchall():
            product_cache[pname] = pid
        new_product_names = set(product_categories.keys()) - set(product_cache.keys())
        new_products = 0
        if new_product_names:
            max_pid = conn.execute(text("SELECT COALESCE(MAX(product_id),0) FROM products")).scalar()
            for name in sorted(new_product_names):
                max_pid = int(max_pid) + 1
                conn.execute(text(
                    "INSERT INTO products(product_id, product_name, category) "
                    "VALUES (:pid, :pname, :cat)"
                ), {"pid": max_pid, "pname": name,
                    "cat": product_categories.get(name, "Uploaded")})
                product_cache[name] = max_pid
                new_products += 1
        dims_inserted["products"] = new_products

        # customers — need region_id and segment. Default region_id = 1
        # if no region is provided; default segment = "Uploaded".
        customer_names = seen_dims["customer"]
        # Load existing customers
        for cid, cname in conn.execute(text("SELECT customer_id, customer_name FROM customers")).fetchall():
            customer_cache[cname] = cid
        new_customer_names = customer_names - set(customer_cache.keys())
        new_customers = 0
        if new_customer_names:
            # figure a sensible default region_id
            default_region = conn.execute(text(
                "SELECT region_id FROM regions ORDER BY region_id LIMIT 1"
            )).scalar() or 1
            max_cid = conn.execute(text("SELECT COALESCE(MAX(customer_id),0) FROM customers")).scalar()
            for name in sorted(new_customer_names):
                max_cid = int(max_cid) + 1
                conn.execute(text(
                    "INSERT INTO customers(customer_id, customer_name, region_id, segment) "
                    "VALUES (:cid, :cname, :rid, :seg)"
                ), {"cid": max_cid, "cname": name,
                    "rid": default_region, "seg": "Uploaded"})
                customer_cache[name] = max_cid
                new_customers += 1
        dims_inserted["customers"] = new_customers

        # Replace or append orders
        if mode == "replace":
            conn.execute(text("DELETE FROM orders"))

        # Establish default FK targets for rows that don't name a dim
        default_region_id = conn.execute(text(
            "SELECT region_id FROM regions ORDER BY region_id LIMIT 1"
        )).scalar() or 1
        default_product_id = conn.execute(text(
            "SELECT product_id FROM products ORDER BY product_id LIMIT 1"
        )).scalar() or 1
        default_customer_id = conn.execute(text(
            "SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1"
        )).scalar() or 1

        # Fresh order_id sequence
        max_oid = conn.execute(text("SELECT COALESCE(MAX(order_id),0) FROM orders")).scalar()

        rows_inserted = 0
        for item in parsed_rows:
            max_oid = int(max_oid) + 1
            region_id = (
                region_cache.get(item.get("region", ""), default_region_id)
                if "region" in item else default_region_id
            )
            product_id = (
                product_cache.get(item.get("product", ""), default_product_id)
                if "product" in item else default_product_id
            )
            customer_id = (
                customer_cache.get(item.get("customer", ""), default_customer_id)
                if "customer" in item else default_customer_id
            )
            conn.execute(text(
                "INSERT INTO orders(order_id, customer_id, product_id, region_id, "
                "order_date, quantity, revenue, cost, discount) "
                "VALUES (:oid, :cid, :pid, :rid, :d, :q, :rev, :cost, :disc)"
            ), {"oid": max_oid, "cid": customer_id, "pid": product_id,
                "rid": region_id, "d": item["order_date"], "q": item["quantity"],
                "rev": item["revenue"], "cost": item["cost"], "disc": item["discount"]})
            rows_inserted += 1

    # Post-upload housekeeping
    reset_engine()
    refresh_schema()
    realtime.state.mark_changed()   # triggers a dashboard broadcast

    return UploadResponse(
        ok=True,
        rows_inserted=rows_inserted,
        rows_skipped=len(skipped),
        skipped_row_indices=skipped[:50],
        columns_recognized=[h for h in headers if h],
        dims_upserted=dims_inserted,
        mode=mode,
        detail=(f"Loaded {rows_inserted} row(s) into orders "
                f"({mode}); upserted {sum(dims_inserted.values())} dim rows."),
    )


@router.get("/api/upload/sample.csv")
def sample_csv():
    """A tiny template a user can download and edit."""
    from fastapi.responses import PlainTextResponse
    csv_body = (
        "order_date,region,category,product,customer,segment,quantity,revenue,cost,discount\n"
        "2026-01-15,North,Electronics,Laptop,Acme Ltd,Enterprise,2,1800.00,1260.00,72.00\n"
        "2026-01-16,South,Furniture,Desk,Zeta Co,SMB,1,450.00,290.00,20.00\n"
        "2026-02-01,East,Software,OS License,Ravi Kumar,Consumer,5,600.00,210.00,15.00\n"
    )
    return PlainTextResponse(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="insightflow_sample.csv"'},
    )
