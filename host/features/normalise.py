"""Per-feature standardisation. Fitted on pre-training data and shipped to the device with the
model; it stays fixed on the device (only the model adapts, and only when the RL agent allows)."""

from __future__ import annotations

import numpy as np

MIN_STD = 1e-3


class Normaliser:
    def __init__(self, mean: np.ndarray, std: np.ndarray):
        self.mean = np.asarray(mean, np.float32)
        self.std = np.asarray(std, np.float32)

    @classmethod
    def fit(cls, X: np.ndarray) -> "Normaliser":
        return cls(X.mean(axis=0), np.maximum(X.std(axis=0), MIN_STD))

    def __call__(self, X: np.ndarray) -> np.ndarray:
        return ((X - self.mean) / self.std).astype(np.float32)

    def to_dict(self) -> dict:
        return {"norm_mean": self.mean, "norm_std": self.std}

    @classmethod
    def from_dict(cls, d) -> "Normaliser":
        return cls(d["norm_mean"], d["norm_std"])
