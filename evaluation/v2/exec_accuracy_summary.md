# Execution-accuracy benchmark

- **Commit:** `2ac37d5ad8d1d426a59ae27cc9c2258bb3975701`
- **Questions:** 27
- **Action accuracy:** 27 / 27 = 100.0%
- **Execution accuracy:** 27 / 27 = 100.0%

**Execution accuracy** means the system's numerical result
equals the independent oracle (stdlib sqlite3 or statistics)
within a 1e-4 relative tolerance.

| id | question | expected | observed | action ok | exec ok |
|---|---|---|---|:---:|:---:|
| S01 | What is the total revenue? | ANSWER | ANSWER | ✅ | ✅ |
| S02 | How many orders were placed? | ANSWER | ANSWER | ✅ | ✅ |
| S03 | What is the average order value? | ANSWER | ANSWER | ✅ | ✅ |
| S04 | What was revenue in July 2026? | ANSWER | ANSWER | ✅ | ✅ |
| S05 | What was revenue in June 2026? | ANSWER | ANSWER | ✅ | ✅ |
| S06 | What was revenue in September 2026? | ANSWER | ANSWER | ✅ | ✅ |
| S07 | Revenue in the last 30 days | ANSWER | ANSWER | ✅ | ✅ |
| S08 | What was revenue last month? | ANSWER | ANSWER | ✅ | ✅ |
| S09 | How many distinct customers do we have? | ANSWER | ANSWER | ✅ | ✅ |
| S10 | How many distinct products are there? | ANSWER | ANSWER | ✅ | ✅ |
| S11 | What is the maximum revenue? | ANSWER | ANSWER | ✅ | ✅ |
| S12 | What is the minimum revenue? | ANSWER | ANSWER | ✅ | ✅ |
| ST1 | What is the median order revenue? | ANSWER | ANSWER | ✅ | ✅ |
| ST2 | What is the 90th percentile of revenue? | ANSWER | ANSWER | ✅ | ✅ |
| ST3 | What is the standard deviation of revenue? | ANSWER | ANSWER | ✅ | ✅ |
| ST4 | What is the variance of revenue? | ANSWER | ANSWER | ✅ | ✅ |
| ST5 | What is the median order quantity? | ANSWER | ANSWER | ✅ | ✅ |
| B01 | Revenue by region | ANSWER | ANSWER | ✅ | ✅ |
| B02 | Revenue by category | ANSWER | ANSWER | ✅ | ✅ |
| T01 | Show monthly revenue from January through September 2026. | ANSWER | ANSWER | ✅ | ✅ |
| R01 | Top 5 products by revenue | ANSWER | ANSWER | ✅ | ✅ |
| H01 | In which months did revenue exceed 400000? | ANSWER | ANSWER | ✅ | ✅ |
| X01 | What will next month's revenue be? | CLARIFY | CLARIFY | ✅ | ✅ |
| X02 | Delete all orders. | ABSTAIN | ABSTAIN | ✅ | ✅ |
| X03 | What is the meaning of life? | CLARIFY | CLARIFY | ✅ | ✅ |
| X04 | How is my business doing? | CLARIFY | CLARIFY | ✅ | ✅ |
| X05 | Find duplicate orders | CLARIFY | CLARIFY | ✅ | ✅ |

## Failed (exec_match=False)
