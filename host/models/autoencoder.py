"""MLP autoencoder and the NumPy reference twin of its on-device training step.

Architecture and update rule match firmware/smoke_train/smoke_train.ino (and later the step 5
C++ engine): dense layers, ReLU on hidden layers, linear output, loss = mean squared error over
the D outputs, plain SGD with batch size 1. sgd_step() is the twin: the C++ code must produce
the same weights from the same inputs (to float32 rounding). train() is offline pre-training
only (mini-batches, optional Adam) and never runs on the device.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULT_SIZES = (48, 16, 8, 16, 48)


class MLPAutoencoder:
    def __init__(self, sizes=DEFAULT_SIZES, seed: int = 0):
        self.sizes = tuple(int(s) for s in sizes)
        rng = np.random.default_rng(seed)
        self.W, self.b = [], []
        for n_in, n_out in zip(self.sizes[:-1], self.sizes[1:]):
            limit = np.sqrt(6.0 / n_in)   # He-uniform, as in the firmware
            self.W.append(rng.uniform(-limit, limit, (n_out, n_in)).astype(np.float32))
            self.b.append(np.zeros(n_out, np.float32))

    # ---- inference ---------------------------------------------------------------------------

    def _forward(self, X: np.ndarray) -> list[np.ndarray]:
        """X: (n, D). Returns the activations of every layer, input first."""
        acts = [X.astype(np.float32)]
        last = len(self.W) - 1
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = acts[-1] @ W.T + b
            acts.append(z if i == last else np.maximum(z, 0.0))
        return acts

    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        return self._forward(np.atleast_2d(X))[-1]

    def score(self, X: np.ndarray) -> np.ndarray:
        """Anomaly score per row: mean squared reconstruction error."""
        X = np.atleast_2d(X).astype(np.float32)
        return ((self._forward(X)[-1] - X) ** 2).mean(axis=1)

    # ---- training ----------------------------------------------------------------------------

    def _grads(self, X: np.ndarray):
        acts = self._forward(X)
        n, d = X.shape
        err = acts[-1] - X
        loss = float((err ** 2).mean())
        g = (2.0 / d) * err / n          # dLoss/dOutput, averaged over the batch
        gW, gb = [None] * len(self.W), [None] * len(self.W)
        for i in range(len(self.W) - 1, -1, -1):
            if i < len(self.W) - 1:
                g = g * (acts[i + 1] > 0)  # ReLU mask on this layer's post-activation output
            gW[i] = g.T @ acts[i]
            gb[i] = g.sum(axis=0)
            g = g @ self.W[i]             # uses W before its update, as the firmware does
        return loss, gW, gb

    def sgd_step(self, x: np.ndarray, lr: float) -> float:
        """One on-device training step on one window. Returns the loss before the update."""
        loss, gW, gb = self._grads(np.asarray(x, np.float32).reshape(1, -1))
        for i in range(len(self.W)):
            self.W[i] -= np.float32(lr) * gW[i]
            self.b[i] -= np.float32(lr) * gb[i]
        return loss

    def train(self, X: np.ndarray, epochs: int = 30, lr: float = 1e-3, batch: int = 64,
              optimiser: str = "adam", seed: int = 0) -> list[float]:
        """Offline pre-training. Returns the mean loss per epoch."""
        rng = np.random.default_rng(seed)
        X = X.astype(np.float32)
        params = self.W + self.b
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        t = 0
        history = []
        for _ in range(epochs):
            order = rng.permutation(len(X))
            losses = []
            for k in range(0, len(X), batch):
                loss, gW, gb = self._grads(X[order[k:k + batch]])
                losses.append(loss)
                grads = gW + gb
                t += 1
                for p, g, mi, vi in zip(params, grads, m, v):
                    if optimiser == "adam":
                        mi *= 0.9; mi += 0.1 * g                 # noqa: E702
                        vi *= 0.999; vi += 0.001 * g * g          # noqa: E702
                        p -= lr * (mi / (1 - 0.9 ** t)) / (np.sqrt(vi / (1 - 0.999 ** t)) + 1e-8)
                    else:
                        p -= lr * g
            history.append(float(np.mean(losses)))
        return history

    # ---- weights as one vector (federated learning) and files --------------------------------

    @property
    def n_params(self) -> int:
        return sum(W.size + b.size for W, b in zip(self.W, self.b))

    def get_flat(self) -> np.ndarray:
        return np.concatenate([np.concatenate([W.ravel(), b]) for W, b in zip(self.W, self.b)])

    def set_flat(self, flat: np.ndarray) -> None:
        k = 0
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            self.W[i] = flat[k:k + W.size].reshape(W.shape).astype(np.float32); k += W.size  # noqa: E702
            self.b[i] = flat[k:k + b.size].astype(np.float32); k += b.size                  # noqa: E702

    def copy(self) -> "MLPAutoencoder":
        other = MLPAutoencoder.__new__(MLPAutoencoder)
        other.sizes = self.sizes
        other.W = [W.copy() for W in self.W]
        other.b = [b.copy() for b in self.b]
        return other

    def to_dict(self) -> dict:
        d = {"sizes": np.array(self.sizes)}
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            d[f"W{i}"], d[f"b{i}"] = W, b
        return d

    @classmethod
    def from_dict(cls, d) -> "MLPAutoencoder":
        m = cls.__new__(cls)
        m.sizes = tuple(int(s) for s in d["sizes"])
        m.W = [np.asarray(d[f"W{i}"], np.float32) for i in range(len(m.sizes) - 1)]
        m.b = [np.asarray(d[f"b{i}"], np.float32) for i in range(len(m.sizes) - 1)]
        return m

    # ---- on-device cost (for RQ2 and the step 2 comparison) ----------------------------------

    def device_cost(self) -> dict:
        """float32 RAM for weights, cached activations and gradient buffers; MACs per window."""
        acts = sum(self.sizes)                       # cached inputs/outputs of every layer
        grad_buf = 2 * max(self.sizes)               # dy / dx scratch
        macs_fwd = sum(a * b for a, b in zip(self.sizes[:-1], self.sizes[1:]))
        return {
            "params": self.n_params,
            "ram_bytes": 4 * (self.n_params + acts + grad_buf),
            "macs_inference": macs_fwd,
            "macs_train_step": 3 * macs_fwd,         # forward + dx + dW
        }


def save(path: Path, model: MLPAutoencoder, **extra) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **model.to_dict(), **extra)


def load(path: Path) -> tuple[MLPAutoencoder, dict]:
    d = dict(np.load(path, allow_pickle=False))
    return MLPAutoencoder.from_dict(d), d
