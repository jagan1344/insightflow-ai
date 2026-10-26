"""Apply the Round 7 revision to the Round 6 v2 manuscript. Each edit asserts that the original passage
exists exactly once, so the change list is explicit and reviewable. Input: ../ieee_round6_v2_original/
InsightFlow_AI_IEEE_Round6_v2.tex (unchanged). Output: InsightFlow_AI_IEEE_Round7.tex."""
import pathlib
H = pathlib.Path(__file__).resolve().parent
s = (H.parent / "ieee_round6_v2_original" / "InsightFlow_AI_IEEE_Round6_v2.tex").read_text()
LOG = []


def rep(tag, old, new):
    global s
    assert s.count(old) == 1, (tag, s.count(old))
    s = s.replace(old, new); LOG.append(tag)


rep("header TODO",
r"""%   4. Reference [3]: add the track designation only if confirmed; reference [8]: add an access
%      date and, if MCP stays in the paper, the specification revision actually implemented.""",
r"""%   4. Reference [3]: add the track designation only if confirmed; reference [8]: add an access
%      date and, if MCP stays in the paper, the specification revision actually implemented.
%   5. Round 7 revision (this file): Fig. 5 (figures/fig_r7_ablation.pdf) was rendered with matplotlib
%      because no TeX installation was available; rebuild it from figures/src/fig_r7_ablation.tex to match
%      the other figures if preferred. This file was NOT compiled after the Round 7 edits; compile and check
%      layout, float placement and page count against the venue limit.
%   6. The Round 7 artifacts (revision 38b60d1 and later) were committed locally; push them before citing
%      the repository as containing them.
%   7. AI-assistance disclosure: the Round 7 implementation changes, question set and these edits were
%      produced with an AI coding agent. Check the venue's policy and add the required statement.""")

rep("abstract",
r"""We report two distinct experiments. In a historical 27-question benchmark on a synthetic sales database, an earlier version of the pipeline executed SQL for all 17 answerable questions and agreed with reference SQL on 15 of those 17 cases. The two disagreements involved diagnostic questions whose intended semantics were not independently adjudicated. In a separate first-run evaluation of the semantic-layer implementation, 66 questions were tested across airline, software-as-a-service (SaaS), and farm database schemas. Of 54 questions labelled answerable, 42 received correct answers, while 11 answerable questions were left unanswered. Two of the 66 cases were classified as silent wrong answers. Both had internal confidence scores near 0.98, indicating that the score alone did not reliably distinguish correct from incorrect outputs. Median and 95th-percentile latency in this run were 14 ms and 38 ms, respectively.

These results expose a practical trade-off between answer coverage and conservative clarification. They also show that explicit semantic checks remain incomplete and that high internal confidence should not be treated as evidence of correctness. The experiments do not establish calibrated confidence, general superiority over existing systems, or elimination of semantic errors. The findings provide an empirical basis for further evaluation of inspectable semantic validation on independently prepared schemas and broader analytical workloads.""",
r"""We report three experiments that are not pooled. In a historical 27-question benchmark on a synthetic sales database, an earlier pipeline agreed with reference SQL on 15 of 17 answerable questions. In a sealed 66-question first run over airline, software-as-a-service (SaaS), and farm schemas (K1), the semantic-layer implementation answered 42 of 54 answerable questions correctly and produced two silent wrong answers, both with internal confidence near 0.98. In a third evaluation (R7), a later revision was frozen and run once on 105 new questions over four synthetic schemas authored by a separate agent process; these questions are not human-adjudicated. The system answered 14 of 74 answerable questions correctly (18.9\%), left 57 unanswered, declined 27 of 31 questions that required clarification or were out of scope, and gave 7 wrong answers among the 105 questions. With six post-generation safeguards disabled, the same build gave 32 wrong answers and 17 correct ones. Paired ablations attribute most of this reduction to checks that compare the question's wording with the executed query, and part to the semantic layer; four other safeguards changed no outcome. Every R7 answer, correct or not, had confidence of at least 0.979.

The results show that explicit checks of the question against the executed query can prevent most silent errors on unfamiliar schemas, at a large cost in coverage, and that the internal confidence score is not calibrated. The experiments do not establish general superiority over existing systems or elimination of semantic errors.""")

