import sys
sys.path.insert(0, '.'); sys.path.insert(0, '../../backend')
import fixtures_r5 as FR, baseline_current as B, run_eval as R
if __name__ == "__main__":
    FR.build_h(); FR.build_i(); FR.build_j()
    R.main(sys.argv[1], sys.argv[2], B.register)
