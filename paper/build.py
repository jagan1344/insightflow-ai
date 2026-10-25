"""Build paper/insightflow_paper.tex (IEEEtran source) and paper/insightflow_paper_preview.pdf
(HTML two-column preview rendered by Chromium; not official IEEE typesetting)."""
import html, pathlib, re, shutil, subprocess
import content as C

H = pathlib.Path(__file__).resolve().parent
FIG = H.parents[0] / "research_improvement" / "figures"
(H / "figures").mkdir(exist_ok=True)
for f in FIG.glob("fig*.*"):
    if f.suffix in (".pdf", ".svg"):
        shutil.copy(f, H / "figures" / f.name)
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]


def tex_esc(s):
    s = s.replace("\\", r"\textbackslash{}")
    for a, b in [("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#"), ("$", r"\$"), ("{", r"\{"), ("}", r"\}")]:
        s = s.replace(a, b)
    s = re.sub(r"(\d)-(\d)", r"\1--\2", s)
    s = re.sub(r'"([^"]*)"', r"``\1''", s)
    s = s.replace(">=", r"$\geq$").replace("<=", r"$\leq$")
    s = re.sub(r"\[(\d+)\]", r"\\cite{r\1}", s)
    s = re.sub(r"\\\{(fig[\w\\]+)\\\}", lambda m: "\\ref{" + m.group(1).replace("\\_", "_") + "}", s)
    return s


def build_tex():
    o = [r"\documentclass[conference]{IEEEtran}", r"\usepackage{graphicx}", r"\usepackage{booktabs}",
         r"\usepackage{cite}", r"\begin{document}", r"\title{" + tex_esc(C.TITLE) + "}",
         r"\author{\IEEEauthorblockN{" + tex_esc(C.AUTHORS) + "}}", r"\maketitle",
         r"\begin{abstract}" + tex_esc(C.ABSTRACT) + r"\end{abstract}",
         r"\begin{IEEEkeywords}" + tex_esc(C.KEYWORDS) + r"\end{IEEEkeywords}"]
    for title, blocks in C.SECTIONS:
        o.append(r"\section{" + tex_esc(title) + "}")
        for b in blocks:
            if b[0] == "p":
                o.append(tex_esc(b[1]) + "\n")
            elif b[0] == "ul":
                o.append(r"\begin{itemize}" + "".join(r"\item " + tex_esc(x) for x in b[1]) + r"\end{itemize}")
            elif b[0] == "fig":
                env = "figure*" if b[3] else "figure"
                w = r"\textwidth" if b[3] else r"\columnwidth"
                o.append(rf"\begin{{{env}}}[t]\centering\includegraphics[width={w}]{{figures/{b[1]}.pdf}}"
                         rf"\caption{{{tex_esc(b[2])}}}\label{{{b[1]}}}\end{{{env}}}")
            elif b[0] == "table":
                cols = "l" + "r" * (len(b[2]) - 1)
                body = " \\\\\n".join(" & ".join(tex_esc(c) for c in r) for r in b[3])
                o.append(r"\begin{table}[t]\centering\caption{" + tex_esc(b[1]) + r"}\footnotesize"
                         r"\begin{tabular}{" + cols + r"}\toprule " + " & ".join(tex_esc(c) for c in b[2]) +
                         r" \\\midrule " + body + r" \\\bottomrule\end{tabular}\end{table}")
    o.append(r"\section*{Disclosure}" + tex_esc(C.DISCLOSURE))
    o.append(r"\begin{thebibliography}{99}" + "".join(
        rf"\bibitem{{r{i}}} " + tex_esc(r) + "\n" for i, r in enumerate(C.REFERENCES, 1)) + r"\end{thebibliography}")
    o.append(r"\end{document}")
    (H / "insightflow_paper.tex").write_text("\n".join(o))