rep("keywords", "selective prediction, query verification", "selective prediction, query verification, ablation study")

rep("intro experiments",
r"""This paper evaluates the prototype through two separate experiments. The first is a historical benchmark of an earlier pipeline on a synthetic sales database. The second evaluates the first-run behaviour of the semantic-layer implementation on a sealed set of questions spanning three database schemas. The results are reported separately because the experiments use different system revisions, datasets, and evaluation protocols.""",
r"""This paper evaluates the prototype through three separate experiments. The first is a historical benchmark of an earlier pipeline on a synthetic sales database. The second evaluates the first-run behaviour of the semantic-layer implementation on a sealed set of questions spanning three database schemas (Round 6). The third freezes a later revision and runs it once on 105 new questions over four further schemas written by a separate agent process (Round 7), and then disables the safeguards one at a time on the same build. The results are reported separately because the experiments use different system revisions, datasets, and evaluation protocols.""")

rep("contribution 2",
r"""  \textbf{Two-stage empirical evaluation:} We report historical reference-SQL agreement results and a separate first-run evaluation of semantic validation across airline, SaaS, and farm schemas.""",
r"""  \textbf{Three-stage empirical evaluation:} We report historical reference-SQL agreement results, a sealed first-run evaluation of semantic validation across airline, SaaS, and farm schemas, and a frozen first run on four new schemas whose questions were written without access to the implementation.
\item
  \textbf{Safeguard ablation:} On the frozen Round 7 build we disable each post-generation safeguard alone, all together, and all but one, and attribute each prevented error to a component through paired per-question transitions.""")

rep("arch caption", r"""\texttt{78d906b} (K1), \texttt{a63cec1} (K3) and \texttt{b11793b}.""",
    r"""\texttt{78d906b} (K1), \texttt{a63cec1} (K3), \texttt{b11793b} and \texttt{38b60d1} (R7).""")

rep("fail-closed R7",
r"""revision \texttt{b11793b}, committed after both Round 6 runs, returns CLARIFY instead (fail-closed). No Round 6 results are reported for that revision.""",
r"""revision \texttt{b11793b}, committed after both Round 6 runs, returns CLARIFY instead (fail-closed). No Round 6 results are reported for that revision. The Round 7 evaluation (Section~\ref{sec:r7method}) uses revision \texttt{38b60d1}, which includes the fail-closed handling and one further rule, \texttt{count\_\allowbreak{}of\_\allowbreak{}measure\_\allowbreak{}noun}.""")

rep("rules caption", r"""\caption{Implemented Semantic Rules at Revision a63cec1}""",
    r"""\caption{Implemented Semantic Rules at Revision 38b60d1}""")
rep("rules row",
r"""\texttt{ratio\_\allowbreak{}unsupported} & ``Per X'' ratio of two measures that the query does not compute & K3 \\""",
r"""\texttt{ratio\_\allowbreak{}unsupported} & ``Per X'' ratio of two measures that the query does not compute & K3 \\
\texttt{count\_\allowbreak{}of\_\allowbreak{}measure\_\allowbreak{}noun} & ``How many X'' where X names a quantity column, answered by counting rows & R7 \\""")
rep("rules note",
r"""K1: present at \texttt{78d906b}; K3: added in \texttt{a63cec1}, after the K1 run.""",
r"""K1: present at \texttt{78d906b}; K3: added in \texttt{a63cec1}, after the K1 run; R7: added in \texttt{38b60d1}, before the R7 run.""")

rep("method intro",
r"""The evaluation comprises two experiments with different purposes. The historical benchmark measures an earlier pipeline on a synthetic sales database. The Round 6 evaluation measures the first-run behaviour of the newer semantic-layer implementation across three schemas. Results from these experiments are not pooled.""",
r"""The evaluation comprises three experiments with different purposes. The historical benchmark measures an earlier pipeline on a synthetic sales database. The Round 6 evaluation measures the first-run behaviour of the newer semantic-layer implementation across three schemas. The Round 7 (R7) evaluation measures a later frozen revision on four new schemas and includes safeguard ablations. Results from these experiments are not pooled.""")

