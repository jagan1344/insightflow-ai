import sys
sys.path.insert(0, '.'); sys.path.insert(0, '../../backend')
import fixtures_v4 as F4, baseline_current as B, run_eval as R
if __name__ == "__main__":
    F4.build_d(); F4.build_e()
    if len(sys.argv) > 3: R.FACT.update({})
    R.main(sys.argv[1], sys.argv[2], B.register)
