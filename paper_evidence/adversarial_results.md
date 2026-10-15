# Adversarial diagnostic — per-question + divergence

**Set size:** 12 hand-crafted questions targeting specific guards (A1 fidelity, A2 result validator, A3 hard cap). Each question's `targets_guard` field names the guard it was designed to stress.

**Reading guide:** `≠Full` means the configuration's
 (action, confidence_bucket) differs from Full's. Confidence buckets are quantized to 0.05 so a trivial float
 difference does not count as a divergence.

| QID | Targets | Full action/conf | B1 | A1 | A2 | A3 | Diverged |
|---|---|---|---|---|---|---|---|
| ADV01 | A3 | CLARIFY/0.05 | ANSWER/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | B1 |
| ADV02 | A2 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | — |
| ADV03 | A2 | ANSWER/0.97 | ANSWER/0.97 | ANSWER/0.97 | ANSWER/0.97 | ANSWER/0.97 | — |
| ADV04 | A1 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | ANSWER/0.99 | — |
| ADV05 | A1 | CLARIFY/0.88 | ANSWER/0.88 | ANSWER/0.98 | CLARIFY/0.88 | CLARIFY/0.88 | B1,A1 |
| ADV06 | A2 | ANSWER/1.00 | ANSWER/1.00 | ANSWER/1.00 | ANSWER/1.00 | ANSWER/1.00 | — |
| ADV07 | A3 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | — |
| ADV08 | A1 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | — |
| ADV09 | A1 | CLARIFY/0.05 | ANSWER/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | B1 |
| ADV10 | baseline | CLARIFY/0.05 | ANSWER/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | CLARIFY/0.05 | B1 |
| ADV11 | A3 | ANSWER/0.85 | ANSWER/0.85 | ANSWER/0.85 | ANSWER/0.85 | ANSWER/0.85 | — |
| ADV12 | baseline | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | ANSWER/0.98 | — |

## Divergence summary

- Questions in set: 12
- Diverged from Full (any config): 4
- B1 diverged from Full in: 4 / 12 questions
- A1 diverged from Full in: 1 / 12 questions
- A2 diverged from Full in: 0 / 12 questions
- A3 diverged from Full in: 0 / 12 questions

## Methodology notes

- Questions were drafted BEFORE running; `hypothesis`
  records the author's prediction of which guard would
  fire. The predictions were NOT revised after seeing
  outputs, so this is a true pre-registered diagnostic.
- The 27-question reliability benchmark is unchanged.
  This adversarial set is a SEPARATE artefact for
  ablation diagnostics and is not combined into the
  main semantic-accuracy / coverage / unsafe-rate tables.
- The verifier `evaluation/verify_ablations.py` already
  showed each switch disables its guard on crafted
  component inputs. This adversarial set shows whether
  natural-language questions can also trigger the
  guards at the end-to-end orchestrator level.