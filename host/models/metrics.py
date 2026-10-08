from __future__ import annotations

import numpy as np


def auroc(normal_scores: np.ndarray, fault_scores: np.ndarray) -> float:
    """Probability that a random fault window scores higher than a random normal one (ties = 1/2)."""
    s = np.concatenate([normal_scores, fault_scores])
    order = s.argsort(kind="mergesort")
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks over ties
    _, inverse, counts = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, weights=ranks)
    ranks = (sums / counts)[inverse]
    n0, n1 = len(normal_scores), len(fault_scores)
    return float((ranks[n0:].sum() - n1 * (n1 + 1) / 2) / (n0 * n1))


def threshold_at(normal_scores: np.ndarray, quantile: float = 0.99) -> float:
    """Alert threshold: this quantile of scores on held-out normal windows."""
    return float(np.quantile(normal_scores, quantile))
