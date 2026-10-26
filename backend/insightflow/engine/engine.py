"""Entry point: question -> grounded typed Query -> verification -> parameterised SQL -> read-only execution,
with an evidence chain at every step."""
from __future__ import annotations

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


def answer(question: str, db_path: str, anchor: str, timeout_s: float = 10.0) -> EngineResult:
    t0 = time.perf_counter()
    r = EngineResult("error", question)
    try:
        m = S.get(db_path, anchor)
        g = Grounder(m, _lexicon(m)).ground(question)
        q = g.query
        r.query = q
        if q.unsupported:
            r.status, r.message = "unsupported", "; ".join(q.unsupported)
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
                con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                deadline = time.perf_counter() + timeout_s
                con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10000)
                try:
                    cur = con.execute(r.sql, r.params)
                    r.columns = [d[0] for d in cur.description]
                    r.rows = [tuple(x) for x in cur.fetchall()]
                finally:
                    con.close()
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
    r.ms = round((time.perf_counter() - t0) * 1000, 1)
    return r
