"""Leave-one-in configurations B1..B6 (all six safeguards off except one), same frozen tree, data and
scorer as run_v5.py (imported unchanged)."""
import sys
import run_v5 as R

ALL = ["semantic", "confidence_gate", "result_consistency", "plan_fidelity", "mention_coverage", "answer_verifier"]
for i, keep in enumerate(ALL, 1):
    R.CONFIGS[f"B{i}"] = ",".join(c for c in ALL if c != keep)

if __name__ == "__main__":
    R.main(sys.argv[1], sys.argv[2])
