from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .preserve import SemanticFinding, preserve
from .spec import SemanticSpec, build_spec
from .typecheck import typecheck


@dataclass
class SemanticReport:
    spec: SemanticSpec
    findings: List[SemanticFinding] = field(default_factory=list)

    @property
    def violations(self) -> List[SemanticFinding]:
        return [f for f in self.findings if f.severity == "violation"]

    @property
    def ok(self) -> bool:
        return not self.violations


def verify_semantics(question, plan, sql, result, explanation, ds, catalog=None) -> SemanticReport:
    spec = build_spec(question, plan, ds, catalog)
    findings = typecheck(spec, question, ds)
    findings += preserve(spec, sql, list(result.columns), list(result.rows), explanation or "", ds)
    return SemanticReport(spec, findings)
