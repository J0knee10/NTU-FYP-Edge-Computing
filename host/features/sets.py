"""Standard data splits per source, shared by steps 2-4 so every experiment uses the same data.

    from features.sets import load_source, standard_splits
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fanlog.recording import BOARD_RATE_HZ, load

from .extract import Windows, extract_many
from .spec import DEFAULT_SPEC, FeatureSpec

SOURCES = ("fraunhofer", "uci", "own")


def load_source(source: str, spec: FeatureSpec = DEFAULT_SPEC) -> dict[str, Windows]:
    """Feature windows per group: fraunhofer -> {"D", "E"}; uci, own -> {"all"}."""
    if source == "fraunhofer":
        return {s: extract_many(load("fraunhofer", split=s, rate_hz=BOARD_RATE_HZ), spec) for s in ("D", "E")}
    return {"all": extract_many(load(source), spec)}


@dataclass
class Splits:
    train: Windows        # normal only: pre-training
    val: Windows          # normal only, held out: alert-threshold calibration
    test_same: Windows    # held-out normal + faults, same mount as training
    test_shifted: Windows | None  # normal + faults after re-mounting (None if the source has none)


def time_split(w: Windows, frac: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
    """Split every recording at frac of its length (in time), so train and val never interleave."""
    first = np.zeros(len(w), bool)
    for name in np.unique(w.rec):
        idx = np.flatnonzero(w.rec == name)
        first[idx[: int(len(idx) * frac)]] = True
    return first, ~first


def standard_splits(source: str, spec: FeatureSpec = DEFAULT_SPEC, groups: dict | None = None) -> Splits:
    groups = groups or load_source(source, spec)
    if source == "fraunhofer":
        d, e = groups["D"], groups["E"]
        first, rest = time_split(d.subset(~d.fault))
        normal = d.subset(~d.fault)
        return Splits(normal.subset(first), normal.subset(rest),
                      Windows.concat([normal.subset(rest), d.subset(d.fault)]), e)
    w = groups["all"]
    normal = w.subset(~w.fault)
    first, rest = time_split(normal)
    return Splits(normal.subset(first), normal.subset(rest),
                  Windows.concat([normal.subset(rest), w.subset(w.fault)]), None)
