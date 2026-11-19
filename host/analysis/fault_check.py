"""Compare test session(s) with healthy reference sessions, per duty and per axis.

usage:
  python host/analysis/fault_check.py --ref <session_dir> [...] --test <session_dir> [...]

Uses the window tables under ANALYSIS_OUT (build them with windows.py first). For each duty, it prints:
- the change of the test median vs the reference median (%), and
- how far that is outside the healthy spread, as z = (test - ref) / sd. sd is the larger of the spread
  between reference sessions and 0.02 log10 (about 5 %), so a single reference can't claim false precision.
It also trains an order-feature autoencoder on the reference windows and reports the share of test windows
above the reference 99th-percentile score.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from features.normalise import Normaliser  # noqa: E402
from models.autoencoder import MLPAutoencoder  # noqa: E402

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight"))
L = lambda v: np.log10(np.maximum(v, 1e-9))  # noqa: E731
FEATS = {
    "acc1_x": lambda t: t["acc_1x_axis"][:, 0], "acc1_y": lambda t: t["acc_1x_axis"][:, 1],
    "acc1_z": lambda t: t["acc_1x_axis"][:, 2], "acc1": lambda t: t["acc_ord"][:, 0],
    "acc2": lambda t: t["acc_ord"][:, 1], "gyr1": lambda t: t["gyr_ord"][:, 0],
    "aud7": lambda t: t["aud_ord"][:, 6], "mag2": lambda t: t["mag_ord"][:, 1],
}
SD_FLOOR = 0.02


def load(sd):
    return dict(np.load(OUT / "windows" / f"{Path(sd).name}.npz", allow_pickle=True))


def order_matrix(t):
    """Order-feature vector per window: accel orders 1-9, gyro 1-6, mag 1-3, log rpm.
    (Orders above 9 pass the IMU Nyquist frequency at full speed, so they would be missing there.)"""
    F = np.hstack([L(t["acc_ord"][:, :9]), L(t["gyr_ord"][:, :6]), L(t["mag_ord"][:, :3]),
                   np.log10(np.maximum(t["rpm"], 1))[:, None]])
    return F


def per_session_medians(tabs, d):
    out = {k: [] for k in FEATS}
    for t in tabs:
        m = t["settled"] & (t["pwm"] == d)
        if m.sum() < 20:
            continue
        for k, f in FEATS.items():
            out[k].append(np.nanmedian(L(f(t)[m])))
    return out


ap = argparse.ArgumentParser()
ap.add_argument("--ref", nargs="+", required=True)
ap.add_argument("--test", nargs="+", required=True)
args = ap.parse_args()
ref = [load(s) for s in args.ref]
test = [load(s) for s in args.test]

duties = sorted(set().union(*[set(t["pwm"][t["settled"]]) for t in test]) - {-1})
print(f"reference: {len(ref)} session(s); test: {', '.join(Path(s).name for s in args.test)}")
print("change vs healthy reference, % (z = distance in healthy sd; |z| > 3 is outside healthy spread)")
hdr = "  duty   rpm  " + " ".join(f"{k:>14}" for k in FEATS)
print(hdr)
for d in duties:
    r = per_session_medians(ref, d)
    c = per_session_medians(test, d)
    if not r["acc1"] or not c["acc1"]:
        continue
    rpm = np.median(np.concatenate([t["rpm"][t["settled"] & (t["pwm"] == d)] for t in test]))
    cells = []
    for k in FEATS:
        rm, cm = np.median(r[k]), np.median(c[k])
        sd = max(np.std(r[k]) if len(r[k]) > 1 else 0.0, SD_FLOOR)
        cells.append(f"{100 * (10 ** (cm - rm) - 1):+6.0f}% z{(cm - rm) / sd:+5.1f}")
    print(f"  {d / 10:4.0f}% {rpm:6.0f}  " + " ".join(f"{x:>14}" for x in cells))

# order-feature autoencoder trained on the reference windows
Xr = np.vstack([order_matrix(t)[t["settled"]] for t in ref])
Xr = Xr[np.isfinite(Xr).all(1)]
if len(Xr) > 300:
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(Xr))
    cut = int(0.8 * len(idx))
    norm = Normaliser.fit(Xr[idx[:cut]].astype(np.float32))
    d_in = Xr.shape[1]
    ae = MLPAutoencoder(sizes=(d_in, 16, 8, 16, d_in))
    ae.train(norm(Xr[idx[:cut]].astype(np.float32)), epochs=30)
    thr = np.quantile(ae.score(norm(Xr[idx[cut:]].astype(np.float32))), 0.99)
    print("\norder-feature autoencoder trained on the reference: % of test windows above its 99th-pct threshold "
          "(healthy: about 1 %)")
    for d in duties:
        Xt = np.vstack([order_matrix(t)[t["settled"] & (t["pwm"] == d)] for t in test])
        Xt = Xt[np.isfinite(Xt).all(1)]
        if len(Xt):
            s = ae.score(norm(Xt.astype(np.float32)))
            print(f"  {d / 10:4.0f}%: {100 * (s > thr).mean():5.1f} % of {len(Xt)} windows")
