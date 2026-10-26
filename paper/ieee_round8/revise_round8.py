"""Round 8 revision: applies asserted edits to ../ieee_round7/InsightFlow_AI_IEEE_Round7.tex (unchanged) and
writes InsightFlow_AI_IEEE_Round8.tex. Adds the post-hoc development result on the revealed R7 set and the
blind first run (R8) of the revised build, with ablations and confidence. R7 results stay as recorded."""
import pathlib
H = pathlib.Path(__file__).resolve().parent
s = (H.parent / "ieee_round7" / "InsightFlow_AI_IEEE_Round7.tex").read_text()
LOG = []


def rep(tag, old, new):
    global s
    assert s.count(old) == 1, (tag, s.count(old))
    s = s.replace(old, new); LOG.append(tag)


rep("header", r"""%   7. AI-assistance disclosure:""", r"""%   8. Round 8 revision (this file): adds Section IV-G/V-K..V-M; not compiled; check page count.
%   7. AI-assistance disclosure:""")

rep("abstract", r"""Every R7 answer, correct or not, had confidence of at least 0.979.""",
r"""Every R7 answer, correct or not, had confidence of at least 0.979. After inspecting the R7 failures we revised the planner's grounding; on the revealed R7 questions the revised build answers 63 of 74 correctly (post-hoc, not held out), but on a further blind set of 106 questions over four new schemas (R8) it answered only 5 of 73 answerable questions correctly and gave 10 wrong answers, so the improvement did not generalize. On R8 the internal confidence score did not separate correct from wrong answers (AUROC 0.45).""")

rep("intro", r"""and then disables the safeguards one at a time on the same build.""",
r"""and then disables the safeguards one at a time on the same build. A fourth step revises the implementation using the R7 failures and evaluates the revised, frozen build on a new blind set (Round 8).""")

rep("method r8", r"""\subsection{Reproducibility}

The project source code""",
r"""\subsection{Round 8: Post-Hoc Revision and Blind Re-Evaluation}
\label{sec:r8method}

After R7 we traced every unanswered answerable question and every wrong answer through planning, SQL generation and the vetoes. Of the 57 unanswered R7 questions, 22 produced no SQL, 29 produced SQL that disagreed with the reference (the veto was right), and only 6 produced correct SQL that a veto rejected. We therefore changed grounding rather than the vetoes: a question-normalization step that rewrites wording to the schema's own vocabulary only when the target exists in the schema (thousands separators, hyphenated and phrasal compounds, multi-word column names, unit words, synonym groups, stored acronyms, revenue words), with every rewrite recorded and interpretive rewrites stated in the answer; composite questions whose formula the wording states (percentage of rows, share of a total, an explicit ``A divided by B'', a difference between two periods whose order is stated), answered from two sub-questions that each pass the full pipeline; comparator suffixes (``1000 or more''); null-state phrasing; flag-polarity synonyms; exclusion cues; and four new wording checks (comparator preserved, negated value kept, rate not computed, vague metric). No veto was removed or relaxed by threshold. We added 71 development tests, including metamorphic tests on a separate schema (renaming, row order, unrelated tables, duplicated child rows). The revised build was frozen at revision \texttt{da925ad} after 597 regression tests passed and the six earlier evaluation sets reproduced their previous outcomes.

The R8 questions were written by a new agent process under the same isolation instructions as R7, and additionally without access to the R7 questions or analyses: 106 questions over four new synthetic schemas (food delivery, property leases, telecom billing, warehouse moves), 73 answerable, 20 requiring clarification and 13 unsupported, with independently written alternative SQL for every answerable item. The protocol, scoring rules and hashes were committed before a single run, and no code was changed afterwards. Like R7, R8 is agent-generated and not human-adjudicated.

\subsection{Reproducibility}

The project source code""")

