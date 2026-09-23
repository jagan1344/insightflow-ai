# Defensible novelty — what can be claimed, what cannot

## Scope of this note

The InsightFlow AI project needs a narrow, defensible research
positioning. This document states it in one paragraph, then lists the
claims that follow from the measured evaluation and the ones that do
not.

## Recent-work check — status

**Not run in this environment.** A live literature check for 2025–2026
work on reliable Text-to-SQL, calibration/abstention in Text-to-SQL,
enterprise/conversational BI, agentic multi-agent BI, and
evidence-grounded analytics was **not** performed here — this session
has no live web search. The claim below is therefore stated narrowly
enough that it does not depend on that check, and it is bounded by two
concrete escape hatches:

- If a 2025–2026 paper describes *the same integrated reliability-to-
  decision layer* (SQL validity + schema alignment + KPI/business
  alignment + context consistency + data completeness + evidence
  strength + result consistency → single reliability score → policy),
  the claim narrows to *the specific instantiation for enterprise BI on
  a KPI semantic layer, with an empirical calibration-focused ablation*.
- If a survey already itemises calibration-driven abstention for
  Text-to-SQL, the claim narrows again to *the integration into a
  running conversational-BI product with an evidence chain that is
  itself the substrate of the decision*.

A follow-up literature scan must be performed before publishing. Any
paper found there must be cited and the phrasing above tightened.

## The narrow, defensible claim

> InsightFlow AI is a conversational-BI prototype in which SQL
> validation, schema alignment, KPI/business-rule alignment, ambiguity /
> out-of-scope detection, execution completeness, evidence strength and
> result consistency are combined into a single reliability score that
> drives an explicit Answer / Warn / Clarify / Abstain policy over a
> registered KPI semantic layer, and the result is evaluated for
> calibration and safe abstention on a project-generated benchmark that
> covers answerable, ambiguous, out-of-scope and diagnostic questions.

That is it. The evaluation supports this claim to the extent that it
shows:

- The seven-signal aggregate is **better calibrated** than SQL-only or
  SQL+KPI on the same data: **ECE 0.041** vs **0.059** and Brier **0.056**
  vs **0.059** [Measured on n=17 SQL-scored items].
- The full system correctly separates the answered questions from the
  clarified ones on **26/27 (96.3 %)** items, and the mean confidence for
  correct answers (0.983) differs from that for incorrect ones (0.970) —
  though narrowly, so the calibration gain matters more than the raw
  gap.
- One high-confidence error survives (see the error-analysis section of
  the research report), so the claim is **not** that reliability
  guarantees safe answers — only that adding these signals improves
  calibration without hurting decision correctness.

## Claims that must NOT be made

- ❌ "First-ever" anything.
- ❌ "No existing system does this."
- ❌ "100 % accurate", "eliminates hallucinations", "guarantees correct
   decisions".
- ❌ "State-of-the-art on Text-to-SQL." The rule-based generator is
   demo-schema-specific; the evaluation is on 17 SQL-scored items on
   that same schema.
- ❌ "Reproduces or beats BIRD." No; BIRD has 12,751 questions across
   95 databases and this experiment covers 17 SQL-scored items on one.
- ❌ "Improves accuracy over baselines." The ablation shows business
   accuracy is **unchanged** across A/B/C — the ablated variable only
   moves calibration and confidence, not the underlying SQL.
- ❌ "Deployable enterprise BI system." This is a prototype and a
   benchmark; production would need read-only DB roles, secret
   management, a real audit log, and real-scale evaluation.

## What the ablation actually earns

The reliability layer is not shown to make the system more accurate on
this benchmark. It is shown to make the system's own confidence *closer
to reality* — ECE drops by about a third. For a BI product whose
usefulness depends on when it refuses to answer, this is a
defensible-but-modest gain, and it is stated as such. If the ablation
had shown the layer was neutral or harmful, that would be the finding
of record.
