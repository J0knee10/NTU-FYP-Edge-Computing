"""Feature-set and detector evaluation with session-level validation (step 1 groundwork).

usage: python host/analysis/feature_eval.py [--seeds 3] [--avg 8] [--duties 300:800:100] [--lodo 400:800]
           [--rotate | --loso] [--speed-gate 0.03] [--subsample 8] [--max-sessions N] [--spread-floor 0.001] [--tag name]

Reads the window tables under ANALYSIS_OUT (healthy campaign sessions only), in time order.

Method:
- **Averaging.** A running median of `avg` consecutive windows within one visit to a duty step, as the board
  would do. It runs over every usable settled row; only rows with a full median are scored.
- **Speed-conditioned normalisation.** For every feature, the healthy curve (median per duty) and spread are
  learned from the training sessions only, on the medianed features (so the spread is the real spread of what
  is scored, whatever the overlap between windows). Spread = within-session (1.4826 x MAD) and between-session
  (sd of session medians) combined. z = (f - curve(log rpm)) / spread(log rpm), interpolated along log rpm.
- **Splits.** Sessions are in time order. The first 60 % are the training block; its last sweep-type
  session (all duties) is held out to set the alert threshold (99th percentile of its scores); the rest of
  the block trains. Test on the remaining sessions.
- **Rotation.** `--rotate` repeats the test with each sweep-type training session as the threshold session
  and reports mean [min-max]: one threshold session alone makes the numbers swing.
- **Leave-one-session-out calibration.** `--loso`: no held-out threshold session. Each training session is
  scored by a model (normalisation + detector) fitted on the other training sessions; the threshold is a high
  percentile (99, 99.5, 99.9) of all those out-of-session scores pooled. The final model uses every training
  session. This is the calibration a device could use: several healthy sessions, no oracle. max|z| and
  Mahalanobis only (the autoencoder would need one fit per session).
- **Matched false alarms.** To compare feature sets fairly, detection is also reported at a threshold that
  gives 2 % false alarms on the healthy test windows (an oracle threshold, for comparison only).
- **Synthetic faults.** Multiply the in-plane accelerometer 1x (board x and z) of test windows at 40-80 %
  by 1.25 / 1.5 / 2 before the running median, then count detections.
- **Unseen speeds.** Leave one duty (in `--lodo`) out of training, then test false alarms at that duty.
- **Duty grid.** `--duties start:stop:step` (permille, inclusive).
- **Long windows.** If `long_windows.py` has written sidecars (ANALYSIS_OUT/windows_long), set L uses 5 s
  tach-locked per-axis orders, and every set is scored on the same rows (whole long window settled).
- **Subsampling.** `--subsample 8` keeps every 8th row: with 4096-sample long windows that is non-overlapping
  5 s windows, as a streaming single-bin DFT on the board would give (no sample buffer).
- **Speed gate.** `--speed-gate 0.03` drops rows whose tach speed is more than 3 % off the median of their
  visit to a duty step, and the 4 rows either side (the span of a 5 s window). Logger 0.3.1 tach glitches
  (a few seconds at +5 %) put the narrowband 5 s features on the wrong bin and gave z up to ~150.
- **Detectors** on the z-scores: max |z|, Mahalanobis distance, and the MLP autoencoder (several seeds).
History: 19 Nov afternoon, after a methods review: spread measured on medianed features (was a 1.25/sqrt(avg)
factor that assumed independent windows), median over all settled rows with full-median rows scored, visits
split, matched-false-alarm comparison, healthy sessions only. Evening: --loso (31 sessions: one held-out session
gave unstable false alarms; pooled out-of-session scores did not).
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.autoencoder import MLPAutoencoder  # noqa: E402

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight"))
L = lambda v: np.log10(np.maximum(v, 1e-9))  # noqa: E731
INPLANE = (0, 2)  # board x, z = rotor plane (same on tapeCorner and flat4)
SPREAD_FLOOR = 1e-3  # log10 units; --spread-floor
SUBSAMPLE = 1  # --subsample k: keep every k-th row (8 with 512-sample rows = non-overlapping 4096 windows)
MATCHED_FA = 0.02
SPEED_GATE = 0.0  # --speed-gate: max relative speed deviation from the visit median (0 = off)


def load():
    tabs = []
    for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
        z = dict(np.load(f, allow_pickle=True))
        if "campaign" in str(z["notes"]) and "acc_axis" in z and str(z.get("fault", "normal")) == "normal":
            z["name"] = Path(f).stem
            side = OUT / "windows_long" / Path(f).name
            if side.exists():
                z.update(dict(np.load(side)))
            tabs.append(z)
    with_long = [t for t in tabs if "acc_axis_long" in t]
    if with_long and len(with_long) < len(tabs):  # compare all sets on the same sessions
        print(f"WARNING: {len(tabs) - len(with_long)} session(s) have no long-window sidecar (run long_windows.py);"
              " left out:", [t["name"] for t in tabs if "acc_axis_long" not in t])
        tabs = with_long
    return tabs


def feature_sets(t):
    """Raw (log10) feature matrices per set for one session table. Axis orders: 0.5, 1, 1.5, 2, 3, 7."""
    acc_ax, gyr_ax = t["acc_axis"], t["gyr_axis"]  # (n, 3, 6)
    compact = np.column_stack([
        L(acc_ax[:, 0, 1]), L(acc_ax[:, 1, 1]), L(acc_ax[:, 2, 1]),      # 1x per axis
        L(acc_ax[:, :, 3].max(1)), L(acc_ax[:, :, 0].max(1)),            # 2x, 0.5x (largest axis)
        L(t["acc_ord"][:, 6]), L(t["acc_ord"][:, 11]), L(t["acc_hf"]),     # 7x (all axes), 12x, 150-400 Hz
        L(gyr_ax[:, 0, 1]), L(gyr_ax[:, 1, 1]), L(gyr_ax[:, 2, 1]),      # gyro 1x per axis
    ])
    sets = {
        "A  48 fixed-Hz bands": np.asarray(t["X48"], float),
        "O  11 order features (accel+gyro, per axis)": compact,
        "O+ O plus audio 7x": np.column_stack([compact, L(t["aud_ord"][:, 6])]),
        "Oall all orders (acc 1-9, gyro 1-6, mag 1-3)": np.column_stack(
            [L(t["acc_ord"][:, :9]), L(t["gyr_ord"][:, :6]), L(t["mag_ord"][:, :3])]),
    }
    if "acc_axis_long" in t:  # same columns as O, orders from 5 s tach-locked windows (12x, 150-400 Hz stay short)
        al, gl = t["acc_axis_long"], t["gyr_axis_long"]
        sets["L  11 features, 5 s tach-locked orders"] = np.column_stack([
            L(al[:, 0, 1]), L(al[:, 1, 1]), L(al[:, 2, 1]),
            L(al[:, :, 3].max(1)), L(al[:, :, 0].max(1)),
            L(np.sqrt((al[:, :, 5] ** 2).sum(1))), L(t["acc_ord"][:, 11]), L(t["acc_hf"]),
            L(gl[:, 0, 1]), L(gl[:, 1, 1]), L(gl[:, 2, 1]),
        ])
    return sets


def inject(set_name, F, ip, inj, fac):
    """Same physical change for every set: in-plane accel 1x (board x and z) multiplied by fac.

    O and L sets hold x, y, z 1x separately (columns 0-2); the 'all orders' set holds the vector 1x (column 0),
    which is recomputed from the per-axis change. Fixed-Hz bands would need the raw spectrum: skipped."""
    if set_name.startswith("A"):
        return None
    Fi = F.copy()
    if set_name.startswith("Oall"):
        vec2 = 10 ** (2 * Fi[inj, 0]) + (fac ** 2 - 1) * (ip[inj] ** 2).sum(1)
        Fi[inj, 0] = np.log10(np.sqrt(vec2))
    else:
        Fi[inj, 0] += np.log10(fac)  # acc 1x x
        Fi[inj, 2] += np.log10(fac)  # acc 1x z
    return Fi


class SpeedNorm:
    """Per-feature healthy curve and spread vs log rpm, from per-duty statistics of (medianed) training windows.

    The spread combines the within-session spread with the spread of per-session medians, so slow drift
    between sessions is part of 'healthy' and does not make every later session look abnormal."""

    def __init__(self, F, lr, duty, sess):
        ds = sorted(set(duty) - {-1})
        self.x = np.array([np.median(lr[duty == d]) for d in ds])
        o = np.argsort(self.x)
        self.x = self.x[o]
        med, spr = [], []
        for d in np.array(ds)[o]:
            md = duty == d
            v = F[md]
            m = np.nanmedian(v, 0)
            sw, per = [], []
            for s_ in np.unique(sess[md]):
                vs = F[md & (sess == s_)]
                if len(vs) >= max(5, 20 // SUBSAMPLE):  # enough windows for a within-session spread
                    ms = np.nanmedian(vs, 0)
                    per.append(ms)
                    sw.append(1.4826 * np.nanmedian(np.abs(vs - ms), 0))
            s_w = np.nanmedian(sw, 0) if sw else 1.4826 * np.nanmedian(np.abs(v - m), 0)
            s_b = np.nanstd(per, 0, ddof=1) if len(per) > 1 else np.zeros(F.shape[1])
            med.append(m)
            spr.append(np.maximum(np.sqrt(s_w ** 2 + s_b ** 2), SPREAD_FLOOR))
        self.med, self.spr = np.array(med), np.array(spr)

    def __call__(self, F, lr):
        Z = np.empty_like(F, dtype=float)
        for j in range(F.shape[1]):
            Z[:, j] = (F[:, j] - np.interp(lr, self.x, self.med[:, j])) / np.interp(lr, self.x, self.spr[:, j])
        return np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)


def running_median(X, groups, k):
    """Median of the last k rows within each group, and each row's position in its group."""
    out, pos = X.copy(), np.zeros(len(X), int)
    for g in np.unique(groups):
        idx = np.nonzero(groups == g)[0]
        pos[idx] = np.arange(len(idx))
        if k > 1:
            for n, i in enumerate(idx):
                out[i] = np.median(X[idx[max(0, n - k + 1):n + 1]], 0)
    return out, pos


