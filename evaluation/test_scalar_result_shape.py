"""Regression tests: a scalar oracle must not accept extra result data."""

from evaluation.run_paper_eval import _matches_oracle


def test_scalar_exact_shape_matches():
    assert _matches_oracle([[42]], [[42]])


def test_scalar_extra_rows_do_not_match():
    assert not _matches_oracle([[42], [99]], [[42]])


def test_scalar_extra_columns_do_not_match():
    assert not _matches_oracle([["wrong metric", 42]], [[42]])


def test_scalar_wrong_value_does_not_match():
    assert not _matches_oracle([[41]], [[42]])
