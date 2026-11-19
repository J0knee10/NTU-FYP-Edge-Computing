"""Summarise all window tables: baselines vs speed, stability, drift, disturbances, AE false alarms.

usage: python night_summary.py [--blades N]
"""
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from features.normalise import Normaliser
from models.autoencoder import MLPAutoencoder

OUT = Path("results/own/overnight")
FIG = OUT / "figs"
FIG.mkdir(parents=True, exist_ok=True)
BLADES = int(sys.argv[sys.argv.index("--blades") + 1]) if "--blades" in sys.argv else 7

tabs = []
for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
    z = dict(np.load(f, allow_pickle=True))
    if "campaign" not in str(z["notes"]):
        continue
    z["name"] = Path(f).stem
    tabs.append(z)
print(f"{len(tabs)} campaign sessions")
if not tabs:
    sys.exit()


def cat(key):
    return np.concatenate([t[key] for t in tabs])


sess = np.concatenate([np.full(len(t["tc"]), i) for i, t in enumerate(tabs)])
clock = cat("clock")
rpm = cat("rpm")
pwm = cat("pwm")
settled = cat("settled")
label = cat("label")
prof = np.concatenate([np.full(len(t["tc"]), str(t["profile"])) for t in tabs])
temp, hum, pres, light = cat("temp"), cat("hum"), cat("pres"), cat("light")
acc_ord, gyr_ord, mag_ord, aud_ord = cat("acc_ord"), cat("gyr_ord"), cat("mag_ord"), cat("aud_ord")
acc_hf, aud_db = cat("acc_hf"), cat("aud_db")
acc1_ax = cat("acc_1x_axis")
X48 = cat("X48")
hours = (clock - clock.min()) / 3600

# Candidate features (log10 so ratios become differences).
L = lambda v: np.log10(np.maximum(v, 1e-9))  # noqa: E731
cands = {
    "acc_1x": L(acc_ord[:, 0]), "acc_2x": L(acc_ord[:, 1]), f"acc_{BLADES}x(bpf)": L(acc_ord[:, BLADES - 1]),
    "acc_1x_x": L(acc1_ax[:, 0]), "acc_1x_y": L(acc1_ax[:, 1]), "acc_1x_z": L(acc1_ax[:, 2]),
    "acc_hf": L(acc_hf),
    "gyr_1x": L(gyr_ord[:, 0]), "gyr_2x": L(gyr_ord[:, 1]),
    "mag_1x": L(mag_ord[:, 0]), "mag_2x(elec)": L(mag_ord[:, 1]), "mag_4x": L(mag_ord[:, 3]),
    "aud_db": aud_db / 20, "aud_1x": L(aud_ord[:, 0]), f"aud_{BLADES}x(bpf)": L(aud_ord[:, BLADES - 1]),
}

report = {"sessions": [str(t["name"]) for t in tabs], "blades_assumed": BLADES}

# ---- 1. Baseline vs speed (settled windows, all sessions) -------------------
fig, axes = plt.subplots(3, 5, figsize=(20, 11))
for ax, (name, v) in zip(axes.ravel(), cands.items()):
    m = settled & np.isfinite(v) & np.isfinite(rpm)
    sc = ax.scatter(rpm[m], v[m], c=hours[m], s=1, cmap="viridis", alpha=0.4)
    ax.set_title(name, fontsize=9)
    ax.set_xlabel("rpm", fontsize=8)
fig.colorbar(sc, ax=axes, label="hours since start", shrink=0.6)
fig.suptitle("Candidate features vs fan speed, healthy fan, all night (colour = time)")
fig.savefig(FIG / "features_vs_rpm.png", dpi=90)
plt.close(fig)