def build_html():
    figno, tabno = {}, {}
    order = [b[1] for _, bl in C.SECTIONS for b in bl if b[0] == "fig"]
    num = {k: i + 1 for i, k in enumerate(order)}
    sub = lambda t: re.sub(r"\{(fig\w+)\}", lambda m: str(num[m.group(1)]), t)
    css = """@page{size:Letter;margin:0.75in 0.625in}body{font-family:'Times New Roman',Times,serif;font-size:9.5pt;line-height:1.18;color:#000;background:#fff}
h1{font-size:20pt;text-align:center;font-weight:normal;margin:0 0 6pt}.auth{text-align:center;font-size:10pt;margin-bottom:12pt}
.cols{column-count:2;column-gap:0.25in;text-align:justify}.abs{font-weight:bold;font-size:9pt}
h2{font-size:9.5pt;font-variant:small-caps;text-align:center;font-weight:normal;margin:8pt 0 4pt;break-after:avoid}
p{margin:0 0 4pt;text-indent:1em}figure{margin:4pt 0;break-inside:avoid;text-align:center}figure img{width:100%}
figure.wide{column-span:all}figcaption{font-size:8pt;text-align:left}table{border-collapse:collapse;font-size:7.6pt;margin:3pt auto;break-inside:avoid}
td,th{padding:1pt 4pt;border-bottom:0.4pt solid #888;text-align:right}td:first-child,th:first-child{text-align:left}
.tcap{font-size:8pt;text-align:center;font-variant:small-caps;margin-top:6pt}ol.ref{font-size:7.8pt;padding-left:16pt}ul{margin:0 0 4pt 0;padding-left:14pt}
.disc{font-size:8pt;font-style:italic}.tblock{break-inside:avoid}ol.ref{list-style:none;counter-reset:r}ol.ref li{counter-increment:r;position:relative}ol.ref li::before{content:'[' counter(r) ']';position:absolute;left:-18pt}"""
    o = [f"<!doctype html><html><head><meta charset='utf-8'><title>InsightFlow AI manuscript</title><style>{css}</style></head><body>",
         f"<h1>{html.escape(C.TITLE)}</h1><div class='auth'>{html.escape(C.AUTHORS)}</div><div class='cols'>",
         f"<p class='abs'><i>Abstract</i>&mdash;{html.escape(C.ABSTRACT)}</p>",
         f"<p class='abs'><i>Index Terms</i>&mdash;{html.escape(C.KEYWORDS)}</p>"]
    for i, (title, blocks) in enumerate(C.SECTIONS):
        o.append(f"<h2>{ROMAN[i]}. {html.escape(title)}</h2>")
        for b in blocks:
            if b[0] == "p":
                o.append(f"<p>{html.escape(sub(b[1]))}</p>")
            elif b[0] == "ul":
                o.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in b[1]) + "</ul>")
            elif b[0] == "fig":
                figno[b[1]] = len(figno) + 1
                o.append(f"<figure class='{'wide' if b[3] else ''}'><img src='figures/{b[1]}.svg'>"
                         f"<figcaption>Fig. {figno[b[1]]}. {html.escape(b[2])}</figcaption></figure>")
            elif b[0] == "table":
                tabno[b[1]] = len(tabno) + 1
                o.append(f"<div class='tblock'><div class='tcap'>Table {ROMAN[tabno[b[1]] - 1]}<br>{html.escape(b[1])}</div><table><tr>" +
                         "".join(f"<th>{html.escape(c)}</th>" for c in b[2]) + "</tr>" +
                         "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in b[3]) + "</table></div>")
    o.append(f"<h2>Disclosure</h2><p class='disc'>{html.escape(C.DISCLOSURE)}</p>")
    o.append("<h2>References</h2><ol class='ref'>" + "".join(f"<li>{html.escape(r)}</li>" for r in C.REFERENCES) + "</ol>")
    o.append("</div></body></html>")
    (H / "insightflow_paper.html").write_text("\n".join(o))
    return figno


if __name__ == "__main__":
    build_tex(); figno = build_html()
    js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage();"
          f"await p.goto('file://{H}/insightflow_paper.html');await p.waitForLoadState('networkidle');"
          f"await p.pdf({{path:'{H}/insightflow_paper_preview.pdf',format:'Letter',printBackground:true}});await b.close()}})()")
    subprocess.run(["node", "-e", js], check=True)
    print("figure numbering:", figno)