rep("r7 method",
r"""\subsection{Reproducibility}

The project source code""",
r"""\subsection{Round 7: Frozen First Run on Agent-Authored Schemas}
\label{sec:r7method}

After K3, development continued on the Round 6 schemas and on earlier development sets. The changes generalize patterns observed there: comparative wording (``larger than'', ``at least'') for numeric conditions on related tables, with an unrecognized comparative never read as equality; flags whose names state the normal condition (e.g.\ \texttt{sensor\_ok}) selected only when the question names that condition, its negation or a listed antonym such as ``faulty''; expanded abbreviations for measure names; a weaker foreign-key inference tier for role-prefixed text codes that share the key suffix of a single parent key and are fully contained in it, always disclosed with a warning; ``average X per'' the base-table row read as a plain average; semi-join filters for value-qualified fan-out phrases; and the rule \texttt{count\_\allowbreak{}of\_\allowbreak{}measure\_\allowbreak{}noun}. On the Round 6 questions this revision answers 54 of 54 answerable questions correctly with no silent wrong answer, but these questions informed the changes, so this is not held-out evidence. The implementation was then frozen at revision \texttt{38b60d1}, after the backend regression suite passed (526 tests).

The R7 questions were written by a separate AI agent process of the same model family as the development agent, instructed not to read the implementation, documentation, results or earlier question sets; this isolation was self-reported and not independently verified. The agent created four synthetic SQLite schemas: hotel bookings (950 bookings), insurance claims (1,100 claims), energy billing (1,250 bills) and ride-hailing (1,450 trips), each with two to four related tables. The schemas include abbreviated column names, 0/1 flags with both positive and normal-condition names, real NULL values, two or three date columns per fact table, undeclared and role-playing foreign keys, one-to-many child tables, lookup members without fact rows, and values containing apostrophes, ampersands and parentheses. It wrote 105 questions: 74 answerable, 19 requiring clarification and 12 unsupported, across 21 categories. Every answerable question has reference SQL and an independently written alternative query that returns the same result; for every clarification item, the competing readings give different results on the data.

Before the run, the scoring rules were fixed: those of Round 6, plus acceptance of a rate stated either as a percentage or as a fraction for eight rate questions, and tolerance of extra zero-valued rows in breakdowns. The authoring agent listed 20 questions as borderline; they are used only for a sensitivity analysis. A SHA-256 manifest of the questions, references, databases and scripts was committed, the frozen build was run once, and the raw output was committed before scoring. No label was changed afterwards. Because the questions are agent-generated and not human-adjudicated, R7 is provisional evidence rather than an independent benchmark.

\subsection{Safeguard Ablation}

A research-only environment switch, which the default pipeline never sets, disables six post-generation safeguards: the semantic layer; the confidence threshold rule; result-consistency checks (result validation, semantic fulfilment, empty-period check); the plan-to-SQL fidelity gate; the mention-coverage checks together with the wording audit; and the answer verifier. Configurations A1--A6 remove one safeguard each, A7 removes all six, and B1--B6 keep exactly one. All configurations use the frozen build, databases, questions and scorer of R7, and outcomes are compared question by question. A5 removes two checks that share one pipeline stage, so their separate contributions are not isolated. A second run of the full pipeline reproduced the first run on all 105 questions.

\subsection{Reproducibility}

The project source code""")

