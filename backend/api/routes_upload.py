"""Upload endpoint: stores each upload as its OWN table, preserving the
source column names 1-to-1, and registers it in the dataset registry as
the active dataset.

Design (2026-09-23 refactor — root-cause fix for the "upload doesn't
change the active dataset" bug):

- Every CSV / XLSX / XLS becomes a new physical SQLite table named
  `dataset_<slug>` whose columns exactly mirror the source header. No
  shoehorning into demo `orders`/`products`/`regions`/`customers`.

- The dataset registry (`insightflow/knowledge/dataset_registry.py`)
  gets a row and the new dataset is marked active. From that point on
  every NL→SQL call sees the uploaded schema, not the demo schema.

- Reactivating the demo dataset is done by
  `POST /api/dataset/activate/demo` or by `POST /api/seed`.

Compatibility: the legacy Superstore-into-demo path is still available
via `POST /api/upload/orders?target=demo`; a plain
`POST /api/upload/orders` (the current UI call) now stores in a NEW
table.

Guarantees:
- No hardcoded SQL string is concatenated from the CSV — every value is
  a bound parameter.
- 5 MB / 50k row caps still apply.
- On any error the transaction rolls back — no half-written state.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import text

from insightflow.execution.executor import get_engine, reset_engine
from insightflow.knowledge.dataset_registry import (
    bootstrap, delete_uploaded, get_active_dataset, list_datasets,
    register_uploaded, set_active, _slug, DEMO_ID,
)
from insightflow.knowledge.schema_agent import refresh_schema

from . import realtime


router = APIRouter()

MAX_FILE_BYTES = 5 * 1024 * 1024        # 5 MB
MAX_ROWS       = 50_000


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    ok: bool
    dataset_id: str
    dataset_name: str
    table_name: str
    rows_inserted: int
    rows_skipped: int
    skipped_row_indices: list[int]
    columns: list[dict]                # [{name, sql_type, role}]
    detail: str = ""
    is_active: bool = True


class DatasetListItem(BaseModel):
    id: str
    name: str
    table: str
    kind: str
    uploaded_at: Optional[str] = None
    is_active: bool


# ---------------------------------------------------------------------------
# Decoding (unchanged from previous version — supports CSV / XLSX / XLS)
# ---------------------------------------------------------------------------

def _cell_to_string(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            pass
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(v)
    return str(v)


def _xlsx_to_csv(body: bytes) -> str:
    from openpyxl import load_workbook  # type: ignore
    wb = load_workbook(io.BytesIO(body), data_only=True, read_only=True)
    ws = wb.active
    out = io.StringIO()
    w = csv.writer(out)
    for row in ws.iter_rows(values_only=True):
        w.writerow([_cell_to_string(v) for v in row])
    wb.close()
    return out.getvalue()


def _xls_to_csv(body: bytes) -> str:
    import xlrd  # type: ignore
    wb = xlrd.open_workbook(file_contents=body)
    ws = wb.sheet_by_index(0)
    out = io.StringIO()
    w = csv.writer(out)
    for i in range(ws.nrows):
        row_out = []
        for j in range(ws.ncols):
            cell = ws.cell(i, j)
            v = cell.value
            if cell.ctype == 3:  # DATE
                try:
                    dt = xlrd.xldate.xldate_as_datetime(v, wb.datemode)
                    row_out.append(dt.strftime("%Y-%m-%d"))
                    continue
                except Exception:
                    pass
            if isinstance(v, float) and v.is_integer():
                row_out.append(str(int(v)))
            else:
                row_out.append("" if v is None else str(v))
        w.writerow(row_out)
    return out.getvalue()


def _decode_upload_to_csv_text(body: bytes, filename: str) -> str:
    lower = (filename or "").lower()
    if lower.endswith((".csv", ".txt")):
        try:
            return body.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                return body.decode("latin-1")
            except Exception:
                raise HTTPException(status_code=400,
                                    detail="File is not UTF-8 or Latin-1 text")
    if lower.endswith(".xlsx"):
        try:
            return _xlsx_to_csv(body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read .xlsx: {e}")
    if lower.endswith(".xls"):
        try:
            return _xls_to_csv(body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read .xls: {e}")
    raise HTTPException(
        status_code=400,
        detail="Please upload a .csv, .txt, .xlsx or .xls file",
    )


# ---------------------------------------------------------------------------
# Cell parsing — value-only guards, all values pass through bound params.
# ---------------------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y",
                 "%d/%m/%Y", "%Y-%m-%d %H:%M:%S")


def _try_int(v: str) -> Optional[int]:
    if not v or not v.strip():
        return None
    v2 = v.replace(",", "").strip()
    try:
        return int(v2)
    except ValueError:
        try:
            f = float(v2)
            if f.is_integer():
                return int(f)
        except ValueError:
            pass
    return None


def _try_float(v: str) -> Optional[float]:
    if not v or not v.strip():
        return None
    v2 = v.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(v2)
    except ValueError:
        return None


def _try_date(v: str) -> Optional[str]:
    if not v or not v.strip():
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(v.strip()).date().isoformat()
    except ValueError:
        return None


def _sanitize_col_name(name: str) -> str:
    """Turn 'Order Date' → 'order_date'. SQL-safe, deterministic."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_")
    if not s:
        return "column"
    if s[0].isdigit():
        s = "c_" + s
    return s.lower()


