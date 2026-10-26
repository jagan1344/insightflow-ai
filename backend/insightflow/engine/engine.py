"""Entry point: question -> grounded typed Query -> verification -> parameterised SQL -> read-only execution,
with an evidence chain at every step."""
from __future__ import annotations

import itertools
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import lexicon as L
from . import schema_model as S
from .compiler import Compiler, CompileError, inline
from .grounding import Grounder
from .ir import Query
from .verify import verify

_LEX: Dict[int, L.Lexicon] = {}


@dataclass
class EngineResult:
    status: str                      # answer | clarify | unsupported | error
    question: str
    query: Optional[Query] = None
    sql: str = ""
    params: List[object] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    rows: List[tuple] = field(default_factory=list)
    message: str = ""
    violations: List[str] = field(default_factory=list)
    reliability: Dict[str, object] = field(default_factory=dict)
    ms: float = 0.0

    @property
    def display_sql(self) -> str:
        return inline(self.sql, self.params) if self.sql else ""

    def trace(self) -> dict:
        q = self.query
        return dict(status=self.status, message=self.message, sql=self.display_sql, violations=self.violations,
                    evidence=[dict(span=e.span, grounded_to=e.grounded_to, reason=e.reason) for e in (q.evidence if q else [])],
                    assumptions=q.assumptions if q else [], ambiguities=q.ambiguities if q else [],
                    unresolved=q.unresolved if q else [], unsupported=q.unsupported if q else [],
                    reliability=self.reliability)


def _lexicon(m: S.SchemaModel) -> L.Lexicon:
    if id(m) not in _LEX:
        _LEX[id(m)] = L.build(m)
    return _LEX[id(m)]


# ambiguities that are not a choice between enumerable readings (they always need the user)
_UNSTRUCTURED = re.compile(r"time series or the stored value|does not say which value of|operand of the expression|"
                           r" describes |'how many' with the money|several periods are named")
MAX_READINGS = 8


def _execute(db_path: str, sql: str, params, timeout_s: float, max_rows: int):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    deadline = time.perf_counter() + timeout_s
    con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10000)
    try:
        cur = con.execute(sql, params)
        return [d[0] for d in cur.description], [tuple(x) for x in cur.fetchmany(max_rows + 1)]
    finally:
        con.close()


def _same(a, b) -> bool:
    def norm(rows):
        return sorted((tuple(round(v, 9) if isinstance(v, float) else v for v in r) for r in rows), key=repr)
    return norm(a) == norm(b)


def _readings(question, m, q, db_path, timeout_s, max_rows):
    """Every combination of the structured choices, each grounded, verified and executed.
    Returns [(label, query, sql, params, columns, rows)] or None when some reading cannot be evaluated."""
    keys = [k for k, _ in q.choices]
    combos = list(itertools.product(*[range(len(c)) for _, c in q.choices]))
    if not combos or len(combos) > MAX_READINGS:
        return None
    out = []
    for combo in combos:
        g = Grounder(m, _lexicon(m), prefer=dict(zip(keys, combo))).ground(question)
        q2 = g.query
        if q2.unsupported or q2.ambiguities or q2.unresolved or verify(q2, m):
            continue                                  # not a consistent reading of the question
        sql, params = Compiler(m).compile(q2)
        cols, rows = _execute(db_path, sql, params, timeout_s, max_rows)
        label = ", ".join(f"{c[i]}" for (_k, c), i in zip(q.choices, combo))
        out.append((label, q2, sql, params, cols, rows))
    return out, len(combos)


def answer(question: str, db_path: str, anchor: str, timeout_s: float = 10.0, max_rows: int = 10000) -> EngineResult:
    t0 = time.perf_counter()
    r = EngineResult("error", question)
    try:
        m = S.get(db_path, anchor)
        g = Grounder(m, _lexicon(m)).ground(question)
        q = g.query
        r.query = q
        rd = None
        if not q.unsupported and q.ambiguities and q.choices and not q.unresolved and \
                not any(_UNSTRUCTURED.search(a) for a in q.ambiguities):
            got = _readings(question, m, q, db_path, timeout_s, max_rows)
            rd, n_all = got if got else (None, 0)
        if q.unsupported:
            r.status, r.message = "unsupported", "; ".join(q.unsupported)
        elif rd and len(rd) == n_all and len(rd) > 1 and all(_same(rd[0][5], x[5]) for x in rd[1:]):
            label, q2, r.sql, r.params, r.columns, rows = rd[0]
            r.query = q = q2
            r.rows = rows[:max_rows]
            q.assumptions.append(f"the question can be read {len(rd)} ways ({' | '.join(x[0] for x in rd)}); "
                                 f"all give the same result")
            r.status = "answer"
        elif rd:
            def show(x):
                rows = x[5]
                return f"{x[0]}: {rows[0][0]:,.2f}" if len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], (int, float)) \
                    else f"{x[0]}: {len(rows)} rows"
            r.status = "clarify"
            same = all(_same(rd[0][5], x[5]) for x in rd[1:])
            r.message = "; ".join(q.ambiguities) + (". The readings give different results — " if not same else
                                                    ". Readings I could evaluate — ") + \
                "; ".join(show(x) for x in rd) + ". Which did you mean?"
        elif q.ambiguities:
            r.status, r.message = "clarify", "; ".join(q.ambiguities)
        elif q.unresolved:
            r.status, r.message = "clarify", "; ".join(q.unresolved)
        else:
            r.violations = verify(q, m)
            if r.violations:
                r.status, r.message = "clarify", "; ".join(r.violations)
            else:
                r.sql, r.params = Compiler(m).compile(q)
                r.columns, r.rows = _execute(db_path, r.sql, r.params, timeout_s, max_rows)
                if len(r.rows) > max_rows:
                    r.rows = r.rows[:max_rows]
                    r.message = f"showing the first {max_rows} rows"
                r.status = "answer"
        r.reliability = dict(
            grounding="complete" if q and not (q.unresolved or q.ambiguities) else "incomplete",
            ambiguities=len(q.ambiguities) if q else None, unresolved=len(q.unresolved) if q else None,
            plan_violations=len(r.violations), executed=r.status == "answer",
            empty_result=r.status == "answer" and (not r.rows or all(v is None for v in r.rows[0])),
            assumptions=len(q.assumptions) if q else None, inferred_joins=any(
                c.path is not None and c.path.inferred for c in q.cols()) if q else None,
            note="component indicators, not a calibrated probability")
    except CompileError as e:
        r.status, r.message = "unsupported", f"cannot compile safely: {e}"
    except sqlite3.Error as e:
        r.status, r.message = "error", f"execution failed: {e}"
    except Exception as e:                       # never answer from a half-built plan
        r.status, r.message = "error", f"internal error while planning: {type(e).__name__}: {e}"
    r.ms = round((time.perf_counter() - t0) * 1000, 1)
    return r
