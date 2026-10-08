"""Step 1: how much each feature separates normal from faulty windows, per source.

    python -m features.report --source fraunhofer
    python -m features.report --source own --window 1024 --bands 32

Prints the single-feature AUROC (0.5 = useless, 1.0 or 0.0 = perfectly separating) for every
feature, the band edges in Hz, and how features vary with speed in normal data. Use it to choose
window length and band edges on our own recordings; the result goes into features/spec.py.
"""

from __future__ import annotations

import argparse

import numpy as np

from models.metrics import auroc

from .extract import Windows, feature_names
from .sets import SOURCES, load_source
from .spec import DEFAULT_SPEC, FeatureSpec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES, default="fraunhofer")
    ap.add_argument("--window", type=int, default=DEFAULT_SPEC.window)
    ap.add_argument("--bands", type=int, default=DEFAULT_SPEC.n_bands)
    ap.add_argument("--f-hi", type=float, default=DEFAULT_SPEC.f_hi_hz)
    a = ap.parse_args()
    spec = FeatureSpec(window=a.window, hop=a.window, n_bands=a.bands, f_hi_hz=a.f_hi)

    w = Windows.concat(list(load_source(a.source, spec).values()))
    edges = spec.band_edges(w.rate_hz)
    print(f"{a.source}: {len(w)} windows at {w.rate_hz:g} Hz; window {spec.window} samples = "
          f"{spec.window / w.rate_hz:.2f} s; FFT bin {w.rate_hz / spec.window:.2f} Hz")
    names = feature_names(spec)
    normal = ~w.fault
    rpm_ok = np.isfinite(w.rpm) & normal
    print(f"{'feature':10s} {'Hz':>13s} {'AUROC':>6s} {'corr_rpm':>8s}  (AUROC: normal vs all faults)")
    for i, name in enumerate(names):
        hz = f"{edges[i]:5.1f}-{edges[i + 1]:5.1f}" if i < spec.n_bands else ""
        auc = auroc(w.X[normal, i], w.X[w.fault, i]) if w.fault.any() else float("nan")
        corr = np.corrcoef(w.X[rpm_ok, i], w.rpm[rpm_ok])[0, 1] if rpm_ok.sum() > 2 else float("nan")
        bar = "#" * int(abs(auc - 0.5) * 40)
        print(f"{name:10s} {hz:>13s} {auc:6.3f} {corr:8.2f}  {bar}")


if __name__ == "__main__":
    main()
