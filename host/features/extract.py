"""Window a Recording and compute one feature vector per window.

Per window (all three axes, each with its own mean removed):
  0..n_bands-1   log10 band power, power summed over the 3 axes (Hann window, real FFT)
  then           log10 RMS per axis (3), kurtosis per axis (3), crest factor of the vector
                 magnitude (1), spectral centroid / f_hi (1)

Only operations that CMSIS-DSP has (arm_rfft_fast_f32, sums, sqrt, log10), so the C++ port can
match this within float32 rounding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fanlog.recording import REPO_ROOT, Recording

from .spec import DEFAULT_SPEC, FeatureSpec

EPS = 1e-12
CACHE = REPO_ROOT / "data" / "processed" / "features"
STAT_NAMES = ["log_rms_x", "log_rms_y", "log_rms_z", "kurt_x", "kurt_y", "kurt_z", "crest", "centroid"]


def feature_names(spec: FeatureSpec = DEFAULT_SPEC) -> list[str]:
    return [f"band{i:02d}" for i in range(spec.n_bands)] + STAT_NAMES


FEATURE_NAMES = feature_names()


@dataclass
class Windows:
    """Feature vectors of one or more recordings, with per-window labels."""

    X: np.ndarray            # (n, n_features) float32
    rpm: np.ndarray          # (n,) mean speed in the window (nan if unknown)
    fault: np.ndarray        # (n,) bool
    severity: np.ndarray     # (n,) int
    rec: np.ndarray          # (n,) recording name
    fan: np.ndarray          # (n,) fan / mount id
    start: np.ndarray        # (n,) first sample index within its recording
    rate_hz: float = float("nan")
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.X)

    def subset(self, mask) -> "Windows":
        mask = np.asarray(mask)
        return Windows(self.X[mask], self.rpm[mask], self.fault[mask], self.severity[mask],
                       self.rec[mask], self.fan[mask], self.start[mask], self.rate_hz, self.meta)

    @staticmethod
    def concat(parts: list["Windows"]) -> "Windows":
        rates = {p.rate_hz for p in parts}
        if len(rates) > 1:
            raise ValueError(f"cannot mix sample rates {rates}; resample first")
        cat = lambda a: np.concatenate([getattr(p, a) for p in parts])  # noqa: E731
        return Windows(cat("X"), cat("rpm"), cat("fault"), cat("severity"), cat("rec"), cat("fan"),
                       cat("start"), parts[0].rate_hz)


def window_features(frames: np.ndarray, rate_hz: float, spec: FeatureSpec = DEFAULT_SPEC) -> np.ndarray:
    """frames: (n, window, 3) raw samples -> (n, n_features) float32."""
    n, w, _ = frames.shape
    assert w == spec.window
    x = frames.astype(np.float64)
    x = x - x.mean(axis=1, keepdims=True)

    power = np.abs(np.fft.rfft(x * np.hanning(w)[None, :, None], axis=1)) ** 2   # (n, bins, 3)
    power = power.sum(axis=2)                                                      # (n, bins)
    bins = spec.band_bins(rate_hz)
    bands = np.zeros((n, spec.n_bands))
    for b in range(spec.n_bands):
        sel = bins == b
        if sel.any():
            bands[:, b] = power[:, sel].sum(axis=1)

    var = (x ** 2).mean(axis=1)                                   # (n, 3)
    rms = np.sqrt(var)
    kurt = (x ** 4).mean(axis=1) / (var ** 2 + EPS)
    mag = np.sqrt((x ** 2).sum(axis=2))                           # (n, w)
    crest = mag.max(axis=1) / (np.sqrt((mag ** 2).mean(axis=1)) + EPS)
    freqs = np.arange(w // 2 + 1) * rate_hz / w
    in_band = bins >= 0
    p_in = power[:, in_band]
    centroid = (p_in * freqs[in_band]).sum(axis=1) / (p_in.sum(axis=1) + EPS) / spec.band_edges(rate_hz)[-1]

    out = np.concatenate([np.log10(bands + EPS), np.log10(rms + EPS), kurt, crest[:, None], centroid[:, None]],
                         axis=1)
    return out.astype(np.float32)


def extract(rec: Recording, spec: FeatureSpec = DEFAULT_SPEC, cache: bool = True) -> Windows:
    """All complete windows of one recording."""
    path = _cache_path(rec, spec)
    cache = cache and rec.source != "own"
    if cache and path.exists():
        z = np.load(path)
        X, rpm, start = z["X"], z["rpm"], z["start"]
    else:
        starts = np.arange(0, len(rec.acc) - spec.window + 1, spec.hop)
        X = np.zeros((len(starts), spec.n_features), np.float32)
        for i in range(0, len(starts), 2048):   # chunked to bound memory
            s = starts[i:i + 2048]
            frames = np.stack([rec.acc[k:k + spec.window] for k in s])
            X[i:i + len(s)] = window_features(frames, rec.rate_hz, spec)
        if rec.rpm is not None:
            csum = np.concatenate([[0.0], np.cumsum(rec.rpm, dtype=np.float64)])
            rpm = ((csum[starts + spec.window] - csum[starts]) / spec.window).astype(np.float32)
        else:
            rpm = np.full(len(starts), np.nan, np.float32)
        start = starts
        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, X=X, rpm=rpm, start=start)
    n = len(X)
    return Windows(
        X=X, rpm=rpm, fault=np.full(n, rec.is_fault), severity=np.full(n, rec.severity),
        rec=np.full(n, rec.name, dtype=object), fan=np.full(n, rec.fan, dtype=object),
        start=start, rate_hz=rec.rate_hz,
    )


def extract_many(recs: list[Recording], spec: FeatureSpec = DEFAULT_SPEC, cache: bool = True) -> Windows:
    return Windows.concat([extract(r, spec, cache) for r in recs])


def _cache_path(rec: Recording, spec: FeatureSpec) -> Path:
    # Only public datasets are cached: they never change. Own sessions are cheap to recompute.
    key = json.dumps({"spec": spec.to_dict(), "rate": rec.rate_hz, "n": len(rec.acc), "v": 3}, sort_keys=True)
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    return CACHE / f"{rec.source}_{rec.name}_{digest}.npz"