rep("table III",
r"""\begin{table}[!t]
\caption{Historical and Round 6 Results: Distinct Revisions, Question Sets and Denominators}
\label{tab:results}
\centering
\footnotesize
\setlength{\tabcolsep}{2.5pt}
\begin{tabular}{@{}>{\raggedright}p{0.345\columnwidth}>{\centering}p{0.19\columnwidth}>{\centering}p{0.19\columnwidth}>{\centering\arraybackslash}p{0.21\columnwidth}@{}}
\toprule
 & \textbf{Historical} & \textbf{K1} & \textbf{K3} \\
\midrule
Revision & \texttt{3c843de} & \texttt{78d906b} & \texttt{a63cec1} \\
Run type & First recorded run & First run, sealed set & Post-hoc, not held out \\
Questions (answerable / other) & 27 (17 / 10) & 66 (54 / 12) & 66 (54 / 12) \\
\midrule
Correct / answerable & 15/17$^{a}$ & 42/54 & 49/54 \\
Answered / answerable & 17/17 & 43/54 & 49/54 \\
Unanswered / answerable & 0/17 & 11/54 & 5/54 \\
Silent wrong / all questions & n/a$^{b}$ & 2/66 & 0/66 observed \\
Correct clarifications / labelled & 10/10 & 11/12 & 12/12 \\
Mean confidence, correct answers & --- & 0.976 & 0.977 \\
Mean confidence, silent wrong & --- & 0.979 & --- \\
Latency, median / p95 (ms) & 4 / 6 & 14 / 38 & 15 / 43 \\
\bottomrule
\end{tabular}

\vspace{3pt}
\parbox{\columnwidth}{\scriptsize $^{a}$Agreement with the reference SQL, not adjudicated semantic correctness. $^{b}$Not measured on the same basis: two answered questions disagreed with the reference SQL and were not adjudicated. K3 was obtained after inspecting the K1 failures and is not held-out evidence.}
\end{table}""",
r"""\begin{table*}[!t]
\caption{Historical, Round 6 and Round 7 Results: Distinct Revisions, Question Sets and Denominators}
\label{tab:results}
\centering
\footnotesize
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}>{\raggedright}p{0.25\textwidth}>{\centering}p{0.14\textwidth}>{\centering}p{0.14\textwidth}>{\centering}p{0.14\textwidth}>{\centering\arraybackslash}p{0.22\textwidth}@{}}
\toprule
 & \textbf{Historical} & \textbf{K1} & \textbf{K3} & \textbf{R7} \\
\midrule
Revision & \texttt{3c843de} & \texttt{78d906b} & \texttt{a63cec1} & \texttt{38b60d1} \\
Run type & First recorded run & First run, sealed set & Post-hoc, not held out & First run, frozen; agent-authored set$^{c}$ \\
Questions (answerable / other) & 27 (17 / 10) & 66 (54 / 12) & 66 (54 / 12) & 105 (74 / 31) \\
\midrule
Correct / answerable & 15/17$^{a}$ & 42/54 & 49/54 & 14/74 \\
Answered / answerable & 17/17 & 43/54 & 49/54 & 17/74 \\
Unanswered / answerable & 0/17 & 11/54 & 5/54 & 57/74 \\
Silent wrong / all questions & n/a$^{b}$ & 2/66 & 0/66 observed & 7/105 \\
Correct clarifications / labelled & 10/10 & 11/12 & 12/12 & 27/31 \\
Mean confidence, correct answers & --- & 0.976 & 0.977 & 0.988 \\
Mean confidence, silent wrong & --- & 0.979 & --- & 0.981 \\
Latency, median / p95 (ms) & 4 / 6 & 14 / 38 & 15 / 43 & 54 / 660 \\
\bottomrule
\end{tabular}

\vspace{3pt}
\parbox{\textwidth}{\scriptsize $^{a}$Agreement with the reference SQL, not adjudicated semantic correctness. $^{b}$Not measured on the same basis: two answered questions disagreed with the reference SQL and were not adjudicated. K3 was obtained after inspecting the K1 failures and is not held-out evidence. $^{c}$Questions written by a separate AI agent process without access to the implementation (self-reported) and not human-adjudicated.}
\end{table*}""")