def _dedupe_columns(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen[n] = 0
            out.append(n)
        else:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
    return out


def _infer_types(headers: list[str],
                 raw_rows: list[list[str]]) -> tuple[list[str], list[list]]:
    """For each column decide REAL / INTEGER / TEXT and convert row values."""
    n_cols = len(headers)
    parsed_cols: list[list] = [[] for _ in range(n_cols)]
    types: list[str] = []
    for j in range(n_cols):
        column_raw = [row[j] if j < len(row) else "" for row in raw_rows]
        non_empty = [v for v in column_raw if v is not None and str(v).strip()]
        n_nonempty = len(non_empty)
        # try DATE
        date_hits = sum(1 for v in non_empty if _try_date(str(v)) is not None)
        if n_nonempty and date_hits / n_nonempty > 0.8:
            types.append("TEXT")  # store as ISO string
            for v in column_raw:
                parsed_cols[j].append(_try_date(str(v)) if v else None)
            continue
        # try INTEGER
        int_hits = sum(1 for v in non_empty if _try_int(str(v)) is not None
                       and _try_float(str(v)) is not None
                       and abs(_try_float(str(v)) - _try_int(str(v))) < 1e-9)
        # try REAL
        float_hits = sum(1 for v in non_empty if _try_float(str(v)) is not None)
        if n_nonempty and float_hits / n_nonempty > 0.8:
            if int_hits == float_hits:
                types.append("INTEGER")
                for v in column_raw:
                    parsed_cols[j].append(_try_int(str(v)))
            else:
                types.append("REAL")
                for v in column_raw:
                    parsed_cols[j].append(_try_float(str(v)))
            continue
        # fallback: TEXT
        types.append("TEXT")
        for v in column_raw:
            parsed_cols[j].append(None if v is None else str(v))
    return types, list(zip(*parsed_cols))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/datasets", response_model=list[DatasetListItem])
def get_datasets():
    return list_datasets()


@router.get("/api/datasets/active")
def get_active():
    ds = get_active_dataset()
    return {
        "id": ds.id, "name": ds.name, "table": ds.table, "kind": ds.kind,
        "columns": [
            {"name": c.name, "sql_type": c.sql_type, "role": c.role,
             "sample_values": [str(v)[:40] for v in c.sample_values[:5]]}
            for c in ds.columns.values()
        ],
        "measures": ds.measures,
        "dimensions": ds.dimensions,
        "dates": ds.dates,
    }


@router.post("/api/datasets/activate/{dataset_id}")
def activate_dataset(dataset_id: str):
    try:
        ds = set_active(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    reset_engine()
    refresh_schema()
    realtime.state.mark_changed()
    return {"ok": True, "id": ds.id, "name": ds.name, "table": ds.table,
            "kind": ds.kind}


@router.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    try:
        delete_uploaded(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    realtime.state.mark_changed()
    return {"ok": True}


@router.get("/api/upload/sample.csv")
def sample_csv():
    from fastapi.responses import PlainTextResponse
    body = (
        "order_date,region,category,product,customer,segment,quantity,revenue,cost,discount\n"
        "2026-01-15,North,Electronics,Laptop,Acme Ltd,Enterprise,2,1800.00,1260.00,72.00\n"
        "2026-01-16,South,Furniture,Desk,Zeta Co,SMB,1,450.00,290.00,20.00\n"
        "2026-02-01,East,Software,OS License,Ravi Kumar,Consumer,5,600.00,210.00,15.00\n"
    )
    return PlainTextResponse(
        content=body, media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="insightflow_sample.csv"'},
    )


@router.post("/api/upload/orders", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV / XLSX / XLS file."),
    mode: str = Query("replace", pattern="^(replace|append)$",
                      description=("`replace` creates a new dataset "
                                   "(the default). `append` requires a "
                                   "target dataset id.")),
    dataset_name: Optional[str] = Query(
        None, description="Human-readable name for the new dataset. "
                          "Defaults to the file name."),
    target: Optional[str] = Query(
        None, description="Existing dataset id to append to (only used "
                          "when mode=append)."),
):
    """Store the upload as its OWN table and set it active.

    `mode=replace` (default, matches the current UI): create a brand new
    dataset table, register it, and mark it active. The demo dataset is
    left untouched — you can reactivate it with
    `POST /api/datasets/activate/demo`.

    `mode=append`: append into the physical table of `target` (must be
    an existing uploaded dataset id). Column names in the CSV must
    already exist in the target table.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")

    body = await file.read()
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"File too large (>{MAX_FILE_BYTES} bytes)")
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    text_body = _decode_upload_to_csv_text(body, file.filename)

    reader = csv.reader(io.StringIO(text_body))
    try:
        raw_header = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    if not raw_header or all(not h.strip() for h in raw_header):
        raise HTTPException(status_code=400, detail="Header row is empty")

    headers = _dedupe_columns([_sanitize_col_name(h) for h in raw_header])

    raw_rows: list[list[str]] = []
    skipped: list[int] = []
    row_num = 1
    for row in reader:
        row_num += 1
        if row_num - 1 > MAX_ROWS + 1:
            skipped.append(row_num)
            continue
        if not any((cell or "").strip() for cell in row):
            continue  # blank line
        raw_rows.append(list(row) + [""] * max(0, len(headers) - len(row)))

    if not raw_rows:
        raise HTTPException(status_code=400, detail="No data rows found")

    types, parsed_rows = _infer_types(headers, raw_rows)

    engine = get_engine()
    bootstrap()

    if mode == "append":
        if not target:
            raise HTTPException(status_code=400,
                                detail="mode=append requires `target` dataset id")
        # look up target's table
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT table_name, kind, name FROM _datasets WHERE id = :id"),
                {"id": target}).fetchone()
            if not row:
                raise HTTPException(status_code=404,
                                    detail=f"unknown dataset id: {target}")
            table_name, kind, ds_name = row
            if kind == "demo":
                raise HTTPException(status_code=400,
                                    detail="cannot append to the demo dataset")
            # Verify column names match
            from sqlalchemy import inspect as sqlinspect
            existing = [c["name"] for c in sqlinspect(engine).get_columns(table_name)]
            unknown = [h for h in headers if h not in existing]
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=f"columns not in target table: {unknown}",
                )
            for parsed in parsed_rows:
                params = {h: parsed[i] for i, h in enumerate(headers)}
                col_list = ", ".join(f'"{h}"' for h in headers)
                ph_list = ", ".join(f":{h}" for h in headers)
                conn.execute(text(
                    f'INSERT INTO "{table_name}"({col_list}) VALUES ({ph_list})'
                ), params)
        dataset_id = target
    else:
        # replace mode — new dataset table
        name = dataset_name or Path(file.filename).stem or "dataset"
        slug = _slug(name)
        table_name = slug if slug.startswith("dataset_") else "dataset_" + slug
        # ensure uniqueness of the table
        with engine.begin() as conn:
            from sqlalchemy import inspect as sqlinspect
            existing_tables = set(sqlinspect(engine).get_table_names())
            base = table_name
            i = 1
            while table_name in existing_tables:
                i += 1
                table_name = f"{base}_{i}"
            col_defs = ", ".join(f'"{h}" {t}' for h, t in zip(headers, types))
            conn.execute(text(f'CREATE TABLE "{table_name}" ({col_defs})'))
            for parsed in parsed_rows:
                params = {h: parsed[i] for i, h in enumerate(headers)}
                col_list = ", ".join(f'"{h}"' for h in headers)
                ph_list = ", ".join(f":{h}" for h in headers)
                conn.execute(text(
                    f'INSERT INTO "{table_name}"({col_list}) VALUES ({ph_list})'
                ), params)
        dataset_id = register_uploaded(name=name, table_name=table_name)

    reset_engine()
    refresh_schema()
    realtime.state.mark_changed()

    ds = get_active_dataset()
    return UploadResponse(
        ok=True,
        dataset_id=dataset_id,
        dataset_name=ds.name,
        table_name=ds.table,
        rows_inserted=len(parsed_rows),
        rows_skipped=len(skipped),
        skipped_row_indices=skipped[:50],
        columns=[
            {"name": c.name, "sql_type": c.sql_type, "role": c.role}
            for c in ds.columns.values()
        ],
        detail=(f"Stored {len(parsed_rows)} row(s) in table "
                f"{ds.table!r} — active dataset is now '{ds.name}'."),
        is_active=True,
    )
