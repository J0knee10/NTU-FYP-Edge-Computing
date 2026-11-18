"""The feature specification: everything the C++ port (step 5) must reproduce exactly.

PROVISIONAL. The defaults are a reasonable starting point for 12 V PC fans on the LSM6DS33 at
833 Hz with its 400 Hz anti-alias filter (1x rotation 10-50 Hz, blade-pass up to ~350 Hz). Step 1 fixes them on our own recordings;
see docs/steps/step1_features.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class FeatureSpec:
    window: int = 512        # samples per window; power of 2 for the FFT (0.61 s at 833 Hz)
    hop: int = 512           # samples between window starts (= window: no overlap)
    n_bands: int = 40        # linear bands, ordered low -> high, as one block
    f_lo_hz: float = 2.0     # below this: gravity, DC drift and the sensor's 1/f noise
    f_hi_hz: float = 450.0   # capped at 0.95 x Nyquist for the recording's rate

    @property
    def n_features(self) -> int:
        return self.n_bands + 8

    def band_edges(self, rate_hz: float) -> np.ndarray:
        f_hi = min(self.f_hi_hz, 0.95 * rate_hz / 2)
        return np.linspace(self.f_lo_hz, f_hi, self.n_bands + 1)

    def band_bins(self, rate_hz: float) -> np.ndarray:
        """FFT bin index -> band index (-1 = not in any band). This table goes into the C code."""
        freqs = np.arange(self.window // 2 + 1) * rate_hz / self.window
        edges = self.band_edges(rate_hz)
        band = np.searchsorted(edges, freqs, side="right") - 1
        band[(freqs < edges[0]) | (freqs >= edges[-1])] = -1
        return band

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_SPEC = FeatureSpec()
