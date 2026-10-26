"""Scorer for the v6 blind set: identical rules to research_improvement/eval/score_v5.py (imported), with
the v6 percentage items and the authoring agent's borderline list fixed BEFORE the first run.
usage: python score_v6.py <raw.json> [...]"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "eval"))
import score_v5 as S
S.PERCENT_IDS = {"FD16", "LS16", "TC15", "WH17"}
S.BORDERLINE_IDS = {"FD19", "FD02", "FD07", "FD18", "TC17", "WH19", "LS18", "LS01", "LS07", "LS17", "LS13", "LS23",
                    "TC05", "TC13", "TC20", "WH14", "WH16", "WH17", "FD25", "LS25", "TC26", "WH26", "TC24", "TC25"}
outcome, summarize, wilson = S.outcome, S.summarize, S.wilson
BORDERLINE_IDS = S.BORDERLINE_IDS

if __name__ == "__main__":
    for p in sys.argv[1:]:
        d = json.load(open(p))
        s = summarize(d["records"])
        b = summarize([r for r in d["records"] if r["id"] not in BORDERLINE_IDS])
        outp = pathlib.Path(p).with_suffix(".summary.json")
        json.dump(dict(source=p, config=d["config"], summary=s, sensitivity_without_borderline=b,
                       outcomes={r["id"]: r["outcome"] for r in d["records"]}), open(outp, "w"), indent=1)
        print(p, {k: s[k] for k in ("n", "correct", "answerable", "answered_answerable", "silent_wrong_total",
                                     "correct_clarify", "clarify_or_unsupported", "unnecessary_clarify", "errors")})