rep("errors table rows",
r"""Verifier exceptions & Fail-open at \texttt{78d906b} and \texttt{a63cec1} & Fail-open & Fail-closed from \texttt{b11793b}; Round 6 not re-run at that revision \\
Scope of the semantic layer & Not applied to the demo dataset or to intents other than direct KPI, breakdown, top-$N$, trend & \texttt{ratio} intent kind added & Other intents rely on the earlier checks only \\
Unsupported patterns & Ratios of measures, period-over-period with dimensions, share of total over joins, many-to-many grouping, anti-joins, non-ISO dates, undeclared foreign keys, non-SQLite engines, non-English questions & Unchanged & Outside the current rules \\""",
r"""Verifier exceptions & Fail-open at \texttt{78d906b} and \texttt{a63cec1} & Fail-open & Fail-closed from \texttt{b11793b}, included in the R7 revision; no verifier exception occurred in any R7 run \\
Scope of the semantic layer & Not applied to the demo dataset or to intents other than direct KPI, breakdown, top-$N$, trend & \texttt{ratio} intent kind added & Other intents rely on the earlier checks only (R7 case IN14 is a distinct count) \\
Unsupported patterns & Ratios of measures, period-over-period with dimensions, share of total over joins, many-to-many grouping, anti-joins, non-ISO dates, undeclared foreign keys, non-SQLite engines, non-English questions & Unchanged & Outside the current rules; undeclared foreign keys are inferred only with name or key-suffix evidence (R7 revision) \\
\midrule
R7 wrong values (3 of 74 answerable) & RI12: ``not paid in cash'' kept only cash trips (204 vs.\ 1,039); IN04: ``claimed amount'' not bound, rows counted per adjuster at confidence 0.996; IN14: correct distinct count with an unrequested sum column appended & R7 revision frozen; no changes after the run & Negated value filters, fallback to a row count, and extra columns are not covered by the current rules \\
R7 answers to clarification items (4 of 31) & HO08: one of two date columns chosen; HO21: ``doing best'' resolved to a booking count; RI24: ``tip rate'' answered as a sum; IN28: ``average claim'' (flagged borderline by its author) & Frozen & Vague metrics and ``rate'' wording are not modelled \\
R7 unanswered (57 of 74 answerable) & Unbound measure paraphrases 20; ordinary words flagged by the unexplained-word check 11; unbound dimension words or negative-existence phrasing 11; unused column words 7; unused numbers 3; other 5 & Frozen & Lexical grounding on unfamiliar wording; the same checks prevent most wrong answers (Section~\ref{sec:ablation}) \\""")

