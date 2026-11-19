"""Clean figures for the overnight report (results/own/overnight/figs/report_*.png)."""
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, psd  # noqa: E402

OUT = Path("results/own/overnight")
FIG = OUT / "figs"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"  # categorical slots 1-3
TIME = LinearSegmentedColormap.from_list("time", ["#b9d6f7", "#2a78d6", "#0c2f5c"])  # one hue, light -> dark
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
})
dB = lambda v: 20 * np.log10(np.maximum(v, 1e-12))  # noqa: E731

tabs = []
for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
    z = dict(np.load(f, allow_pickle=True))
    if "campaign" in str(z["notes"]):
        z["name"] = Path(f).stem
        tabs.append(z)
cat = lambda k: np.concatenate([t[k] for t in tabs])  # noqa: E731
rpm, settled, clock, pwm = cat("rpm"), cat("settled"), cat("clock"), cat("pwm")
hours = (clock - clock.min()) / 3600
acc_ord, gyr_ord, mag_ord, aud_ord, acc_hf = cat("acc_ord"), cat("gyr_ord"), cat("mag_ord"), cat("aud_ord"), cat("acc_hf")

# ---- 1. key features vs speed --------------------------------------------------
feats = [
    ("Accel 1x (dB re 1 g)", acc_ord[:, 0]), ("Gyro 1x (dB re 1 dps)", gyr_ord[:, 0]),
    ("Magnetometer 2x, electrical (dB re 1 G)", mag_ord[:, 1]), ("Audio 7x, blade pass (dB re 1 count)", aud_ord[:, 6]),
    ("Accel 2x (dB re 1 g)", acc_ord[:, 1]), ("Accel 150-400 Hz rms (dB re 1 g)", acc_hf),
]
fig, axes = plt.subplots(2, 3, figsize=(15, 8.5))
order = np.argsort(hours)
for ax, (title, v) in zip(axes.ravel(), feats):
    m = settled[order] & np.isfinite(v[order]) & np.isfinite(rpm[order]) & (rpm[order] > 300)
    sc = ax.scatter(rpm[order][m], dB(v[order][m]), c=hours[order][m], cmap=TIME, s=2, linewidths=0, vmin=0, vmax=hours.max())
    lo, hi = np.percentile(dB(v[order][m]), [0.5, 99.8])
    ax.set_ylim(lo - 3, hi + 3)
    ax.set_title(title, loc="left")
    ax.set_xlabel("fan speed (rpm)")
cb = fig.colorbar(sc, ax=axes, shrink=0.5, pad=0.015)
cb.set_label("hours since 00:07")
fig.suptitle("Healthy fan: per-rotation features vs speed, every settled 0.6 s window of the night (40 981 windows)",
             x=0.02, ha="left", color=INK, fontsize=12, fontweight="bold")
fig.savefig(FIG / "report_features_vs_speed.png", dpi=110, bbox_inches="tight")
plt.close(fig)

# ---- 2. feature sets at seen vs unseen speeds ------------------------------------
summ = json.loads((OUT / "summary.json").read_text())
fs = summ["feature_sets_unseen_speed"]
names = list(fs)
short = ["A  48 fixed-Hz accel bands\n(current spec)", "B  A + log rpm", "C  order amplitudes, all sensors\n+ log rpm",
         "D  C without audio", "E  accel orders + log rpm"]
seen = [fs[n]["seen_pct"] for n in names]
unseen = [fs[n]["unseen_pct"] for n in names]
fig, ax = plt.subplots(figsize=(10, 4.8))
y = np.arange(len(names))[::-1]
h = 0.36
b1 = ax.barh(y + h / 2 + 0.01, seen, h, color=S1, label="speeds in training (30-90 %)")
b2 = ax.barh(y - h / 2 - 0.01, unseen, h, color=S2, label="unseen speeds (55 %, 65 %)")
for bars, vals in ((b1, seen), (b2, unseen)):
    for r, v in zip(bars, vals):
        ax.text(r.get_width() + 1, r.get_y() + r.get_height() / 2, f"{v:.2f} %" if v < 10 else f"{v:.0f} %",
                va="center", color=INK2, fontsize=9)
