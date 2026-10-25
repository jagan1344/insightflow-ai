"""Cost-aware execution guard (SQLite).

Static pre-flight (EXPLAIN QUERY PLAN + table sizes) and a runtime budget:

  * cartesian / unconstrained joins are blocked
  * an estimated scanned-row count above `max_scan_cost` is blocked
  * full scans of large tables inside a join loop are flagged (diagnostic)
  * runtime: a progress handler aborts the statement after `timeout_s`

Nothing here rewrites SQL: an optimisation is only acceptable when result
equivalence is proven, and no such rewrite is performed.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import List

DEFAULT_MAX_SCAN_COST = 20_000_000      # estimated row visits
DEFAULT_TIMEOUT_S = 10.0


@dataclass
class CostReport:
    level: str = "ok"                   # ok | warn | block
    est_rows: int = 0
    reasons: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.level == "block"


def _cartesian(sql: str) -> bool:
    s = re.sub(r"\s+", " ", sql)
    if re.search(r"\bCROSS JOIN\b", s, re.I):
        return True
    for m in re.finditer(r"\b(?:LEFT |INNER |RIGHT |FULL )?JOIN\b", s, re.I):
        tail = s[m.end():]
        nxt = re.search(r"\b(JOIN|WHERE|GROUP BY|ORDER BY|LIMIT|HAVING|UNION)\b", tail, re.I)
        seg = tail[: nxt.start()] if nxt else tail
        if not re.search(r"\b(ON|USING)\b", seg, re.I):
            return True
    # "FROM a, b" comma joins with no WHERE linking them
    if re.search(r"\bFROM\s+[\w\"`.]+(?:\s+(?:AS\s+)?\w+)?\s*,\s*[\w\"`]", s, re.I) \
            and not re.search(r"\bWHERE\b", s, re.I):
        return True
    return False


def analyze(db_path: str, sql: str,
            max_scan_cost: int = DEFAULT_MAX_SCAN_COST) -> CostReport:
    rep = CostReport()
    if _cartesian(sql):
        rep.level = "block"
        rep.reasons.append("join without a join condition (cartesian product)")
        return rep
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return rep
    try:
        plan = con.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        alias_of = {}
        for m in re.finditer(r'(?:FROM|JOIN|,)\s+"?(\w+)"?(?:\s+(?:AS\s+)?"?(\w+)"?)?', sql, re.I):
            tbl, al = m.group(1), m.group(2)
            if al and al.upper() not in ("ON", "WHERE", "JOIN", "LEFT", "INNER", "CROSS", "GROUP", "ORDER", "LIMIT", "USING", "UNION", "HAVING"):
                alias_of[al] = tbl
        sizes = {}
        scans = []
        for row in plan:
            detail = str(row[-1])
            m = re.match(r"SCAN\s+(?:TABLE\s+)?(\"?[\w]+\"?)", detail, re.I)
            if m and "USING" not in detail.upper().split("SCAN", 1)[-1][:60]:
                t = m.group(1).strip('"')
                t = alias_of.get(t, t)
                if t not in sizes:
                    try:
                        sizes[t] = con.execute(
                            f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    except sqlite3.Error:
                        sizes[t] = 0
                scans.append((t, sizes[t]))
        est = 1
        for _t, n in scans:
            est *= max(n, 1)
        rep.est_rows = est if scans else 0
        if rep.est_rows > max_scan_cost:
            rep.level = "block"
            rep.reasons.append(
                f"estimated {rep.est_rows:,} row visits exceeds budget "
                f"{max_scan_cost:,} ({', '.join(f'{t}={n}' for t, n in scans)})")
        elif len(scans) > 1 and rep.est_rows > max_scan_cost // 20:
            rep.level = "warn"
            rep.reasons.append("nested full scans of several tables")
    except sqlite3.Error:
        pass            # unparsable plan: execution layer reports the error
    finally:
        con.close()
    return rep


def arm_timeout(raw_conn, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
    """Abort the running statement after `timeout_s` (sqlite3 connection)."""
    deadline = time.monotonic() + timeout_s
    raw_conn.set_progress_handler(
        lambda: 1 if time.monotonic() > deadline else 0, 20000)