rep("r7 results",
r"""\section{Discussion}""",
r"""\subsection{Round 7 First-Run Results}

Table~\ref{tab:results} lists the R7 first-run measures alongside the earlier experiments, and Table~\ref{tab:r7} adds intervals and the sensitivity analysis. The frozen build answered 17 of the 74 answerable questions, 14 of them correctly. It declined all 12 unsupported questions and 15 of the 19 questions labelled as requiring clarification. Of its 7 wrong answers, 3 are wrong values on answerable questions and 4 are answers to questions labelled as requiring clarification (Table~\ref{tab:errors}). Removing the 20 questions that the authoring agent had flagged as borderline gives 14 correct answers among 65 answerable questions and 5 wrong answers among 85 questions, so the conclusions do not depend on those labels.

Coverage is far lower than in K1 (42 of 54). The K1 questions were written in the same process as the implementation, whereas the R7 schemas and phrasing were new to it. The most frequent causes of an unnecessary clarification were measure phrases that the planner could not bind, such as ``amount claimed'', ``kilowatt-hours'' and ``room nights'', and ordinary words flagged by the unexplained-word check, such as ``break down'' and ``came from''.

\begin{table}[!t]
\caption{Round 7 First Run (Frozen Revision 38b60d1)}
\label{tab:r7}
\centering
\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}>{\raggedright}p{0.50\columnwidth}>{\raggedleft\arraybackslash}p{0.44\columnwidth}@{}}
\toprule
\textbf{Measure} & \textbf{Value [95\% Wilson interval]} \\
\midrule
Correct / answerable & 14/74 = 18.9\% [11.6, 29.3] \\
Correct / answered answerable & 14/17 = 82.4\% [59.0, 93.8] \\
Silent wrong / all questions & 7/105 = 6.7\% [3.3, 13.1] \\
Declined: clarification / unsupported & 15/19 / 12/12 \\
Without 20 borderline items & 14/65 correct; 5/85 wrong \\
Confidence of answers (min) & 0.979 \\
ECE, answered items, 5 bins & 0.32 \\
AUROC, correct vs.\ wrong answers & 0.67 \\
Latency, median / p95 & 54 ms / 660 ms \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Safeguard Ablation Results}
\label{sec:ablation}

Table~\ref{tab:ablation} and Fig.~\ref{fig:r7abl} summarize the ablations. Disabling all six safeguards (A7) raised wrong answers from 7 to 32 and correct answers from 14 to 17. Removing the mention-coverage and wording checks (A5) turned 21 of the full pipeline's clarifications into wrong answers and 3 into correct answers; used alone (B5), these checks prevented 24 of the 32 errors seen in A7 at the cost of 3 correct answers. The semantic layer used alone (B1) prevented 4 errors (RI19, EN09, EN10, EN12) without losing a correct answer; three of those are also caught by the coverage checks, so removing it from the full pipeline (A1) added one wrong answer (EN12). The confidence threshold rule, the result-consistency checks, the plan-to-SQL fidelity gate and the answer verifier changed no outcome in any configuration. This does not show that they are ineffective in general, since regression tests exercise them on constructed failures, but this question set did not trigger them. Every executed answer scored at least 0.979, so the 0.70 and 0.40 thresholds never applied.

\begin{table}[!t]
\caption{Round 7 Safeguard Ablation (105 Questions; 74 Answerable)}
\label{tab:ablation}
\centering
\footnotesize
\setlength{\tabcolsep}{2.5pt}
\begin{tabular}{@{}>{\raggedright}p{0.44\columnwidth}>{\centering}p{0.12\columnwidth}>{\centering}p{0.13\columnwidth}>{\centering}p{0.11\columnwidth}>{\centering\arraybackslash}p{0.14\columnwidth}@{}}
\toprule
\textbf{Configuration} & \textbf{Correct} & \textbf{Answered} & \textbf{Wrong} & \textbf{Unnec.\ clarif.} \\
\midrule
A0 full pipeline & 14 & 17 & 7 & 57 \\
A1 without semantic layer & 14 & 18 & 8 & 56 \\
A2 without confidence threshold & 14 & 17 & 7 & 57 \\
A3 without result consistency & 14 & 17 & 7 & 57 \\
A4 without plan fidelity gate & 14 & 17 & 7 & 57 \\
A5 without coverage + wording & 17 & 38 & 28 & 36 \\
A6 without answer verifier & 14 & 17 & 7 & 57 \\
A7 all six removed & 17 & 41 & 32 & 33 \\
B1 only semantic layer & 17 & 38 & 28 & 36 \\
B5 only coverage + wording & 14 & 18 & 8 & 56 \\
\bottomrule
\end{tabular}

\vspace{3pt}
\parbox{\columnwidth}{\scriptsize Correct and Answered: of 74 answerable. Wrong: of 105 questions. B2, B3, B4 and B6 equal A7. A5 removes two checks in one stage and is confounded between them.}
\end{table}

\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{figures/fig_r7_ablation.pdf}
\caption{Round 7 ablation on the frozen revision \texttt{38b60d1}: correct answers, wrong answers and unnecessary clarifications for configurations that change at least one outcome. A2, A3, A4 and A6 equal A0.}
\label{fig:r7abl}
\end{figure}

\subsection{Confidence on Round 7}

All 21 answers of the full pipeline, and all 49 answers with the safeguards disabled, scored between 0.979 and 1.0; every wrong answer was therefore a high-confidence error. Accuracy among answered questions was 0.67 in A0 and 0.35 in A7, against a mean score near 0.985, giving expected calibration errors of 0.32 and 0.64 \cite{naeini2015bbq}. The area under the ROC curve for separating correct from wrong answers was 0.67 and 0.69. This weak separation follows answer shape rather than correctness: plain scalar answers receive 0.979, while breakdowns that reconcile with their totals receive 0.99--1.0, and most wrong answers were scalars. A higher threshold could trade coverage for risk, but such an operating point would have to be chosen on held-out data. The protection measured in Section~\ref{sec:ablation} comes from checks that override the decision, not from the score.

\section{Discussion}""")

