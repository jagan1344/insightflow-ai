# Typed query plan (IR) and verification

Code: `backend/insightflow/engine/ir.py`, `backend/insightflow/engine/verify.py`.

## Nodes (frozen dataclasses, bounded tree)

| Node | Meaning |
|---|---|
| `Col(table, column, path)` | a column; `path=None` for the anchor, otherwise the exact join path (role included) |
| `Lit(value)` | a literal; always compiled as a bound parameter |
| `Agg(func, arg, where)` | `sum`, `avg`, `min`, `max`, `count` (arg None = rows), `count_distinct`; `where` makes it conditional |
| `Arith(op, left, right)` | `+ - * /`, used for row-level products (`SUM(qty*price)`) and for combining aggregates (ratios, differences, percentages) |
| `Cmp(col, op, Lit)` | `= != > >= < <=` |
| `InSet(col, values, negated)` | IN / NOT IN over stored values |
| `IsNull(col, negated)` | IS NULL / IS NOT NULL |
| `Exists(path, pred, negated)` | EXISTS / NOT EXISTS over a one-to-many path, with an optional inner predicate |
| `BoolOp(and/or, items)`, `Not(item)` | boolean structure |

`Measure(name, expr, unit)` is one output column. A `Query` holds:
- `measures`, `filters`, `group_by`, `time_bucket` (col, unit), `order_desc`, `limit`, `share_of_total`, `shape`;
- the record of how it was built: `evidence` (span → element, reason), `assumptions`, `ambiguities`, `unresolved`,
  `unsupported`.

## Shapes the grounder builds

| Question form | Plan |
|---|---|
| "total X", "average X", "highest X" | `Agg(fn, Col X)` |
| "how many orders" | `Agg(count)`; "how many <quantity>" sums the quantity |
| "number of distinct riders" / "customers who placed orders" | `count_distinct` of the anchor FK |
| "X times Y" | `SUM(X*Y)` (row-level product, then aggregated) |
| "X divided by Y", "X per Y", "X over Y" | `SUM(X) / SUM(Y)` (ratio of totals) |
| "X minus / plus Y" | `SUM(X) ∓ SUM(Y)`, noting that missing values count as nothing |
| "percentage of orders that are gifts" | `100 * COUNT(where gift) / COUNT(*)` (numerator condition after the subject) |
| "share of X by G" | per-group value / grand total (window) |
| "rentals with no issues", "orders returned as damaged" | `[NOT] EXISTS` over the child table, with an inner predicate when one is named |
| "orders not shipped", "exams not graded" | nullable date verb → `IS NULL` (`IS NOT NULL` without negation) |
| "never reopened" | count column → `= 0` (`> 0` without negation) |
| "unpaid", "unresolved" | `un-`/`non-` prefix negates a yes/no column |
| "Q1 vs Q2 2025 (difference)" | per-period conditional aggregates, plus their difference |
| "monthly", "by quarter" | time bucket on the stated date column |
| "top 3 X by Y" | grouping by X, ordered by Y, `LIMIT ?` |

## Verification before any SQL (`verify`)

A plan is rejected, and the reason is returned to the user as a clarification, when:
- there is no measure;
- an aggregate does not fit the column kind (SUM/AVG of a category, MIN/MAX of text);
- an arithmetic operand is not numeric;
- a column on a one-to-many path is used outside EXISTS (fan-out);
- an ordered comparison is on a non-numeric, non-date column, or a date is compared with a number;
- EXISTS runs over a many-to-one path;
- grouping is by a numeric measure, unless it is ordinal;
- a time series is bucketed on a non-date column;
- there is a share of total without groups, or a ranking without grouping.

The grounder already refuses, as *unsupported*, the following:
- aggregating a lookup attribute through a many-to-one join without saying over what (weighting);
- measures on one-to-many tables (they need that table as the base);
- relative dates;
- grouping through a one-to-many table;
- missing values that cannot be told apart from a missing link.

## Not supported (refused, never approximated)

- Date arithmetic: durations between two date columns ("average resolution time").
- Relative dates ("last 7 days").
- Medians and percentiles.
- Top-N within each group.
- Anti-joins from a lookup's side ("members with no visits").
- Measures at child grain combined with anchor grain.
- Nested aggregates.
- HAVING thresholds on grouped values.
- Forecasting.
- Synonyms not present in the schema or its values ("revenue", "visits", "borrowed").
