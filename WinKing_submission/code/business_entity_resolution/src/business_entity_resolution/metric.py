"""Macro-averaged F_0.5 — the exact metric the leaderboard scores against.

Formula (from the problem statement):

    F_β = (1 + β²) · P · R / (β² · P + R),  β = 0.5
        → F_0.5 = 1.25 · P · R / (0.25 · P + R)

Per-entity, then arithmetic mean over **all** Source-1 entities in the evaluation set —
so singletons (empty ground truth) are included in the average:

* gt empty, prediction empty       → **1.0**  (correct "no match")
* gt empty, prediction non-empty   → **0.0**  (false merge on a true singleton)
* gt non-empty, prediction empty   → **0.0**  (recall = 0)

The `beta` argument is left tunable only so unit tests can exercise it; production paths
should call `macro_f05` and treat β = 0.5 as a fixed contract.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def f_beta_per_entity(
    predicted: Iterable[str] | set[str],
    truth: Iterable[str] | set[str],
    *,
    beta: float = 0.5,
) -> float:
    """F_β for one Source-1 entity, with the singleton edge case handled explicitly.

    ``predicted`` and ``truth`` are iterables of Source-2/3 entity ids; duplicates within
    an iterable are ignored (the validator forbids them anyway).
    """
    pred_set = predicted if isinstance(predicted, set) else set(predicted)
    true_set = truth if isinstance(truth, set) else set(truth)

    if not true_set:
        return 1.0 if not pred_set else 0.0
    if not pred_set:
        return 0.0

    tp = len(pred_set & true_set)
    if tp == 0:
        return 0.0

    p = tp / len(pred_set)
    r = tp / len(true_set)
    b2 = beta * beta
    return (1.0 + b2) * p * r / (b2 * p + r)


def macro_f05(
    predictions: Mapping[str, Iterable[str]],
    truth: Mapping[str, Iterable[str]],
) -> float:
    """Macro F_0.5 across every S1 entity in ``truth``.

    An S1 entity present in ``truth`` but absent from ``predictions`` is scored as if it
    had predicted the empty list (a missing row in a real submission is a rejection, but
    at eval time it means "no match predicted").
    """
    if not truth:
        return 0.0
    total = 0.0
    for s1, t in truth.items():
        total += f_beta_per_entity(predictions.get(s1, ()), t, beta=0.5)
    return total / len(truth)


def per_entity_scores(
    predictions: Mapping[str, Iterable[str]],
    truth: Mapping[str, Iterable[str]],
) -> dict[str, float]:
    """One F_0.5 score per S1 entity — for error analysis (NB10)."""
    return {
        s1: f_beta_per_entity(predictions.get(s1, ()), t, beta=0.5)
        for s1, t in truth.items()
    }
