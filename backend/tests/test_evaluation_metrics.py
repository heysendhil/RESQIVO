"""Metric calculations used by the evaluation framework."""

import pytest

from app.evaluation.metrics import (
    count_ratio,
    first_relevant_rank,
    ratio,
    recall_at_k,
    reciprocal_rank,
    summarize_ranks,
)


def test_ratio_keeps_numerator_and_denominator():
    assert ratio(1, 3).model_dump() == {
        "numerator": 1,
        "denominator": 3,
        "value": 0.3333,
    }
    assert count_ratio([True, False, True, True]).value == 0.75


def test_empty_ratio_has_no_value():
    assert ratio(0, 0).value is None
    assert count_ratio([]).model_dump() == {
        "numerator": 0,
        "denominator": 0,
        "value": None,
    }


@pytest.mark.parametrize(("n", "d"), [(-1, 2), (3, 2), (0, -1)])
def test_invalid_ratios_are_rejected(n, d):
    with pytest.raises(ValueError):
        ratio(n, d)


def test_recall_at_k():
    ranked = ["a", "b", "c", "d"]

    assert recall_at_k(ranked, {"a"}, 1) == 1.0
    assert recall_at_k(ranked, {"c"}, 1) == 0.0
    assert recall_at_k(ranked, {"b", "d"}, 3) == 0.5
    assert recall_at_k(ranked, {"b", "d"}, 10) == 1.0  # k beyond the list
    assert recall_at_k(ranked, {"z"}, 4) == 0.0


@pytest.mark.parametrize(("relevant", "k"), [(set(), 1), ({"a"}, 0)])
def test_recall_rejects_invalid_input(relevant, k):
    with pytest.raises(ValueError):
        recall_at_k(["a"], relevant, k)


def test_first_relevant_rank_and_reciprocal_rank():
    assert first_relevant_rank(["a", "b", "c"], {"c", "b"}) == 2
    assert first_relevant_rank(["a"], {"z"}) is None
    assert reciprocal_rank(None) == 0.0
    assert reciprocal_rank(4) == 0.25
    with pytest.raises(ValueError):
        reciprocal_rank(0)
    with pytest.raises(ValueError):
        first_relevant_rank(["a"], set())


def test_summarize_ranks():
    metrics = summarize_ranks({"q1": 1, "q2": 3, "q3": None, "q4": 6}, 10)

    assert {k: (r.numerator, r.denominator) for k, r in metrics.recall_at.items()} == {
        "1": (1, 4),
        "3": (2, 4),
        "5": (2, 4),
    }
    assert metrics.mrr == round((1 + 1 / 3 + 0 + 1 / 6) / 4, 4)
    assert metrics.missed_within_cutoff["5"] == ["q3", "q4"]
    assert metrics.missed_within_cutoff["1"] == ["q2", "q3", "q4"]
    assert metrics.not_found_within_depth == ["q3"]


def test_summarize_ranks_on_an_empty_dataset():
    metrics = summarize_ranks({}, 5)

    assert metrics.queries == 0
    assert metrics.mrr is None
    assert all(
        r.value is None and r.denominator == 0 for r in metrics.recall_at.values()
    )


def test_all_misses_score_zero_not_none():
    metrics = summarize_ranks({"q1": None, "q2": None}, 5)

    assert metrics.mrr == 0.0
    assert metrics.recall_at["5"].value == 0.0


@pytest.mark.parametrize(
    ("ranks", "depth", "cutoffs"),
    [
        ({"q": 1}, 3, (1, 5)),  # cutoff beyond retrieved depth
        ({"q": 4}, 3, (1,)),  # rank beyond depth
        ({"q": 0}, 3, (1,)),  # ranks start at 1
        ({"q": 1}, 0, (1,)),
    ],
)
def test_summarize_ranks_rejects_invalid_input(ranks, depth, cutoffs):
    with pytest.raises(ValueError):
        summarize_ranks(ranks, depth, cutoffs)
