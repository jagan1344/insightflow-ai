"""Held-out generalization regressions: unseen schema (flat upload of
heldout.db) with multi-word, apostrophe, '&', overlapping and unknown
values. Oracle is stdlib sqlite3 on the original multi-table DB."""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.slow
def test_heldout_e2e_all_correct():
    subprocess.run([sys.executable, str(ROOT / "evaluation/v2/build_heldout_dataset.py")],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / "evaluation/v2/heldout_e2e.py")],
                   check=True, capture_output=True)
    import json
    res = json.loads((ROOT / "evaluation/v2/heldout_e2e_results.json").read_text())
    bad = [r["id"] for r in res["results"] if not r.get("exec_ok")]
    assert not bad, bad
