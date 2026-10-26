import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "blind"))
import run_v6 as B
import run_dev as D, run_v5 as R
R.CONFIGS.update(B.CONFIGS)
if __name__ == "__main__":
    R.main(sys.argv[1], "posthoc_dev_" + sys.argv[2])
