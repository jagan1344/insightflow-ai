# 07 — External baseline status: not run

An external text-to-SQL baseline could not be run fairly in this environment:
- No model API key is configured (checked by variable name only; no value was printed). Session
  infrastructure tokens exist but are not for this use and were not used.
- Hugging Face and GitHub downloads are blocked by the network proxy (HTTP 403), so neither open model
  weights nor the Spider/BIRD datasets could be fetched. No GPU, torch or transformers are installed.
- No published score is directly comparable: published text-to-SQL results use other databases, other
  questions and execution-match scoring without a clarify/abstain option.

What is reported instead: the internal "safeguards off" configuration A7 (same planner and compiler, all six
post-generation safeguards disabled) as a within-system reference (`04_ablation_analysis.md`). It is not an
external baseline and must not be described as one.

To run a fair external baseline later: give the same 105 questions and schema DDL to an LLM text-to-SQL
prompt (fixed model id and version, temperature 0), execute its SQL against the same databases, score with
`eval/score_v5.py` (treat no SQL as a clarification), and report wrong answers and coverage with the same denominators.
