"""Discretised agent state (proposal Table 4): 5 x 3 x 4 x 2 = 120 states.

  level        anomaly score / alert threshold: <1, 1-2, 2-4, 4-8, >=8
  trend        slope of the smoothed score over recent windows: falling, flat, rising
  persistence  consecutive windows with level >= 1: 0, 1-2, 3-9, >=10
  context      speed setting changed in the last CONTEXT_HOLD windows: no, yes

Everything here is integer/float arithmetic on a few scalars, cheap to reproduce in C.
"""

from __future__ import annotations

import numpy as np

LEVEL_EDGES = (1.0, 2.0, 4.0, 8.0)
PERSIST_EDGES = (1, 3, 10)
TREND_WINDOW = 8          # windows between the two smoothed-score samples compared
TREND_DEADBAND = 0.25     # change in score/threshold that counts as rising or falling
EMA_ALPHA = 0.3
CONTEXT_HOLD = 20         # windows the context flag stays set after a speed change
SPEED_CHANGE = 0.05       # relative rpm change that counts as a new speed setting

N_LEVEL, N_TREND, N_PERSIST, N_CONTEXT = len(LEVEL_EDGES) + 1, 3, len(PERSIST_EDGES) + 1, 2
N_STATES = N_LEVEL * N_TREND * N_PERSIST * N_CONTEXT


def state_index(level: int, trend: int, persist: int, context: int) -> int:
    return ((level * N_TREND + trend) * N_PERSIST + persist) * N_CONTEXT + context


def decode(index: int) -> tuple[int, int, int, int]:
    index, context = divmod(index, N_CONTEXT)
    index, persist = divmod(index, N_PERSIST)
    level, trend = divmod(index, N_TREND)
    return level, trend, persist, context


class StateEncoder:
    """Turns the stream of (score, rpm) into state indices. One instance per device / episode."""

    def __init__(self, threshold: float):
        self.threshold = float(threshold)
        self.reset()

    def reset(self) -> None:
        self.ema = None
        self.history: list[float] = []
        self.persist = 0
        self.context_timer = 0
        self.speed_ref = None

    def update(self, score: float, rpm: float = float("nan")) -> int:
        ratio = score / self.threshold
        self.ema = ratio if self.ema is None else EMA_ALPHA * ratio + (1 - EMA_ALPHA) * self.ema
        self.history.append(self.ema)
        if len(self.history) > TREND_WINDOW + 1:
            self.history.pop(0)
        self.persist = self.persist + 1 if ratio >= 1.0 else 0

        if np.isfinite(rpm):
            if self.speed_ref is None:
                self.speed_ref = rpm
            elif abs(rpm - self.speed_ref) > SPEED_CHANGE * self.speed_ref:
                self.context_timer = CONTEXT_HOLD
                self.speed_ref = rpm
        context = int(self.context_timer > 0)
        self.context_timer = max(self.context_timer - 1, 0)

        level = int(np.searchsorted(LEVEL_EDGES, ratio, side="right"))
        delta = self.history[-1] - self.history[0]
        trend = 0 if delta < -TREND_DEADBAND else (2 if delta > TREND_DEADBAND else 1)
        persist = int(np.searchsorted(PERSIST_EDGES, self.persist, side="right"))
        self.last = (level, trend, persist, context)
        self.last_ratio = ratio
        return state_index(level, trend, persist, context)