rep("results r8", r"""\section{Discussion}""",
r"""\subsection{Round 8: Revised Build on Revealed and Blind Questions}

On the revealed R7 questions the revised build answers 63 of 74 answerable questions correctly and gives 2 wrong answers among 105, against 14 and 7 in the R7 first run; 49 correct answers were gained and none lost. These questions informed the changes, so this is a post-hoc development result. On the blind R8 set the same frozen build answered 11 of 73 answerable questions, 5 correctly (6.8\%, 95\% CI 3.0--15.1\%), refused 29 of 33 questions that required clarification or were unsupported, and gave 10 wrong answers among 106 questions (9.4\%, 95\% CI 5.2--16.5\%), see Table~\ref{tab:r8}. R7 and R8 use different questions, so the two first runs are not a paired comparison; but the revised build shows no improvement on unseen data, and the post-hoc gain must be read as fitting to the questions that motivated it. The R8 wrong answers include new classes: a time-unit word (``monthly rent'') read as a trend over a numeric column at confidence 1.0, an inverted date-state condition (``ever signed''), a product of two columns returned as two sums, and vague requests (``big orders'', ``top-paying tenants'') answered with a default metric.

\begin{table}[!t]
\caption{Round 8: Revised Build (da925ad) on Revealed (Post-Hoc) and Blind Questions}
\label{tab:r8}
\centering
\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}>{\raggedright}p{0.40\columnwidth}>{\centering}p{0.26\columnwidth}>{\centering\arraybackslash}p{0.26\columnwidth}@{}}
\toprule
 & \textbf{R7 set, post-hoc} & \textbf{R8 blind, first run} \\
\midrule
Questions (answerable / other) & 105 (74 / 31) & 106 (73 / 33) \\
Correct / answerable & 63/74 & 5/73 \\
Answered / answerable & 64/74 & 11/73 \\
Wrong answers / all & 2/105 & 10/106 \\
Appropriate refusals & 30/31 & 29/33 \\
All safeguards off: correct / wrong & 64 / 9 & 9 / 35 \\
Latency, median / p95 (ms) & 214 / 796 & 319 / 1,741 \\
\bottomrule
\end{tabular}

\vspace{3pt}
\parbox{\columnwidth}{\scriptsize The R7 column is post-hoc (the questions guided the changes) and is not held out. R8 questions are agent-generated, not human-adjudicated.}
\end{table}

The ablations on R8 repeat the R7 pattern. Disabling all six safeguards gives 9 correct and 35 wrong answers. Used alone, the mention-coverage and wording checks prevent 23 of those 35 errors at the cost of 4 correct answers, the semantic layer prevents 4, and the plan-to-SQL fidelity gate prevents 2; the confidence threshold, the result-consistency checks and the answer verifier change no outcome. On R8 every answer scored at least 0.835 and 9 of the 10 wrong answers scored at least 0.9; the area under the ROC curve for separating correct from wrong answers was 0.45 (0.48 with the safeguards disabled), no better than chance, and the expected calibration error was 0.64.

\section{Discussion}""")

rep("discussion r8", r"""Improving grounding without weakening those checks is therefore the main engineering problem identified by this study.""",
r"""Improving grounding without weakening those checks is therefore the main engineering problem identified by this study. Round 8 shows how hard that problem is: grounding changes derived from inspected failures fixed those failures but did not raise accuracy on new schemas and wording, while the checks again prevented most of the errors that the planner would otherwise have returned.""")

rep("lim posthoc", r"""\textbf{Post-hoc evaluation.} K3 was tuned after K1 failure cases had been inspected.""",
r"""\textbf{Post-hoc evaluation.} The 63 of 74 correct answers of the revised build on the R7 questions are post-hoc; the blind R8 result (5 of 73) is the relevant estimate for that build. K3 was tuned after K1 failure cases had been inspected.""")

rep("conclusion r8", r"""The post-hoc K3 results improved on the evaluated cases,""",
r"""A revised build that fixed the inspected R7 failures answered 63 of 74 of those questions correctly but only 5 of 73 on a new blind set (R8), with 10 wrong answers among 106; its improvements did not generalize, and on R8 its confidence score was no better than chance at separating correct from wrong answers.

The post-hoc K3 results improved on the evaluated cases,""")

rep("repro r8", r"""Ablation runs, the confidence analysis and a script that recomputes every reported R7 figure are in \texttt{research\_\allowbreak{}improvement/}.""",
r"""Ablation runs, the confidence analysis and a script that recomputes every reported R7 figure are in \texttt{research\_\allowbreak{}improvement/}. The revised build is frozen at \texttt{da925ad}; the R8 questions are in \texttt{evaluation/\allowbreak{}v6\_blind/}, and their protocol, manifest, raw first run (committed before scoring), ablations and analysis are in \texttt{research\_\allowbreak{}improvement/\allowbreak{}accuracy\_\allowbreak{}improvement/}.""")

(H / "InsightFlow_AI_IEEE_Round8.tex").write_text(s)
print(len(LOG), "edits:", ", ".join(LOG))
