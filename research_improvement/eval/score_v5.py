"""Score raw v5 run files (never modifies them). usage: python score_v5.py <raw.json> [...]"""
import json, math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "evaluation" / "v3"))
from run_eval import score  # same scoring rule as all earlier sealed sets

ANSWER = ("ANSWER", "WARN")


def outcome(r):
    ans = r["action"] in ANSWER
    if r["action"] == "ERROR":
        return "error"
    if r["kind"] == "clarify":
        return "correct_clarify" if not ans else "wrong_answer_to_clarify_item"
    if not ans:
        return "unnecessary_clarify"
    ok, _ = score(r["kind"], [tuple(x) for x in r["rows"]], [tuple(x) for x in (r["expected"] or [])])
    return "correct" if ok else "silent_wrong"


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - w, 3), round(c + w, 3))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def summarize(recs):
    for r in recs:
        r["outcome"] = outcome(r)
    A = [r for r in recs if r["kind"] != "clarify"]
    C = [r for r in recs if r["kind"] == "clarify"]
    cor = sum(r["outcome"] == "correct" for r in A)
    ansA = [r for r in A if r["action"] in ANSWER]
    sw = sum(r["outcome"] == "silent_wrong" for r in A)
    wc = sum(r["outcome"] == "wrong_answer_to_clarify_item" for r in C)
    lat = [r["latency_ms"] for r in recs]
    s = dict(n=len(recs), answerable=len(A), clarify_or_unsupported=len(C),
             correct=cor, correct_rate=round(cor / len(A), 3) if A else None, correct_ci95=wilson(cor, len(A)),
             answered_answerable=len(ansA), coverage=round(len(ansA) / len(A), 3) if A else None,
             accuracy_when_answered=round(cor / len(ansA), 3) if ansA else None,
             accuracy_when_answered_ci95=wilson(cor, len(ansA)),
             silent_wrong_answerable=sw, answered_clarify_items=wc,
             silent_wrong_total=sw + wc, silent_wrong_rate_all=round((sw + wc) / len(recs), 3),
             silent_wrong_ci95=wilson(sw + wc, len(recs)),
             unnecessary_clarify=sum(r["outcome"] == "unnecessary_clarify" for r in A),
             correct_clarify=sum(r["outcome"] == "correct_clarify" for r in C),
             errors=sum(r["outcome"] == "error" for r in recs),
             latency_ms_p50=pct(lat, 50), latency_ms_p95=pct(lat, 95), latency_ms_max=max(lat) if lat else None)
    for ab in ("clarify", "unsupported"):
        sub = [r for r in recs if r["answerability"] == ab]
        s[f"{ab}_items_refused"] = f"{sum(r['action'] not in ANSWER for r in sub)}/{len(sub)}"
    cats = {}
    for r in recs:
        c = cats.setdefault(r["category"], dict(n=0, correct=0, silent_wrong=0, unnecessary_clarify=0,
                                                 correct_clarify=0, wrong_answer_to_clarify_item=0, error=0))
        c["n"] += 1; c[r["outcome"]] += 1
    s["by_category"] = cats
    return s


if __name__ == "__main__":
    for p in sys.argv[1:]:
        d = json.load(open(p))
        s = summarize(d["records"])
        outp = pathlib.Path(p).with_suffix(".summary.json")
        json.dump(dict(source=p, config=d["config"], summary=s,
                       outcomes={r["id"]: r["outcome"] for r in d["records"]}), open(outp, "w"), indent=1)
        print(p, {k: s[k] for k in ("n", "correct", "answerable", "coverage", "accuracy_when_answered",
                                     "silent_wrong_total", "correct_clarify", "clarify_or_unsupported",
                                     "unnecessary_clarify", "errors")})
