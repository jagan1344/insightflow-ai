import sys
sys.path.insert(0, '.'); sys.path.insert(0, '../../backend')
import fixtures_f as FF, baseline_current as B, run_eval as R
if __name__ == "__main__":
    FF.build_f()
    R.main(sys.argv[1], sys.argv[2], B.register)