# ---- 2. Noise and repeatability at fixed duty --------------------------------
rows = []
for d in sorted(set(pwm[settled]) - {-1}):
    md = settled & (pwm == d)
    for name, v in cands.items():
        per = []
        within = []
        for i in np.unique(sess[md]):
            mm = md & (sess == i) & np.isfinite(v)
            if mm.sum() < 30:
                continue
            per.append(np.median(v[mm]))
            within.append(np.std(v[mm]))
        if len(per) < 1:
            continue
        rows.append(dict(duty=int(d), feature=name, n_sessions=len(per), within_sd=float(np.median(within)),
                         between_sd=float(np.std(per)) if len(per) > 1 else np.nan,
                         median=float(np.median(per))))
report["stability"] = rows
print("\nfeature stability at fixed duty (log10 units; 0.1 = 26 % change):")
print(f"{'feature':>14} {'within-seg sd':>13} {'between-session sd':>18}   (median over duties)")
for name in cands:
    w = [r["within_sd"] for r in rows if r["feature"] == name]
    b = [r["between_sd"] for r in rows if r["feature"] == name and np.isfinite(r["between_sd"])]
    print(f"{name:>14} {np.median(w) if w else np.nan:13.3f} {np.median(b) if b else np.nan:18.3f}")

# ---- 3. Drift over the night at fixed duty + temperature ----------------------
fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
for d, c in zip([700, 500, 900, 600, 400], ["C0", "C1", "C2", "C3", "C4"]):
    md = settled & (pwm == d)
    if md.sum() < 50:
        continue
    for ax, name in zip(axes[:2], ["acc_1x", "mag_2x(elec)"]):
        ax.plot(hours[md], cands[name][md], ".", ms=1, color=c, label=f"duty {d / 10:.0f}%")
for ax, name in zip(axes[:2], ["acc_1x", "mag_2x(elec)"]):
    ax.set_ylabel(f"log10 {name}")
    ax.legend(fontsize=7, markerscale=8)
axes[2].plot(hours, temp, ".", ms=1, label="SHT30 temp C")
ax2 = axes[2].twinx()
ax2.plot(hours, light, ".", ms=1, color="orange", label="light (clear)")
axes[2].set_ylabel("temp C")
ax2.set_ylabel("light")
axes[2].set_xlabel("hours since start")
fig.suptitle("Drift over the night at fixed duty, with context")
fig.savefig(FIG / "drift_over_night.png", dpi=90)
plt.close(fig)

# correlation of each feature (residual from per-duty median) with temperature
corr = {}
for name, v in cands.items():
    res = np.full(len(v), np.nan)
    for d in set(pwm[settled]) - {-1}:
        md = settled & (pwm == d) & np.isfinite(v)
        if md.sum() > 30:
            res[md] = v[md] - np.median(v[md])
    m = np.isfinite(res) & np.isfinite(temp)
    corr[name] = float(np.corrcoef(res[m], temp[m])[0, 1]) if m.sum() > 100 and np.std(temp[m]) > 0 else np.nan
report["corr_with_temp"] = corr
print("\ncorrelation of feature (minus its per-duty median) with temperature:")
print("  " + "  ".join(f"{k}:{v:+.2f}" for k, v in corr.items()))

# ---- 4. Disturbances: impulsive windows ---------------------------------------
ev = np.zeros(len(acc_hf), bool)
for i in np.unique(sess):
    for d in set(pwm[sess == i]):
        m = (sess == i) & (pwm == d) & settled
        if m.sum() < 30:
            continue
        med = np.median(acc_hf[m])
        mad = np.median(np.abs(acc_hf[m] - med)) + 1e-9
        ev[m] = (acc_hf[m] - med) / (1.4826 * mad) > 8
aud_ev = np.zeros(len(aud_db), bool)
for i in np.unique(sess):
    for d in set(pwm[sess == i]):
        m = (sess == i) & (pwm == d) & settled & np.isfinite(aud_db)
        if m.sum() > 30:
            aud_ev[m] = aud_db[m] - np.median(aud_db[m]) > 6