def detectors(Ztr, seeds):
    mu = Ztr.mean(0)
    cov = np.cov(Ztr, rowvar=False) + 1e-3 * np.eye(Ztr.shape[1])
    icov = np.linalg.inv(cov)
    dets = {"max|z|": lambda Z: np.abs(Z).max(1),
            "Mahalanobis": lambda Z: np.einsum("ij,jk,ik->i", Z - mu, icov, Z - mu)}
    for s in range(seeds):
        d = Ztr.shape[1]
        h1, h2 = max(4, min(16, d // 2)), max(2, min(8, d // 4))
        ae = MLPAutoencoder(sizes=(d, h1, h2, h1, d), seed=s)
        ae.train(Ztr.astype(np.float32), epochs=30)
        dets[f"AE seed {s}"] = lambda Z, ae=ae: ae.score(Z.astype(np.float32))
    return dets


def speed_outliers(t, frac, span=9):
    """Rows whose speed is more than frac off the median of their visit to a duty step (settled rows), widened by
    span // 2 rows each side (a 5 s window spans 9 rows): a speed-plausibility gate."""
    rpm, pwm, st = t["rpm"], t["pwm"], t["settled"]
    visit = np.cumsum(np.r_[True, np.diff(pwm) != 0])
    bad = np.zeros(len(rpm), bool)
    for v in np.unique(visit):
        m = (visit == v) & st & np.isfinite(rpm)
        if m.sum() >= 5:
            bad |= m & (np.abs(rpm / np.median(rpm[m]) - 1) > frac)
    return np.convolve(bad.astype(int), np.ones(span, int), mode="same") > 0


def gather(tabs, sel, set_name, duties, avg=1, fac=None):
    """Running-medianed features of the selected sessions, for the rows that are scored.

    The median runs over consecutive usable rows (every SUBSAMPLE-th settled row) of one visit to a duty step.
    Returned rows have a full median of `avg` windows and, if sidecars exist, a settled long window. The row
    selection does not depend on the features, so calls with and without `fac` return the same rows.
    fac: multiply the in-plane accel 1x by fac at 40-80 % before the median (synthetic fault).
    Returns (F, log rpm, duty, session index) or None if the set can't be injected."""
    F, lr, duty, ss = [], [], [], []
    for i in sel:
        t = tabs[i]
        base = t["settled"] & np.isfinite(t["rpm"]) & np.isin(t["pwm"], duties)
        base &= np.arange(len(base)) % SUBSAMPLE == 0
        if SPEED_GATE:
            base &= ~speed_outliers(t, SPEED_GATE)
        idx = np.nonzero(base)[0]
        if len(idx) == 0:  # e.g. a steady session at a duty outside the grid
            continue
        X = feature_sets(t)[set_name][idx].astype(float)
        pwm = t["pwm"][idx]
        if fac is not None:
            ip = np.column_stack([t["acc_axis"][idx][:, a, 1] for a in INPLANE])
            X = inject(set_name, X, ip, (pwm >= 400) & (pwm <= 800), fac)
            if X is None:
                return None
        visit = np.cumsum(np.r_[True, (np.diff(idx) != SUBSAMPLE) | (np.diff(pwm) != 0)])
        Xm, pos = running_median(X, visit, avg)
        keep = pos >= avg - 1
        if "settled_long" in t:
            keep &= t["settled_long"][idx]
        F.append(Xm[keep])
        lr.append(np.log10(t["rpm"][idx][keep]))
        duty.append(pwm[keep])
        ss.append(np.full(int(keep.sum()), i))
    if not F:
        ncol = feature_sets(tabs[sel[0]])[set_name].shape[1] if len(sel) else 0
        return np.empty((0, ncol)), np.empty(0), np.empty(0, int), np.empty(0, int)
    return np.vstack(F), np.concatenate(lr), np.concatenate(duty), np.concatenate(ss)


def evaluate(tabs, train_idx, th_idx, test_idx, duties, set_name, avg, seeds, lodo_duties=()):
    """False alarms and synthetic-fault detection for one split; leave-one-duty-out if lodo_duties."""
    tr = gather(tabs, train_idx, set_name, duties, avg)
    th = gather(tabs, [th_idx], set_name, duties, avg)
    te = gather(tabs, test_idx, set_name, duties, avg)
    norm = SpeedNorm(*tr)
    Ztr, Zth, Zte = norm(tr[0], tr[1]), norm(th[0], th[1]), norm(te[0], te[1])
    inj = (te[2] >= 400) & (te[2] <= 800)  # synthetic in-plane 1x faults on test windows at 40-80 %
    Zi = {}
    for fac in (1.25, 1.5, 2.0):
        g = gather(tabs, test_idx, set_name, duties, avg, fac)
        if g is not None:
            Zi[fac] = norm(g[0], g[1])
    dets = detectors(Ztr, seeds)
    row = {}
    for dname, score in dets.items():
        s_te = score(Zte)
        thr = np.quantile(score(Zth), 0.99)
        thr_m = np.quantile(s_te, 1 - MATCHED_FA)  # oracle: 2 % false alarms on healthy test windows
        r = {"threshold": float(thr), "FA_test": float((s_te > thr).mean()),
             "FA_per_duty": {int(d): round(100 * float((s_te[te[2] == d] > thr).mean()), 2) for d in np.unique(te[2])}}
        for fac, Z in Zi.items():
            s = score(Z)
            for tag, th_ in (("", thr), ("matched_", thr_m)):
                hit = s > th_
                r[f"{tag}detect_x{fac}"] = float(hit[inj].mean())
                r[f"{tag}detect_x{fac}_per_duty"] = {int(d): round(100 * float(hit[inj & (te[2] == d)].mean()), 1)
                                                     for d in np.unique(te[2][inj])}
        row[dname] = r
    lodo = {}
    for d in lodo_duties:  # leave-one-duty-out false alarms (unseen speed)
        keep = tr[2] != d
        if keep.sum() < 100 or not (te[2] == d).any():
            continue
        n2 = SpeedNorm(tr[0][keep], tr[1][keep], tr[2][keep], tr[3][keep])
        kth = th[2] != d
        d2 = detectors(n2(tr[0][keep], tr[1][keep]), 1)
        Z2th, Z2te = n2(th[0][kth], th[1][kth]), n2(te[0], te[1])
        for dname in ("max|z|", "Mahalanobis", "AE seed 0"):
            thr = np.quantile(d2[dname](Z2th), 0.99)
            lodo.setdefault(dname, {})[d] = round(100 * float((d2[dname](Z2te)[te[2] == d] > thr).mean()), 2)
    return row, lodo


LOSO_Q = (0.99, 0.995, 0.999)


def loso_calibrate(tabs, train_idx, set_name, duties, avg, dnames=("max|z|", "Mahalanobis")):
    """Leave-one-session-out calibration: each training session scored by a model fitted on the others.
    Returns (norm, dets) fitted on every training session, the pooled out-of-session scores per detector, and
    the number of sessions that contributed."""
    oos = {d: [] for d in dnames}
    for s in train_idx:
        g = gather(tabs, [s], set_name, duties, avg)
        if len(g[0]) == 0:
            continue
        tr = gather(tabs, [i for i in train_idx if i != s], set_name, duties, avg)
        norm = SpeedNorm(*tr)
        dets = detectors(norm(tr[0], tr[1]), 0)
        for d in dnames:
            oos[d].append(dets[d](norm(g[0], g[1])))
    tr = gather(tabs, train_idx, set_name, duties, avg)
    norm = SpeedNorm(*tr)
    dets = detectors(norm(tr[0], tr[1]), 0)
    return norm, dets, {d: np.concatenate(v) for d, v in oos.items()}, len(oos[dnames[0]])


def loso(tabs, train_idx, test_idx, duties, set_name, avg):
    """Threshold from leave-one-session-out scores pooled over the training sessions (see module docstring)."""
    dnames = ("max|z|", "Mahalanobis")
    norm, dets, oos, ncal = loso_calibrate(tabs, train_idx, set_name, duties, avg, dnames)
    te = gather(tabs, test_idx, set_name, duties, avg)
    Zte = norm(te[0], te[1])
    inj = (te[2] >= 400) & (te[2] <= 800)
    Zi = {}
    for fac in (1.25, 1.5, 2.0):
        g = gather(tabs, test_idx, set_name, duties, avg, fac)
        if g is not None:
            Zi[fac] = norm(g[0], g[1])
    out = {"calibration_sessions": ncal}
    for d in dnames:
        sc = oos[d]
        s_te = dets[d](Zte)
        for q in LOSO_Q:
            thr = float(np.quantile(sc, q))
            fa_s = {str(tabs[k]["name"]): round(100 * float((s_te[te[3] == k] > thr).mean()), 2) for k in np.unique(te[3])}
            r = {"threshold": thr, "FA_test": 100 * float((s_te > thr).mean()), "FA_per_session": fa_s,
                 "FA_session_max": max(fa_s.values())}
            for fac, Z in Zi.items():
                hit = dets[d](Z) > thr
                r[f"detect_x{fac}"] = 100 * float(hit[inj].mean())
                r[f"detect_x{fac}_per_duty"] = {int(dd): round(100 * float(hit[inj & (te[2] == dd)].mean()), 1)
                                                for dd in np.unique(te[2][inj])}
            out[f"{d} q{q}"] = r
    return out


def rotate(tabs, ntr, sweepish, test_idx, duties, avgs, seeds):
    """Repeat the evaluation with each sweep-type training session in turn as the threshold session."""
    out = {}
    for avg in avgs:
        for set_name in feature_sets(tabs[0]):
            if set_name.startswith("A"):
                continue
            runs = []
            for th_idx in sweepish:
                train_idx = [i for i in range(ntr) if i != th_idx]
                row, _ = evaluate(tabs, train_idx, th_idx, test_idx, duties, set_name, avg, seeds)
                runs.append(row)
            key = f"{set_name} | avg {avg}"
            out[key] = {}
            print(f"\n== {key}: mean [min-max] over {len(runs)} threshold sessions")
            groups = {"max|z|": ["max|z|"], "Mahalanobis": ["Mahalanobis"],
                      "AE": [k for k in runs[0] if k.startswith("AE")]}
            for g, ks in groups.items():
                stats = {}
                for metric in ("FA_test", "detect_x1.25", "detect_x1.5", "detect_x2.0",
                               "matched_detect_x1.25", "matched_detect_x1.5", "matched_detect_x2.0"):
                    v = np.array([np.mean([r[k][metric] for k in ks]) for r in runs]) * 100
                    stats[metric] = [float(v.mean()), float(v.min()), float(v.max())]
                for tag in ("", "matched_"):
                    key_pd = f"{tag}detect_x1.5_per_duty"
                    stats[key_pd] = {d: float(np.mean([r[k][key_pd].get(d, np.nan) for r in runs for k in ks]))
                                     for d in runs[0][ks[0]][key_pd]}
                out[key][g] = stats
                print(f"  {g:12s} FA {stats['FA_test'][0]:5.2f} [{stats['FA_test'][1]:.2f}-{stats['FA_test'][2]:.2f}] %"
                      + "   detect x1.25/1.5/2: " + " / ".join(
                          f"{stats[m][0]:5.1f} [{stats[m][1]:.0f}-{stats[m][2]:.0f}]"
                          for m in ("detect_x1.25", "detect_x1.5", "detect_x2.0"))
                      + "   x1.5 by duty: " + " ".join(f"{d // 10}%:{v:.0f}" for d, v in stats["detect_x1.5_per_duty"].items()))
                print(f"  {'':12s} at matched {100 * MATCHED_FA:.0f} % FA: x1.25/1.5/2: " + " / ".join(
                          f"{stats['matched_' + m][0]:5.1f}" for m in ("detect_x1.25", "detect_x1.5", "detect_x2.0"))
                      + "   x1.5 by duty: " + " ".join(
                          f"{d // 10}%:{v:.0f}" for d, v in stats["matched_detect_x1.5_per_duty"].items()))
    return out


def main():
    global SPREAD_FLOOR, SUBSAMPLE, SPEED_GATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--avg", type=int, default=8)
    ap.add_argument("--train-frac", type=float, default=0.6)
    # default 30-80 %: 90-100 % excluded, tapeCorner rocked there (a different regime)
    ap.add_argument("--duties", default="300:800:100", help="start:stop:step in permille, inclusive")
    ap.add_argument("--lodo", default="400:800", help="range of duties to leave out in turn, inclusive")
    ap.add_argument("--tag", default="", help="suffix for the output file name")
    ap.add_argument("--spread-floor", type=float, default=1e-3, help="minimum spread per feature, log10 units")
    ap.add_argument("--rotate", action="store_true", help="each sweep-type training session as threshold session in turn")
    ap.add_argument("--speed-gate", type=float, default=0.0, help="drop rows >frac off their visit's median speed")
    ap.add_argument("--loso", action="store_true", help="threshold from pooled leave-one-session-out scores")
    ap.add_argument("--subsample", type=int, default=1, help="keep every k-th window row (emulates a longer hop)")
    ap.add_argument("--max-sessions", type=int, help="use only the first N sessions (reproduce an earlier split)")
    args = ap.parse_args()
    SPREAD_FLOOR = args.spread_floor
    SUBSAMPLE = args.subsample
    SPEED_GATE = args.speed_gate
    a, b, c = (int(v) for v in args.duties.split(":"))
    duties = tuple(range(a, b + 1, c))
    lo, hi = (int(v) for v in args.lodo.split(":"))
    lodo_duties = [d for d in duties if lo <= d <= hi]
    tabs = load()
    if args.max_sessions:
        tabs = tabs[:args.max_sessions]
    n = len(tabs)
    ntr = max(3, int(round(args.train_frac * n)))
    # Threshold session: the last sweep-type session (all duties) in the training block, held out.
    sweepish = [i for i in range(ntr) if str(tabs[i]["profile"]) in ("speed_sweep", "speed_sweep_fine", "mount_check")]
    th_idx = sweepish[-1] if sweepish else ntr - 1
    train_idx = [i for i in range(ntr) if i != th_idx]
    test_idx = list(range(ntr, n))
    print(f"{n} sessions; train {len(train_idx)}, threshold session {tabs[th_idx]['name']} "
          f"({tabs[th_idx]['profile']}), test {len(test_idx)}; duties {duties}, left out in turn {lodo_duties}")
    config = {"duties": list(duties), "avg": args.avg, "seeds": args.seeds, "spread_floor": SPREAD_FLOOR,
              "subsample": SUBSAMPLE, "speed_gate": SPEED_GATE, "long_windows": "acc_axis_long" in tabs[0], "matched_fa": MATCHED_FA,
              "sessions": [str(t["name"]) for t in tabs], "test": [str(tabs[i]["name"]) for i in test_idx]}
    if args.loso:
        res = {}
        train_all = list(range(ntr))
        print(f"leave-one-session-out calibration over the {ntr} training sessions; test {len(test_idx)}")
        for avg in sorted({1, args.avg}):
            for set_name in feature_sets(tabs[0]):
                if set_name.startswith("A"):
                    continue
                r = loso(tabs, train_all, test_idx, duties, set_name, avg)
                res[f"{set_name} | avg {avg}"] = r
                print(f"\n== {set_name} | avg {avg} ({r['calibration_sessions']} calibration sessions)")
                for k, v in r.items():
                    if k == "calibration_sessions":
                        continue
                    print(f"  {k:18s} FA {v['FA_test']:5.2f} % (worst session {v['FA_session_max']:5.1f})   detect"
                          + "".join(f"  x{f}: {v.get(f'detect_x{f}', np.nan):5.1f}" for f in (1.25, 1.5, 2.0))
                          + "   x1.5 by duty: " + " ".join(f"{d // 10}%:{p:.0f}"
                                                          for d, p in v.get("detect_x1.5_per_duty", {}).items()))
        res["_config"] = {**config, "loso": True, "train": [str(tabs[i]["name"]) for i in train_all],
                          "quantiles": list(LOSO_Q)}
    elif args.rotate:
        print(f"rotating the threshold session over {[str(tabs[i]['name']) for i in sweepish]}")
        res = rotate(tabs, ntr, sweepish, test_idx, duties, sorted({1, args.avg}), args.seeds)
        res["_config"] = {**config, "rotate": True, "threshold_sessions": [str(tabs[i]["name"]) for i in sweepish]}
    else:
        res = {}
        for avg in sorted({1, args.avg}):
            for set_name in feature_sets(tabs[0]):
                row, lodo = evaluate(tabs, train_idx, th_idx, test_idx, duties, set_name, avg, args.seeds, lodo_duties)
                res[f"{set_name} | avg {avg}"] = {"detectors": row, "leave_one_duty_out_FA_pct": lodo}
                print(f"\n== {set_name} | running median of {avg} window(s)")
                ae_keys = [k for k in row if k.startswith("AE")]
                for dname in ("max|z|", "Mahalanobis"):
                    r = row[dname]
                    print(f"  {dname:12s} thr {r['threshold']:7.2f}  FA {100 * r['FA_test']:5.2f} %   detect x1.25/1.5/2: "
                          + " / ".join(f"{100 * r.get(f'detect_x{f}', np.nan):5.1f}" for f in (1.25, 1.5, 2.0))
                          + "   matched-FA: " + " / ".join(f"{100 * r.get(f'matched_detect_x{f}', np.nan):5.1f}"
                                                       for f in (1.25, 1.5, 2.0))
                          + f"   unseen-duty FA {lodo.get(dname)}")
                fa = [row[k]["FA_test"] for k in ae_keys]
                det = {f: [row[k].get(f"detect_x{f}", np.nan) for k in ae_keys] for f in (1.25, 1.5, 2.0)}
                print(f"  {'AE (' + str(len(ae_keys)) + ' seeds)':12s} FA {100 * np.mean(fa):5.2f}±{100 * np.std(fa):.2f} %"
                      + "   detect x1.25/1.5/2: " + " / ".join(f"{100 * np.mean(det[f]):5.1f}" for f in (1.25, 1.5, 2.0))
                      + f"   unseen-duty FA {lodo.get('AE seed 0')}")
        res["_config"] = {**config, "lodo": lodo_duties, "threshold_session": str(tabs[th_idx]["name"]),
                          "train": [str(tabs[i]["name"]) for i in train_idx]}
    out = OUT / f"feature_eval{'_' + args.tag if args.tag else ''}.json"
    out.write_text(json.dumps(res, indent=1))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
