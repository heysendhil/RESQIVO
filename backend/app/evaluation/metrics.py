"""Reusable evaluation metrics. Every ratio keeps its numerator and denominator,
and a zero denominator gives a value of None rather than a misleading 0 or 1."""

from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel


class Ratio(BaseModel):
    numerator: int
    denominator: int
    value: float | None


def ratio(numerator: int, denominator: int) -> Ratio:
    if denominator < 0 or numerator < 0 or numerator > denominator:
        raise ValueError("Ratio needs 0 <= numerator <= denominator.")
    value = round(numerator / denominator, 4) if denominator else None
    return Ratio(numerator=numerator, denominator=denominator, value=value)


def count_ratio(flags: Iterable[bool]) -> Ratio:
    values = list(flags)
    return ratio(sum(values), len(values))


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of the relevant items found in the first k results."""
    if k < 1:
        raise ValueError("k must be at least 1.")
    if not relevant_ids:
        raise ValueError("A query needs at least one relevant item.")
    return len(relevant_ids & set(ranked_ids[:k])) / len(relevant_ids)


def first_relevant_rank(
    ranked_ids: Sequence[str], relevant_ids: set[str]
) -> int | None:
    if not relevant_ids:
        raise ValueError("A query needs at least one relevant item.")
    return next(
        (rank for rank, item in enumerate(ranked_ids, 1) if item in relevant_ids),
        None,
    )


def reciprocal_rank(rank: int | None) -> float:
    if rank is None:
        return 0.0
    if rank < 1:
        raise ValueError("Ranks start at 1.")
    return 1.0 / rank


class RetrievalMetrics(BaseModel):
    """Hit-based metrics for queries with one relevance target, from the rank of
    the first relevant result (None if not retrieved within depth). With one
    relevant item per query, Recall@k equals the hit rate at k."""

    queries: int
    retrieval_depth: int
    recall_at: dict[str, Ratio]
    mrr: float | None
    missed_within_cutoff: dict[str, list[str]]
    not_found_within_depth: list[str]


def summarize_ranks(
    ranks: Mapping[str, int | None],
    retrieval_depth: int,
    cutoffs: Sequence[int] = (1, 3, 5),
) -> RetrievalMetrics:
    if retrieval_depth < 1:
        raise ValueError("retrieval_depth must be at least 1.")
    if any(k < 1 or k > retrieval_depth for k in cutoffs):
        raise ValueError("Cutoffs must be between 1 and the retrieval depth.")
    for query_id, rank in ranks.items():
        if rank is not None and not 1 <= rank <= retrieval_depth:
            raise ValueError(f"{query_id}: rank outside 1..retrieval_depth.")
    n = len(ranks)
    return RetrievalMetrics(
        queries=n,
        retrieval_depth=retrieval_depth,
        recall_at={
            str(k): count_ratio(r is not None and r <= k for r in ranks.values())
            for k in cutoffs
        },
        mrr=round(sum(reciprocal_rank(r) for r in ranks.values()) / n, 4)
        if n
        else None,
        missed_within_cutoff={
            str(k): sorted(q for q, r in ranks.items() if r is None or r > k)
            for k in cutoffs
        },
        not_found_within_depth=sorted(q for q, r in ranks.items() if r is None),
    )
