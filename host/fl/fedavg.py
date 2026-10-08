"""Server-side aggregation and the update format sent over BLE (proposal 7.6)."""

from __future__ import annotations

import numpy as np


def fedavg(flats: list[np.ndarray], counts: list[int]) -> np.ndarray | None:
    """Weighted FedAvg; weight = number of windows each client trained on (approved ADAPTs).
    Returns None if nobody trained this round (the global model stays as it was)."""
    counts = np.asarray(counts, np.float64)
    if counts.sum() == 0:
        return None
    return (np.stack(flats).astype(np.float64) * (counts / counts.sum())[:, None]).sum(axis=0).astype(np.float32)


def blend(local: np.ndarray, global_: np.ndarray, beta: float) -> np.ndarray:
    """Personalisation: keep (1 - beta) of the local weights."""
    return (beta * global_ + (1 - beta) * local).astype(np.float32)


def quantise_int8(flat: np.ndarray) -> tuple[np.ndarray, np.float32]:
    """Symmetric int8 with one float32 scale for the whole vector."""
    scale = np.float32(max(float(np.abs(flat).max()), 1e-12) / 127)
    return np.clip(np.round(flat / scale), -127, 127).astype(np.int8), scale


def dequantise_int8(q: np.ndarray, scale: np.float32) -> np.ndarray:
    return q.astype(np.float32) * scale


def update_bytes(n_params: int, int8: bool = True) -> int:
    """Payload of one model upload or download (weights + scale), before BLE framing."""
    return n_params + 4 if int8 else 4 * n_params
