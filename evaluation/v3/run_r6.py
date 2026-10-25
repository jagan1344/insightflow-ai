import sys
sys.path.insert(0, '.'); sys.path.insert(0, '../../backend')
import fixtures_r6 as FR, baseline_current as B, run_eval as R
if __name__ == "__main__":
    FR.build_air(); FR.build_saas(); FR.build_farm()
    R.main(sys.argv[1], sys.argv[2], B.register)
