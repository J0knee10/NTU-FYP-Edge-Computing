"""Compare two mount-check sessions (e.g. old vs new mount), per duty step and per axis.

usage: python host/analysis/compare_mounts.py <session_a> <session_b>
Needs the window tables (host/analysis/windows.py) for both sessions.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, order_amp, psd  # noqa: E402
from windows import OUT  # noqa: E402


def describe(sd):
    s = Session(sd)
    w = np.load(OUT / f"{s.dir.name}.npz", allow_pickle=True)
    g = s.acc.mean(0)
    out = dict(name=s.dir.name, mount=s.meta.get("mount"), gravity=g, steps={})
    for seg in s.segments:
        m = (w["tc"] > seg["t0"]) & (w["tc"] < seg["t1"]) & w["settled"]
        if m.sum() < 20:
            continue
        rpm = float(np.median(w["rpm"][m]))
        f1 = rpm / 60
        r = dict(rpm=rpm)
        acc = s.slice("imu", seg["t0"], seg["t1"])
        f, p = psd(acc, s.rate["imu"], 4096)
        r["acc1"] = [order_amp(f, p[:, a], f1, 1, tol_hz=0.6) * 1e3 for a in range(3)]
        r["acc05"] = [order_amp(f, p[:, a], f1, 0.5, tol_hz=0.6) * 1e3 for a in range(3)]
        r["acc2"] = [order_amp(f, p[:, a], f1, 2, tol_hz=0.6) * 1e3 for a in range(3)]
        band = (f > 3) & (f < 400)
        r["acc_rms"] = float(np.sqrt(p[band].sum() * (f[1] - f[0])) * 1e3)
        # Share of accel power (3-400 Hz) that sits at rotation orders (0.5x steps, +-0.6 Hz).
        on = np.zeros_like(f, bool)
        for k in np.arange(0.5, 400 / f1, 0.5):
            on |= np.abs(f - k * f1) < 0.6
        pt = p.sum(1)
        r["order_share"] = float(pt[band & on].sum() / pt[band].sum())
        gy = s.slice("gyro", seg["t0"], seg["t1"])
        f, p = psd(gy, s.rate["imu"], 4096)
        r["gyr1"] = [order_amp(f, p[:, a], f1, 1, tol_hz=0.6) for a in range(3)]
        mg = s.slice("mag", seg["t0"], seg["t1"])
        f, p = psd(mg, s.rate["mag"], 1024)
        r["mag2"] = [order_amp(f, p[:, a], f1, 2, tol_hz=3) * 1e3 for a in range(3)]
        r["aud7"] = float(np.nanmedian(20 * np.log10(np.maximum(w["aud_ord"][m, 6], 1e-9))))
        r["acc1_sd"] = float(np.std(np.log10(w["acc_ord"][m, 0])))  # within-step stability
        out["steps"][f"{seg['label']}"] = r
    return out


def fmt(v, p=1):
    return "/".join(f"{x:.{p}f}" for x in v)


A, B = describe(sys.argv[1]), describe(sys.argv[2])
for d in (A, B):
    g = d["gravity"]
    print(f"{d['name']} mount={d['mount']} gravity (g) x/y/z = {fmt(g, 3)}")
print()
cols = ("rpm", "acc 1x x/y/z mg", "acc 0.5x x/y/z mg", "acc 2x x/y/z mg", "acc rms mg", "order share",
        "gyro 1x x/y/z dps", "mag 2x x/y/z mG", "aud 7x dB")
for label in A["steps"]:
    if label not in B["steps"]:
        continue
    print(f"== {label}")
    for d in (A, B):
        r = d["steps"][label]
        print(f"  {d['mount']:>10}: rpm {r['rpm']:6.0f} | acc1 {fmt(r['acc1'])} | acc0.5 {fmt(r['acc05'], 2)} | "
              f"acc2 {fmt(r['acc2'], 2)} | rms {r['acc_rms']:5.1f} | orders {100 * r['order_share']:3.0f}% | "
              f"gyr1 {fmt(r['gyr1'], 2)} | mag2 {fmt(r['mag2'], 0)} | aud7 {r['aud7']:5.1f} | sd {r['acc1_sd']:.3f}")
