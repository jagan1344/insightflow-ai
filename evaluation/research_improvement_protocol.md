# InsightFlow AI: Research Improvement Evaluation Protocol

**Status:** Proposed protocol; not an evaluation result.  
**Purpose:** Pre-register how semantic correctness, independent evaluation, and safeguard contribution will be assessed.  
**Scope:** This protocol must not modify or replace historical K1/K3 artifacts.

## 1. Research questions

- **RQ1 — Semantic correctness:** For query categories explicitly supported by the frozen system, how often does the system return a result matching the independently adjudicated analytical meaning?
- **RQ2 — Safe clarification:** For ambiguous, unsupported, or unresolved questions, how often does the system clarify/abstain instead of presenting an unsupported result as correct?
- **RQ3 — Safeguard contribution:** Which checks detect errors that would otherwise reach the user, and what are the costs in unnecessary clarification and reduced answer coverage?

Do not frame this evaluation as proof of superiority over other systems unless a suitable baseline is run under the same protocol.

## 2. Separate historical and new evidence

1. Preserve the sealed K1 first-run evaluation and the post-hoc K3 evaluation exactly as they are.
2. Label K1 as the historical first-run result and K3 as post-hoc tuning on inspected K1 failures. K3 is not independent held-out evidence.
3. Store new evaluation inputs, reference annotations, run outputs, and summaries in new versioned files. Never overwrite pinned historical artifacts.
4. Before test questions are used to tune the system, freeze the implementation commit and record the question-set and annotation-file SHA-256 hashes.
5. If any sealed question is inspected during development, remove it from the independent test set and document the exclusion before scoring.

## 3. Question-set design and annotation

Prepare a new set of questions that was not used for implementation or tuning. Prefer questions written or reviewed by someone other than the primary implementer. Include multiple relational schemas and business domains; include a public or independently sourced schema where feasible, while retaining a separate synthetic stress-test set.

Target at least 120 new questions across at least four schema variants, if the available annotation budget permits. Treat this as a target, not a completed dataset or a guarantee of statistical power. Report actual counts and any deviations.

Stratify questions across:
- direct KPI / scalar aggregation;
- grouped breakdown and ranking;
- date filtering and time trends;
- related-table filters and foreign-key paths;
- distinct-entity counts and NULL handling;
- negation, exclusions, status flags, and numeric thresholds;
- join fan-out and aggregation-grain risks;
- ratios / derived measures and other unsupported formulas;
- ambiguous date roles, ambiguous KPI meanings, and diagnostic questions;
- out-of-scope requests.

For each item, record:
- stable question ID and exact question text;
- schema/database version and hash;
- answerability label: answerable, ambiguous, or unsupported;
- intended KPI, entity, aggregation grain, dimensions, filters, date role, and join assumptions, as applicable;
- reference SQL and independently executed expected result for answerable questions;
- acceptable alternative interpretations, where justified;
- adjudication status, annotator/reviewer roles, and reason for any exclusion.

Do not force a single reference SQL for a question with multiple valid interpretations. Resolve disagreement independently or label the item ambiguous and exclude it from the primary answer-accuracy denominator.

## 4. Freeze and execution procedure

1. Freeze the code commit before revealing the held-out question file to anyone tuning the system.
2. Record commit SHA, environment, Python/dependency versions, database hashes, configuration, and random seeds where applicable.
3. Run every eligible question once with a fixed configuration; preserve raw outputs, SQL, action, confidence, latency, and diagnostics.
4. Execute reference SQL against the same database snapshot and compare normalized results using predeclared numeric tolerances and NULL/group handling rules.
5. Keep the complete per-question ledger, including failures, exceptions, timeouts, and clarifications. Do not silently drop difficult cases.
6. If a bug is fixed after seeing held-out results, that set becomes diagnostic/development evidence. Use a new untouched set for the next independent estimate.

## 5. Primary metrics

Report counts and denominators alongside percentages.

