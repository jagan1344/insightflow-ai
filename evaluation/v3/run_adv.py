import sys, sqlite3
sys.path.insert(0, '.'); sys.path.insert(0, '../../backend')
import baseline_current as B, run_eval as R
if __name__ == "__main__":
    B.F.build_a(); B.F.build_b()
    R.main("adversarial", sys.argv[1], B.register)
