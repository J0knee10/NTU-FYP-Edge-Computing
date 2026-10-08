"""Build simulator episodes (proposal Table 8) by splicing recorded windows.

  S1  benign drift: normal at speed A, then normal at speed B (and maybe C)    -> ADAPT, no alert
  S2  gradual fault: normal at A, then severity 1, 2, 3, ... at A              -> FREEZE, then ALERT
  S3  sudden fault: normal at A, then a severe fault at A                      -> ALERT quickly
  S1+S3: speed change first, then a fault at the new speed                     -> ADAPT, then ALERT

Every episode starts with a learning period (proposal 7.4, "stick-on-and-learn"): `learn` normal
windows at the first speed, during which the device always adapts and then sets its own threshold.
The agent acts only after it.

Segments are contiguous runs of windows from one recording, so the natural slow drift inside a
recording (e.g. the 20 s speed steps of the Fraunhofer data) is kept. All segments of one episode
come from one fan (one machine + mount), so a client never sees another machine's data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from features.extract import Windows

SCENARIOS = ("S1", "S2", "S3", "S1+S3")
RPM_BAND = 0.04   # a segment starts within +-4 % of its target speed


@dataclass
class Episode:
    X: np.ndarray          # (T, D) normalised features
    rpm: np.ndarray        # (T,)
    fault: np.ndarray      # (T,) bool
    severity: np.ndarray   # (T,) int
    scenario: str
    fan: str
    learn: int = 0          # leading windows that form the learning period

    @property
    def onset(self) -> int | None:
        idx = np.flatnonzero(self.fault[self.learn:]) + self.learn
        return int(idx[0]) if len(idx) else None

    def __len__(self) -> int:
        return len(self.X)


class EpisodeBuilder:
    def __init__(self, windows: Windows, normalise, seed: int = 0,
                 normal_len=(100, 250), drift_len=(150, 300), step_len=(40, 100), fault_len=(100, 200),
                 learn_len: int = 300):
        self.w = windows
        self.Xn = normalise(windows.X)
        self.rng = np.random.default_rng(seed)
        self.normal_len, self.drift_len, self.step_len, self.fault_len = normal_len, drift_len, step_len, fault_len
        self.learn_len = learn_len
        # time-ordered window indices per recording
        self.by_rec = {r: np.flatnonzero(windows.rec == r)[np.argsort(windows.start[windows.rec == r])]
                       for r in np.unique(windows.rec)}
        self.fans = sorted(set(windows.fan))
        self.fault_fans = [f for f in self.fans if (windows.fault & (windows.fan == f)).any()]

    # ---- segments -----------------------------------------------------------------------------

    def _recs(self, fan: str, severity: int) -> list[str]:
        m = (self.w.fan == fan) & (self.w.severity == severity)
        return sorted(set(self.w.rec[m]))

    def segment(self, fan: str, severity: int, rpm: float, length: int) -> np.ndarray:
        """Indices of `length` consecutive windows of one recording, starting near `rpm`."""
        rec = self.rng.choice(self._recs(fan, severity))
        idx = self.by_rec[rec]
        speed = self.w.rpm[idx]
        if np.isfinite(rpm) and np.isfinite(speed).any():
            near = np.flatnonzero(np.abs(speed - rpm) <= RPM_BAND * rpm)
            if not len(near):
                near = np.array([np.nanargmin(np.abs(speed - rpm))])
            pos = int(self.rng.choice(near))
        else:
            pos = int(self.rng.integers(0, max(len(idx) - length, 1)))
        pos = min(pos, max(len(idx) - length, 0))
        return idx[pos:pos + length]

    def speed_range(self, fan: str) -> tuple[float, float]:
        rpm = self.w.rpm[(self.w.fan == fan) & ~self.w.fault]
        rpm = rpm[np.isfinite(rpm)]
        return (np.percentile(rpm, 5), np.percentile(rpm, 95)) if len(rpm) else (np.nan, np.nan)

    def _two_speeds(self, fan: str) -> tuple[float, float]:
        lo, hi = self.speed_range(fan)
        if not np.isfinite(lo):
            return np.nan, np.nan
        a = self.rng.uniform(lo, hi)
        far = [x for x in self.rng.uniform(lo, hi, 50) if abs(x - a) > 0.25 * (hi - lo)]
        return a, (far[0] if far else hi if a < (lo + hi) / 2 else lo)

    def _len(self, rng_pair) -> int:
        return int(self.rng.integers(*rng_pair))

    def _severities(self, fan: str) -> list[int]:
        return sorted({int(s) for s in self.w.severity[(self.w.fan == fan) & self.w.fault]})

    # ---- scenarios ----------------------------------------------------------------------------

    def build(self, scenario: str | None = None) -> Episode:
        scenario = scenario or str(self.rng.choice(SCENARIOS))
        fans = self.fans if scenario == "S1" else self.fault_fans
        fan = str(self.rng.choice(fans))
        a, b = self._two_speeds(fan)
        learn = self.segment(fan, 0, a, self.learn_len + self._len(self.normal_len)) if self.learn_len else None
        parts = [learn if learn is not None else self.segment(fan, 0, a, self._len(self.normal_len))]
        if scenario == "S1":
            parts.append(self.segment(fan, 0, b, self._len(self.drift_len)))
            if self.rng.random() < 0.5:
                parts.append(self.segment(fan, 0, a, self._len(self.drift_len)))
        elif scenario == "S2":
            for sev in self._severities(fan):
                parts.append(self.segment(fan, sev, a, self._len(self.step_len)))
        elif scenario == "S3":
            sev = max(self._severities(fan))
            parts.append(self.segment(fan, sev, a, self._len(self.fault_len)))
        elif scenario == "S1+S3":
            parts.append(self.segment(fan, 0, b, self._len(self.drift_len)))
            sev = int(self.rng.choice(self._severities(fan)[1:] or self._severities(fan)))
            parts.append(self.segment(fan, sev, b, self._len(self.fault_len)))
        else:
            raise ValueError(scenario)
        return self.from_segments(parts, scenario, fan, min(self.learn_len, len(parts[0]) // 2))

    def from_segments(self, parts: list[np.ndarray], scenario: str, fan: str, learn: int = 0) -> Episode:
        idx = np.concatenate(parts)
        return Episode(self.Xn[idx], self.w.rpm[idx], self.w.fault[idx], self.w.severity[idx], scenario, fan, learn)

    def batch(self, n: int, scenarios=SCENARIOS) -> list[Episode]:
        return [self.build(scenarios[i % len(scenarios)]) for i in range(n)]
