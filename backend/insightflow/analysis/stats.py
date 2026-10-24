"""Pure-Python statistical post-aggregations.

SQLite 3.45 has no native median or percentile aggregate. Rather than
refuse these operations, we fetch the raw rows via SQL (which SQLite
CAN do fast) and compute the statistic in Python using the stdlib
`statistics` module. The pipeline marks the measure as `aggregation=
"post_agg_median"` / `"post_agg_percentile"` so a dedicated executor
knows to retrieve a column and reduce it in Python.

This keeps:
  * the semantic contract (user asked for median → user gets median)
  * SQL safety (query is `SELECT col FROM orders [WHERE …]` with no
    user-authored expressions)
  * database portability (works on any SQL engine)

Trade-off: the full column is pulled into memory. For the 2 000-row
demo DB this is trivial. For >1 M rows a server-side aggregate (via a
UDF or an engine upgrade) would be preferable; the capability gate
should probably keep refusing on datasets above a configurable row
threshold.
"""
from __future__ import annotations

import math
import statistics
from typing import List, Optional, Sequence


def median(values: Sequence[float]) -> Optional[float]:
    vs = [float(v) for v in values if v is not None]
    if not vs:
        return None
    return statistics.median(vs)


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    """Linear-interpolation percentile. `p` is in [0, 100]."""
    vs = sorted(float(v) for v in values if v is not None)
    if not vs:
        return None
    if not 0.0 <= p <= 100.0:
        raise ValueError(f"percentile p must be in [0, 100]: got {p}")
    if len(vs) == 1:
        return vs[0]
    k = (p / 100.0) * (len(vs) - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return vs[lo]
    frac = k - lo
    return vs[lo] + (vs[hi] - vs[lo]) * frac


def stdev(values: Sequence[float]) -> Optional[float]:
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2:
        return None
    return statistics.stdev(vs)


def variance(values: Sequence[float]) -> Optional[float]:
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2:
        return None
    return statistics.variance(vs)