rep("discussion fifth",
r"""Finally, the difference between K1 and K3 illustrates""",
r"""Fifth, R7 shows how strongly the earlier first-run results depended on schemas and wording written in the same process as the implementation. On new schemas and phrasing, coverage fell to 17 of 74 answerable questions while wrong answers stayed at 7 of 105. The ablation shows that this caution is not incidental: the checks that compare the question's words with the executed query prevented 24 of the 32 errors seen without safeguards, and the same checks account for most unnecessary clarifications. Improving grounding without weakening those checks is therefore the main engineering problem identified by this study.

Finally, the difference between K1 and K3 illustrates""")

rep("lim synthetic",
r"""\textbf{Synthetic datasets and limited scale.} The experiments use relatively small, synthetic datasets and author-written questions. The results do not establish performance on production enterprise data, broader user populations, or naturally occurring business questions.""",
r"""\textbf{Synthetic datasets and limited scale.} The experiments use relatively small, synthetic datasets. The historical and Round 6 questions were written by the authors; the R7 questions were generated by an AI agent of the same model family as the development agent, under instructions not to read the implementation, and no human adjudicated their labels. R7 is therefore provisional evidence, and its intervals are wide. The results do not establish performance on production enterprise data, broader user populations, or naturally occurring business questions.""")

rep("lim partial",
r"""Heuristic synonyms and word stems may also over-trigger or fail to identify intended concepts.""",
r"""Heuristic synonyms and word stems may also over-trigger or fail to identify intended concepts; in R7 they caused most of the 57 unnecessary clarifications. R7 also exposed error classes that the rules do not cover: a negated value filter applied with the wrong polarity, an unbound measure phrase that fell back to a row count, an unrequested extra column, and ``rate'' wording answered as a sum.""")

rep("lim confidence",
r"""\textbf{Confidence calibration.} The observed high-confidence errors show that the current confidence score is not a sufficient guarantee of correctness. The reported values do not establish calibrated probabilities, and the pooled calibration report covers several different evaluation sets.""",
r"""\textbf{Confidence calibration.} The observed high-confidence errors show that the current confidence score is not a sufficient guarantee of correctness. In R7 every answer scored at least 0.979 and the expected calibration error was 0.32. The reported values do not establish calibrated probabilities, and the pooled calibration report covers several different evaluation sets.

\textbf{Ablation scope.} Four of the six safeguards changed no R7 outcome; their value is not demonstrated by this evaluation. The coverage and wording checks were ablated together and are not separated.""")

rep("lim external",
r"""The results therefore do not support a claim of superiority over existing systems.""",
r"""The results therefore do not support a claim of superiority over existing systems. For R7, no language-model access or downloadable baseline was available in the evaluation environment; the configuration with all safeguards disabled is an internal reference, not an external baseline.""")

rep("conclusion r7",
r"""The post-hoc K3 results improved on the evaluated cases,""",
r"""In the Round 7 first run on four new agent-authored schemas, a later frozen revision answered 14 of 74 answerable questions correctly, declined 27 of 31 questions that required clarification or were unsupported, and gave 7 wrong answers among 105 questions, against 32 with its post-generation safeguards disabled. The checks comparing the question with the executed query produced most of this reduction; the confidence score did not separate correct from wrong answers.

The post-hoc K3 results improved on the evaluated cases,""")

rep("repro r7",
r"""These tests check implementation behavior; they are not an accuracy benchmark, and no Round 6 results are reported for that revision.""",
r"""These tests check implementation behavior; they are not an accuracy benchmark, and no Round 6 results are reported for that revision.

The Round 7 build was frozen at revision \texttt{38b60d1} after 526 regression tests passed. The R7 questions, reference results, databases and protocol are in \texttt{evaluation/\allowbreak{}v5\_provisional/} and \texttt{research\_\allowbreak{}improvement/\allowbreak{}eval/}; the SHA-256 manifest \texttt{V5\_MANIFEST.sha256} was committed before the first run, and the raw first-run output (\texttt{v5\_A0\_first\_run.json}) was committed before it was scored. Ablation runs, the confidence analysis and a script that recomputes every reported R7 figure are in \texttt{research\_\allowbreak{}improvement/}.""")

(H / "InsightFlow_AI_IEEE_Round7.tex").write_text(s)
print(len(LOG), "edits applied:", ", ".join(LOG))
