"""Common business abbreviations -> canonical word. Language knowledge, not
schema knowledge: it only lets "transaction type" find `txn_type`."""
import re

ABBREV = {
    "txn": "transaction", "trx": "transaction", "tran": "transaction", "qty": "quantity", "amt": "amount",
    "cust": "customer", "acct": "account", "acc": "account", "dept": "department", "emp": "employee",
    "prod": "product", "prd": "product", "addr": "address", "num": "number", "nbr": "number", "pct": "percent",
    "dt": "date", "desc": "description", "cat": "category", "mgr": "manager", "org": "organization",
    "reg": "region", "loc": "location", "svc": "service", "inv": "invoice", "ord": "order", "prc": "price",
    "cd": "code", "stat": "status", "sts": "status", "tot": "total", "avg": "average", "bal": "balance",
    "pmt": "payment", "wo": "workorder", "po": "purchaseorder", "sku": "sku", "yr": "year", "mth": "month",
    "wk": "week", "cnt": "count", "ref": "reference", "src": "source", "dst": "destination", "dest": "destination",
    "ctry": "country", "st": "state", "veh": "vehicle", "temp": "temperature", "pax": "passenger", "apt": "airport", "carr": "carrier", "flt": "flight", "sup": "supplier", "vend": "vendor",
}


def canon(token: str) -> str:
    t = token.lower()
    t = ABBREV.get(t, t)
    # crude singular so "transactions" ~ "transaction"
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t


def canon_tokens(text: str) -> list:
    return [canon(t) for t in re.split(r"[^a-zA-Z0-9]+", text) if t]
