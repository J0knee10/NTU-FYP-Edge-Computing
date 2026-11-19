"""Repeatability of the healthy baseline across the night.

1. Baseline curve (feature median per duty) for every sweep-type session, overlaid.
2. Start vs end mount check: did the tape mount change over the night?
3. Smallest detectable change per feature: sd of an N-window mean, including between-session spread.

usage: python repeatability.py   (reads results/own/overnight/windows, writes figs + repeatability.json)
"""
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
FIG = OUT / "figs"
L = lambda v: np.log10(np.maximum(v, 1e-9))  # noqa: E731

tabs = []
for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
    z = dict(np.load(f, allow_pickle=True))
    if "campaign" not in str(z["notes"]):
        continue
    z["name"] = Path(f).stem
    tabs.append(z)


def feats(t):
    return {
        "acc_1x": L(t["acc_ord"][:, 0]),
        "acc_2x": L(t["acc_ord"][:, 1]),
        "acc_1x_z": L(t["acc_1x_axis"][:, 2]),
        "acc_hf": L(t["acc_hf"]),
        "gyr_1x": L(t["gyr_ord"][:, 0]),
        "mag_2x": L(t["mag_ord"][:, 1]),
        "aud_7x": L(t["aud_ord"][:, 6]),
        "acc_rms": L(np.linalg.norm(t["acc_rms"], axis=1)),
    }


FEATS = list(feats(tabs[0]).keys())
sweeps = [t for t in tabs if str(t["profile"]) in ("mount_check", "speed_sweep")]
res = {"sessions": [], "start_vs_end": {}, "detectable": {}}

# ---- 1. baseline curves per sweep session -------------------------------------
curves = {}  # name -> feature -> {duty: (median, n)}
for t in sweeps:
    F = feats(t)
    c = {}
    for k in FEATS:
        c[k] = {}
        for d in sorted(set(t["pwm"][t["settled"]]) - {-1}):
            m = t["settled"] & (t["pwm"] == d) & np.isfinite(F[k])
            if m.sum() >= 20:
                c[k][int(d)] = (float(np.median(F[k][m])), int(m.sum()))
    curves[str(t["name"])] = c
    clock0 = datetime.fromtimestamp(float(t["clock"][0])).strftime("%H:%M")
    res["sessions"].append(dict(name=str(t["name"]), profile=str(t["profile"]), start=clock0))

fig, axes = plt.subplots(2, 4, figsize=(18, 8))
cm = plt.get_cmap("viridis")
for ax, k in zip(axes.ravel(), FEATS):
    for i, t in enumerate(sweeps):
        c = curves[str(t["name"])][k]
        d = sorted(c)
        lab = datetime.fromtimestamp(float(t["clock"][0])).strftime("%H:%M") + (" mount" if str(t["profile"]) == "mount_check" else "")
        ax.plot([x / 10 for x in d], [c[x][0] for x in d], "o-", ms=3, color=cm(i / max(1, len(sweeps) - 1)), label=lab)
    ax.set_title(f"log10 {k}", fontsize=10)
    ax.set_xlabel("duty %")
    ax.grid(alpha=0.3)
axes[0, 0].legend(fontsize=7)
fig.suptitle("Healthy baseline per sweep across the night (each line = one sweep session)")
fig.tight_layout()
fig.savefig(FIG / "baseline_repeatability.png", dpi=90)
plt.close(fig)

# spread across sweeps per duty
spread = {}
for k in FEATS:
    per_d = {}
    for d in range(300, 1001, 100):
        v = [curves[n][k][d][0] for n in curves if d in curves[n][k]]
        if len(v) >= 3:
            per_d[d] = dict(sd=float(np.std(v)), range=float(np.ptp(v)), n=len(v))
    spread[k] = per_d
res["sweep_spread_log10"] = spread

# ---- 2. start vs end mount check ----------------------------------------------
mc = [t for t in sweeps if str(t["profile"]) == "mount_check"]
if len(mc) >= 2:
    a, b = curves[str(mc[0]["name"])], curves[str(mc[-1]["name"])]
    for k in FEATS:
        res["start_vs_end"][k] = {
            d: round(100 * (10 ** (b[k][d][0] - a[k][d][0]) - 1), 1) for d in sorted(a[k]) if d in b[k]
        }
    # (gravity direction / tilt over the night: see mount_drift.py)

# ---- 3. smallest detectable change ---------------------------------------------
# For each feature and duty: within-session window sd (sw) and between-session sd of session medians (sb).
# An N-window average has sd sqrt(sw^2/N + sb^2). A change is "detectable" if > 3 sd.
allsess = tabs
for k in FEATS:
    rows = {}
    for d in range(300, 1001, 100):
        meds, sds = [], []
        for t in allsess:
            F = feats(t)[k]
            m = t["settled"] & (t["pwm"] == d) & np.isfinite(F)
            if m.sum() >= 30:
                meds.append(np.median(F[m]))
                sds.append(np.std(F[m]))
        if len(meds) < 3:
            continue
        sw, sb = float(np.median(sds)), float(np.std(meds))
        det = {}
        for N in (1, 10, 50, 100):
            sd = np.sqrt(sw ** 2 / N + sb ** 2)
            det[N] = round(100 * (10 ** (3 * sd) - 1), 1)  # % increase needed
        rows[d] = dict(sw=round(sw, 4), sb=round(sb, 4), n_sessions=len(meds), detectable_pct=det)
    res["detectable"][k] = rows

(OUT / "repeatability.json").write_text(json.dumps(res, indent=1))

print("sessions:", [(s["start"], s["profile"]) for s in res["sessions"]])
print("\nsweep-to-sweep sd (log10) per duty:")
for k in FEATS:
    print(f"  {k:>9}: " + "  ".join(f"{d // 10}%:{v['sd']:.3f}" for d, v in spread[k].items()))
print("\nstart vs end mount check, % change of feature (end vs start):")
for k, v in res["start_vs_end"].items():
    print(f"  {k:>9}: " + "  ".join(f"{d // 10}%:{p:+.0f}" for d, p in v.items()))
print("\nsmallest detectable increase (%), 3 sd, averaging N windows (0.62 s each), median over duties:")
for k, rows in res["detectable"].items():
    if not rows:
        continue
    out = []
    for N in (1, 10, 50, 100):
        out.append(f"N={N}: {np.median([r['detectable_pct'][N] for r in rows.values()]):.0f}%")
    sw = np.median([r["sw"] for r in rows.values()])
    sb = np.median([r["sb"] for r in rows.values()])
    print(f"  {k:>9}: sw={sw:.3f} sb={sb:.3f}  " + "  ".join(out))