report["disturbances"] = dict(acc_impulsive_windows=int(ev.sum()), audio_loud_windows=int(aud_ev.sum()),
                              both=int((ev & aud_ev).sum()), settled_windows=int(settled.sum()))
print(f"\ndisturbances: {ev.sum()} impulsive accel windows, {aud_ev.sum()} loud audio windows "
      f"({(ev & aud_ev).sum()} both) out of {settled.sum()} settled windows")
for nm, e in (("impulsive accel", ev), ("loud audio", aud_ev)):
    if e.any():
        hh = sorted({datetime.fromtimestamp(c).strftime('%H:%M') for c in clock[e]})
        print(f"  {nm} at", hh[:60])
report["disturbance_minutes"] = {
    "accel": sorted({datetime.fromtimestamp(c).strftime('%H:%M') for c in clock[ev]}),
    "audio": sorted({datetime.fromtimestamp(c).strftime('%H:%M') for c in clock[aud_ev]}),
}

# ---- 5. Autoencoder false alarms over the night ---------------------------------
# Train on the first full cycle (mount check + sweep + 70 % + benign drift + steady) if present.
first_cycle = [i for i, t in enumerate(tabs)][: min(5, max(1, len(tabs) // 2))]
train_m = np.isin(sess, first_cycle) & settled
if train_m.sum() > 500:
    rng = np.random.default_rng(0)
    idx = np.nonzero(train_m)[0]
    rng.shuffle(idx)
    cut = int(0.8 * len(idx))
    tr, va = idx[:cut], idx[cut:]
    norm = Normaliser.fit(X48[tr])
    ae = MLPAutoencoder()
    ae.train(norm(X48[tr]), epochs=30)
    thr = np.quantile(ae.score(norm(X48[va])), 0.99)
    later = settled & ~np.isin(sess, first_cycle)
    sc = ae.score(norm(X48))
    fpr_later = float((sc[later] > thr).mean()) if later.any() else np.nan
    report["autoencoder"] = dict(train_sessions=[str(tabs[i]["name"]) for i in first_cycle],
                                 threshold_q99=float(thr), false_alarm_rate_later=fpr_later,
                                 n_later=int(later.sum()))
    print(f"\nautoencoder (48 features) trained on sessions {first_cycle}: false-alarm rate on later "
          f"healthy windows = {100 * fpr_later:.2f} % (expected ~1 % at the 99th-percentile threshold)")
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.semilogy(hours, sc, ".", ms=1)
    ax.axhline(thr, color="r")
    ax.set_xlabel("hours")
    ax.set_ylabel("AE score")
    ax.set_title("Autoencoder score over the night (red = alert threshold from the first sessions)")
    fig.savefig(FIG / "ae_score_over_night.png", dpi=90)
    plt.close(fig)
    # false alarms per later session
    per = {}
    for i in np.unique(sess[later]):
        m = later & (sess == i)
        per[str(tabs[i]["name"])] = round(float((sc[m] > thr).mean()) * 100, 2)
    report["autoencoder"]["false_alarm_pct_per_session"] = per

# ---- 6. Benign drift: false alarms at speeds the model never saw ---------------
# Train on sweep-type sessions (10 % duty steps), test on everything else; split by whether
# the window's duty appeared in training. 55 % and 65 % (benign_drift ramps) are never in a sweep.
train_prof = np.isin(prof, ["mount_check", "speed_sweep"])
tr_all = np.nonzero(train_prof & settled)[0]
if len(tr_all) > 500 and (settled & ~train_prof).any():
    rng = np.random.default_rng(1)
    rng.shuffle(tr_all)
    cut = int(0.8 * len(tr_all))
    tr, va = tr_all[:cut], tr_all[cut:]
    seen = set(pwm[tr_all])
    norm6 = Normaliser.fit(X48[tr])
    ae6 = MLPAutoencoder()
    ae6.train(norm6(X48[tr]), epochs=30)
    thr6 = np.quantile(ae6.score(norm6(X48[va])), 0.99)
    sc6 = ae6.score(norm6(X48))
    test = settled & ~train_prof
    res6 = {}
    for d in sorted(set(pwm[test]) - {-1}):
        m = test & (pwm == d)
        res6[f"{d / 10:.0f}%{'' if d in seen else ' (unseen)'}"] = round(100 * float((sc6[m] > thr6).mean()), 2)
    report["unseen_speed_false_alarms_pct"] = res6
    print("\nAE trained on sweep sessions only: false-alarm % on other sessions, per duty:")
    print("  " + "  ".join(f"{k}: {v}" for k, v in res6.items()))

# ---- 7. Which feature set generalises to unseen speeds? ------------------------
def fill(F):
    F = np.array(F, dtype=np.float64)
    med = np.nanmedian(F, axis=0)
    bad = np.isnan(F)
    F[bad] = np.take(med, np.nonzero(bad)[1])
    return F.astype(np.float32)


lr = np.log10(np.maximum(rpm, 1))[:, None]
aud_ok = np.isfinite(aud_ord[:, :12]).mean(0) > 0.9
sets = {
    "A: 48 fixed-Hz accel features (current spec)": X48,
    "B: A + log rpm": np.hstack([X48, lr]),
    "C: order amplitudes acc/gyro/mag/audio + log rpm": np.hstack(
        [L(acc_ord[:, :12]), L(gyr_ord[:, :6]), L(mag_ord[:, :3]), L(aud_ord[:, :12][:, aud_ok]), aud_db[:, None] / 20, lr]),
    "D: C without audio": np.hstack([L(acc_ord[:, :12]), L(gyr_ord[:, :6]), L(mag_ord[:, :3]), lr]),
    "E: accel orders only + log rpm": np.hstack([L(acc_ord[:, :12]), lr]),
}
train_prof = np.isin(prof, ["mount_check", "speed_sweep"])
tr_all = np.nonzero(train_prof & settled & np.isfinite(rpm))[0]
test = settled & ~train_prof & np.isfinite(rpm)
if len(tr_all) > 500 and test.any():
    rng = np.random.default_rng(2)
    rng.shuffle(tr_all)
    cut = int(0.8 * len(tr_all))
    tr, va = tr_all[:cut], tr_all[cut:]
    seen = set(pwm[tr_all])
    res7 = {}
    print("\nfeature sets: AE trained on sweep sessions; false-alarm % on other sessions")
    for name, F in sets.items():
        F = fill(F)
        nm = Normaliser.fit(F[tr])
        d = F.shape[1]
        ae7 = MLPAutoencoder(sizes=(d, 16, 8, 16, d))
        ae7.train(nm(F[tr]), epochs=30)
        th = np.quantile(ae7.score(nm(F[va])), 0.99)
        sc7 = ae7.score(nm(F))
        seen_m = test & np.isin(pwm, list(seen))
        unseen_m = test & ~np.isin(pwm, list(seen))
        r = dict(n_features=d, seen_pct=round(100 * float((sc7[seen_m] > th).mean()), 2),
                 unseen_pct=round(100 * float((sc7[unseen_m] > th).mean()), 2) if unseen_m.any() else None,
                 per_duty={f"{dd / 10:.0f}%": round(100 * float((sc7[test & (pwm == dd)] > th).mean()), 1)
                           for dd in sorted(set(pwm[test]) - {-1})})
        res7[name] = r
        print(f"  {name:<52} n={d:3d}  seen speeds {r['seen_pct']:6.2f} %   unseen {r['unseen_pct']} %   {r['per_duty']}")
    report["feature_sets_unseen_speed"] = res7

(OUT / "summary.json").write_text(json.dumps(report, indent=1, default=float))
print("\nwrote", OUT / "summary.json", "and figures in", FIG)