ax.set_yticks(y)
ax.set_yticklabels(short)
ax.set_xlim(0, 112)
ax.set_xlabel("false alarms on healthy windows (%), alert threshold = 99th percentile of training")
ax.axvline(1, color=INK2, lw=0.8, ls=":")
ax.text(1.5, y[-1] - 0.62, "1 % expected", color=INK2, fontsize=8, va="center")
ax.set_ylim(y[-1] - 0.85, y[0] + 0.6)
ax.grid(axis="y", visible=False)
ax.legend(loc="lower right", frameon=False)
ax.set_title("Autoencoder trained on the sweeps only, tested on the other sessions", loc="left")
fig.tight_layout()
fig.savefig(FIG / "report_feature_sets.png", dpi=110)
plt.close(fig)

# ---- 3. which orders each sensor sees (one mount-check session) -------------------
sd = Path("data/raw/20261119-073901_pc01_normal_none")
s = Session(sd)
w = np.load(OUT / "windows" / f"{sd.name}.npz", allow_pickle=True)
pick = {400: S1, 700: S2, 900: S3}
streams = [("Accelerometer", "imu", 4096, 16), ("Gyroscope", "gyro", 4096, 16), ("Magnetometer", "mag", 1024, 8),
           ("Microphone", "audio", 16384, 40)]
fig, axes = plt.subplots(4, 1, figsize=(12, 13))
for ax, (title, stream, nper, omax) in zip(axes, streams):
    for seg in s.segments:
        if seg["pwm"] not in pick or not seg["label"].startswith("duty"):
            continue
        m = (w["tc"] > seg["t0"]) & (w["tc"] < seg["t1"]) & w["settled"]
        r = float(np.median(w["rpm"][m]))
        x = s.slice(stream, seg["t0"], seg["t1"])
        f, p = psd(x, s.stream_rate(stream), nper)
        p = p.sum(1)
        ax.semilogy(f / (r / 60), p, lw=0.9, color=pick[seg["pwm"]], label=f"{seg['pwm'] / 10:.0f} % duty, {r:.0f} rpm")
    ax.set_xlim(0, omax)
    ax.set_xticks(range(0, omax + 1, 1 if omax <= 16 else 2))
    ax.set_title(title, loc="left")
    ax.set_ylabel("PSD")
axes[0].legend(frameon=False, loc="upper right")
axes[-1].set_xlabel("order (frequency / rotation frequency): peaks that line up across speeds belong to the fan")
fig.suptitle("Spectra against rotation order, 07:39 mount check (end of night)", x=0.02, ha="left", color=INK,
             fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "report_orders.png", dpi=100)
plt.close(fig)

# ---- 4. baseline per sweep across the night ---------------------------------------
sweeps = [t for t in tabs if str(t["profile"]) in ("mount_check", "speed_sweep")]
panels = [("Accel 1x (dB re 1 g)", lambda t: t["acc_ord"][:, 0]), ("Gyro 1x (dB re 1 dps)", lambda t: t["gyr_ord"][:, 0]),
          ("Audio 7x (dB)", lambda t: t["aud_ord"][:, 6]), ("Magnetometer 2x (dB re 1 G)", lambda t: t["mag_ord"][:, 1])]
fig, axes = plt.subplots(1, 4, figsize=(17, 4.6))
h0 = min(float(t["clock"][0]) for t in sweeps)
hmax = max(float(t["clock"][0]) for t in sweeps) - h0
for ax, (title, fn) in zip(axes, panels):
    for t in sweeps:
        v = fn(t)
        d = sorted(set(t["pwm"][t["settled"]]) - {-1})
        med = [np.median(dB(v[t["settled"] & (t["pwm"] == x) & np.isfinite(v)])) for x in d]
        c = TIME((float(t["clock"][0]) - h0) / hmax)
        ax.plot([x / 10 for x in d], med, "-o", ms=4, lw=1.6, color=c,
                label=datetime.fromtimestamp(float(t["clock"][0])).strftime("%H:%M")
                + (" mount check" if str(t["profile"]) == "mount_check" else " sweep"))
    ax.set_title(title, loc="left")
    ax.set_xlabel("duty (%)")
axes[0].legend(frameon=False, fontsize=8)
fig.suptitle("Healthy baseline, one line per sweep (light = early, dark = late)", x=0.01, ha="left", color=INK,
             fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig(FIG / "report_baseline_per_sweep.png", dpi=105)
plt.close(fig)
print("figures written")
