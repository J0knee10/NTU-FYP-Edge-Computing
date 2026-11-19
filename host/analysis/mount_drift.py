"""Did the mount move over the night? Gravity direction per session (and within the last sessions),
rpm per duty per session, and 1x amplitude per axis over time at fixed duty."""
import os
import glob
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight"))  # ANALYSIS_OUT: one results folder per campaign
RAW = Path("data/raw")
names = []
for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
    z = np.load(f, allow_pickle=True)
    if "campaign" in str(z["notes"]):
        names.append(Path(f).stem)

g0 = None
rows = []
gv_t, gv = [], []  # per-minute gravity vector across the night
for n in names:
    z = np.load(RAW / n / "session.npz")
    acc = z["imu_counts"].astype(float) * float(z["imu_g_per_count"])
    w = np.load(OUT / "windows" / f"{n}.npz", allow_pickle=True)
    # per-window mean (gravity), windows of 512
    W = 512
    nw = min(len(acc) // W, len(w["clock"]))
    gm = acc[: nw * W].reshape(nw, W, 3).mean(1)
    g = gm.mean(0)
    if g0 is None:
        g0 = g / np.linalg.norm(g)
    ang = np.degrees(np.arccos(np.clip(np.dot(g / np.linalg.norm(g), g0), -1, 1)))
    # per-minute
    per = int(60 / 0.619)
    for k in range(0, nw - per, per):
        gv_t.append(float(w["clock"][k]))
        gv.append(gm[k:k + per].mean(0))
    rpm = {}
    for d in sorted(set(w["pwm"][w["settled"]]) - {-1}):
        m = w["settled"] & (w["pwm"] == d)
        rpm[int(d)] = float(np.median(w["rpm"][m]))
    rows.append(dict(name=n, profile=str(w["profile"]), start=datetime.fromtimestamp(float(w["clock"][0])).strftime("%H:%M"),
                     g=[round(x, 4) for x in g], tilt_deg_vs_first=round(float(ang), 3), rpm=rpm,
                     temp=float(np.nanmedian(w["temp"]))))

gv = np.array(gv)
gv_t = np.array(gv_t)
gn = gv / np.linalg.norm(gv, axis=1, keepdims=True)
tilt = np.degrees(np.arccos(np.clip(gn @ g0, -1, 1)))
hours = (gv_t - gv_t[0]) / 3600

print(f"{'start':>5} {'profile':>14} {'g (x,y,z)':>28} {'tilt':>6} {'temp':>5}  rpm per duty")
for r in rows:
    print(f"{r['start']:>5} {r['profile']:>14} {str(r['g']):>28} {r['tilt_deg_vs_first']:6.3f} {r['temp']:5.1f}  "
          + " ".join(f"{d // 10}:{v:.0f}" for d, v in r["rpm"].items()))

# 1x per axis over time at 80 % and 70 % duty
fig, ax = plt.subplots(4, 1, figsize=(14, 13), sharex=True)
ax[0].plot(hours, tilt, ".", ms=2)
ax[0].set_ylabel("tilt vs start (deg)")
ax[0].set_title("Gravity direction relative to the first minute (per-minute mean)")
t0 = gv_t[0]
for n in names:
    w = np.load(OUT / "windows" / f"{n}.npz", allow_pickle=True)
    h = (w["clock"] - t0) / 3600
    for d, c in ((800, "C3"), (700, "C0"), (500, "C1")):
        m = w["settled"] & (w["pwm"] == d)
        if m.sum() < 20:
            continue
        for k, a in enumerate(ax[1:]):
            a.plot(h[m], np.log10(w["acc_1x_axis"][m, k]), ".", ms=1, color=c, alpha=0.5)
for k, a in enumerate(ax[1:]):
    a.set_ylabel(f"log10 acc 1x {'xyz'[k]}")
ax[1].plot([], [], ".", color="C3", label="80 %")
ax[1].plot([], [], ".", color="C0", label="70 %")
ax[1].plot([], [], ".", color="C1", label="50 %")
ax[1].legend(markerscale=8, fontsize=8)
ax[-1].set_xlabel("hours since 00:07")
fig.tight_layout()
fig.savefig(OUT / "figs" / "mount_drift.png", dpi=90)
(OUT / "mount_drift.json").write_text(json.dumps(dict(rows=rows, tilt_max_deg=float(tilt.max()),
                                                       tilt_end_deg=float(tilt[-10:].mean())), indent=1))
print("max tilt over night %.3f deg, last 10 min %.3f deg" % (tilt.max(), tilt[-10:].mean()))
# where did tilt change fastest?
d = np.abs(np.diff(tilt))
for i in np.argsort(d)[-6:][::-1]:
    print("  tilt jump %.3f deg at %s" % (d[i], datetime.fromtimestamp(gv_t[i + 1]).strftime("%H:%M")))
