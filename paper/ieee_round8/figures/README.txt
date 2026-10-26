Figure sources (editable TikZ / PGFPlots, Times font, grayscale, drawn at final IEEE print width)
  src/common.tex                 shared styles (included by every figure)
  src/fig_architecture.tex       Fig. 1  (double column)
  src/fig_semantic_workflow.tex  Fig. 2  (single column)
  src/fig_k1_k3.tex              Fig. 3  (single column; plots data/round6_k1_k3.csv values)
  src/fig_a17_trace.tex          Fig. 4  (single column)
Rebuild: cd figures/src && for f in fig_*.tex; do pdflatex "$f"; done && cp fig_*.pdf ..
The manuscript includes the compiled PDFs from figures/ with \includegraphics.
Round 7 addition:
  src/fig_r7_ablation.tex        Fig. 5  (single column; data/round7_ablation.csv)
  fig_r7_ablation.pdf was rendered by make_r7_figures.py (matplotlib, Liberation Serif = Times metrics,
  grayscale) because no TeX installation was available; rebuild from src/ with pdflatex to match the others.