### Answerable questions
- **Execution/semantic accuracy:** number of answered questions whose results match an adjudicated acceptable result, divided by all answerable questions.
- **Answer coverage:** number of answerable questions receiving ANSWER or WARN, divided by all answerable questions.
- **Unnecessary clarification rate:** answerable questions receiving CLARIFY or ABSTAIN, divided by all answerable questions.
- **Silent-wrong rate:** incorrect answers among all answerable questions, with both the count and denominator reported. Also report the count of wrong answers among all questions.

### Ambiguous and unsupported questions
- **Safe handling rate:** ambiguous/unsupported questions receiving the expected clarification or abstention, divided by all adjudicated ambiguous/unsupported questions.
- **Unsafe answer rate:** ambiguous/unsupported questions receiving an answer that violates the annotation or unsupported-scope policy, divided by all adjudicated ambiguous/unsupported questions.

### Confidence and latency
- Report confidence separately for correct answers, incorrect answers, and clarification/abstention decisions.
- Assess calibration only on independently labelled outcomes and state the exact population and denominator. Include a reliability plot and a proper calibration metric where sample size permits.
- Report local latency as local latency; do not infer production performance from it.

Provide 95% confidence intervals for key rates when the sample size and sampling design support them. Do not combine unrelated evaluation sets into one calibration estimate without an explicit rationale and set-specific results.

## 6. Safeguard ablations

Use the same frozen question set, database snapshots, runtime configuration, and scoring code for every configuration. Save one row per question and configuration. Predefine the ablations before examining their results.

Subject to the actual architecture and whether each component can be disabled safely, evaluate:
- full pipeline;
- without semantic type checking;
- without semantic-preservation checks;
- without the independent answer verifier;
- without mention-coverage checks;
- a simple planner/validator baseline, if it can be defined without changing other variables.

Do not assume a component is useful because its name suggests a benefit. Report for each ablation:
- accuracy and coverage changes relative to the full pipeline;
- changes in silent-wrong answers;
- errors uniquely caught by the removed safeguard;
- newly introduced wrong answers;
- additional clarifications or answers incorrectly blocked;
- execution failures and latency.

If components cannot be isolated without changing other behaviour, label the ablation as approximate and document the confound. Do not call identical outputs evidence of an improvement.

## 7. Error taxonomy

Manually classify each incorrect answer and each unnecessary clarification, preferably with independent review, using categories such as:
- dropped or inverted filter;
- wrong entity or aggregation grain;
- incorrect join / fan-out / missing relationship;
- wrong KPI or aggregation;
- date-role or boundary error;
- NULL or negation error;
- ratio / derived-measure ambiguity;
- unsupported query incorrectly answered;
- answer text inconsistent with executed result;
- verification false positive / false negative;
- infrastructure or execution failure.

Publish representative cases with question ID, expected interpretation, actual action/result, responsible stage, and whether a safeguard detected the issue. Avoid exposing private or sensitive source data.

## 8. Reporting and integrity rules

- Report failures, negative results, and regressions as well as improvements.
- Do not claim that clarification is always correct: measure unnecessary clarifications on answerable questions.
- Do not equate SQL execution success with semantic correctness.
- Do not describe confidence as a calibrated probability unless independent calibration evidence supports it.
- Do not describe K3 as held out, and do not compare results from different datasets as if they were a controlled experiment.
- Do not claim superiority over established systems without a matched baseline.
- Preserve exact source files and SHA-256 hashes for the code, question set, annotations, database snapshots, raw results, and analysis scripts.
- The protocol itself is not evidence that any metric has improved. Claims must be based on completed, reproducible runs.

## 9. Pre-run checklist

- [ ] Code freeze commit recorded.
- [ ] Held-out questions were not used during development.
- [ ] Reference annotations independently reviewed.
- [ ] Ambiguous items adjudicated or excluded from the primary accuracy denominator.
- [ ] Database snapshots and hashes recorded.
- [ ] Metrics, tolerances, and ablations fixed before scoring.
- [ ] Raw per-question outputs retained.
- [ ] Historical K1/K3 artifacts unchanged.
- [ ] Analysis script can reproduce every table and figure from the raw ledger.
