"""POST-HOC DEVELOPMENT runs on the revealed v5 set (diagnostic, not held out). Same runner logic as
research_improvement/eval/run_v5.py but without the frozen-tree requirement; outputs go to
accuracy_improvement/results/ with the label prefix posthoc_dev_. usage: python run_dev.py <config> <label>"""
import pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))
import run_v5 as R
R.OUT = pathlib.Path(__file__).resolve().parent / "results"
R.check_frozen = lambda: subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=R.ROOT, text=True).strip() + "+worktree"
if __name__ == "__main__":
    R.main(sys.argv[1], "posthoc_dev_" + sys.argv[2])
