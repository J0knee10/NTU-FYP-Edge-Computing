"""Non-neural anomaly baselines an examiner will ask about. Same interface: fit(X), score(X).

All are fitted on normal windows only (no fault labels), like the autoencoder.
"""

from __future__ import annotations

import numpy as np


class PCAModel:
    """Reconstruction error after projecting onto the top-k principal components."""

    def __init__(self, k: int = 8):
        self.k = k

    def fit(self, X: np.ndarray) -> "PCAModel":
        self.mean = X.mean(axis=0)
        _, _, vt = np.linalg.svd(X - self.mean, full_matrices=False)
        self.components = vt[: self.k]
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        Z = X - self.mean
        recon = (Z @ self.components.T) @ self.components
        return ((Z - recon) ** 2).mean(axis=1)


class MahalanobisModel:
    """Mahalanobis distance to the normal data, with shrinkage so the covariance is invertible."""

    def __init__(self, shrinkage: float = 0.05):
        self.shrinkage = shrinkage

    def fit(self, X: np.ndarray) -> "MahalanobisModel":
        self.mean = X.mean(axis=0)
        cov = np.cov(X, rowvar=False)
        cov = (1 - self.shrinkage) * cov + self.shrinkage * np.eye(len(cov)) * np.trace(cov) / len(cov)
        self.precision = np.linalg.inv(cov)
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        Z = X - self.mean
        return np.einsum("ij,jk,ik->i", Z, self.precision, Z)


class KMeansModel:
    """Squared distance to the nearest of k cluster centres (Lloyd's algorithm)."""

    def __init__(self, k: int = 16, iters: int = 50, seed: int = 0):
        self.k, self.iters, self.seed = k, iters, seed

    def fit(self, X: np.ndarray) -> "KMeansModel":
        rng = np.random.default_rng(self.seed)
        self.centres = X[rng.choice(len(X), self.k, replace=False)].copy()
        for _ in range(self.iters):
            label = self._dist(X).argmin(axis=1)
            for j in range(self.k):
                if (label == j).any():
                    self.centres[j] = X[label == j].mean(axis=0)
        return self

    def _dist(self, X: np.ndarray) -> np.ndarray:
        return ((X[:, None, :] - self.centres[None]) ** 2).sum(axis=2)

    def score(self, X: np.ndarray) -> np.ndarray:
        return np.concatenate([self._dist(X[i:i + 4096]).min(axis=1) for i in range(0, len(X), 4096)])
