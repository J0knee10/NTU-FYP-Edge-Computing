"""Feature-set and detector evaluation with session-level validation (step 1 groundwork).

usage: python host/analysis/feature_eval.py [--seeds 5] [--avg 8] [--duties 300:800:100] [--lodo 400:800] [--tag fine]
                                           [--spread-floor 0.001]

Reads the window tables under ANALYSIS_OUT (campaign sessions only), in time order.

Method:
- **Speed-conditioned normalisation.** For every feature, the healthy curve (median per duty) and spread
  (1.4826 x MAD per duty) are learned from the training sessions only. Each window's residual is
  z = (f - curve(log rpm)) / spread(log rpm), interpolated along log rpm. One table per feature, cheap on
  the board.
- **Splits.** Sessions are in time order. The first 60 % are the training block; its last sweep-type
  session (all duties) is held out to set the alert threshold (99th percentile of its scores); the rest of
  the block trains. Test on the remaining sessions. Neighbouring windows are therefore never on both
  sides of the threshold.
- **Duty grid.** `--duties start:stop:step` (permille, inclusive) picks the duties used; 10 % steps by default,
  5 % steps (`300:1000:50`) when the campaign has fine sweeps.
- **Unseen speeds.** Leave one duty (in `--lodo`, default 40-80 %) out of training, then test false alarms
  at that duty. Keep the range inside the grid, so the left-out duty is interpolated, not extrapolated.
- **Synthetic faults.** Multiply the in-plane accelerometer 1x (board x and z) of test windows at 40-80 %
  by 1.25 / 1.5 / 2 (and optionally gyro 1x too), then count detections at the same threshold.
- **Detectors** on the residuals: max |z|, Mahalanobis distance, and the MLP autoencoder (several seeds).
- **Long windows.** If `long_windows.py` has written sidecars (ANALYSIS_OUT/windows_long), an extra set L uses
  5 s tach-locked per-axis orders, and every set is scored on the same rows (whole long window settled).
- **Spread floor.** `--spread-floor` (log10 units) stops very stable features from dominating max|z|.
- **Rotation.** `--rotate` repeats the test with each sweep-type training session as the threshold session
  and reports mean [min-max]: one threshold session alone makes the numbers swing.
- **Subsampling.** `--subsample 8` keeps every 8th row: with 4096-sample long windows that is non-overlapping
  5 s windows, as a streaming single-bin DFT on the board would give (no sample buffer).
- **Averaging.** Optionally a running median of `avg` consecutive windows (same session and duty) before
  scoring, as the board would do over ~5 s.
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


def load():
    tabs = []
    for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
        z = dict(np.load(f, allow_pickle=True))
        if "campaign" in str(z["notes"]) and "acc_axis" in z:
            z["name"] = Path(f).stem
            side = OUT / "windows_long" / Path(f).name
            if side.exists():
                z.update(dict(np.load(side)))
            tabs.append(z)
    return tabs


def feature_sets(t):
    """Raw (log10) feature matrices per set for one session table. Axis orders: 0.5, 1, 1.5, 2, 3, 7."""
    acc_ax, gyr_ax = t["acc_axis"], t["gyr_axis"]  # (n, 3, 6)
    compact = np.column_stack([
        L(acc_ax[:, 0, 1]), L(acc_ax[:, 1, 1]), L(acc_ax[:, 2, 1]),      # 1x per axis
        L(acc_ax[:, :, 3].max(1)), L(acc_ax[:, :, 0].max(1)),            # 2x, 0.5x (largest axis)
        L(t["acc_ord"][:, 6]), L(t["acc_ord"][:, 11]), L(t["acc_hf"]),     # 7x, 12x, 150-400 Hz
        L(gyr_ax[:, 0, 1]), L(gyr_ax[:, 1, 1]), L(gyr_ax[:, 2, 1]),      # gyro 1x per axis
    ])
    sets = {
        "A  48 fixed-Hz bands": np.asarray(t["X48"], float),
        "O  11 order features (accel+gyro, per axis)": compact,
        "O+ O plus audio 7x": np.column_stack([compact, L(t["aud_ord"][:, 6])]),
        "Oall all orders (acc 1-9, gyro 1-6, mag 1-3)": np.column_stack(
            [L(t["acc_ord"][:, :9]), L(t["gyr_ord"][:, :6]), L(t["mag_ord"][:, :3])]),
    }
    if "acc_axis_long" in t:  # same columns as O, orders from 5 s tach-locked windows
        al, gl = t["acc_axis_long"], t["gyr_axis_long"]
        sets["L  11 features, 5 s tach-locked orders"] = np.column_stack([
            L(al[:, 0, 1]), L(al[:, 1, 1]), L(al[:, 2, 1]),
            L(al[:, :, 3].max(1)), L(al[:, :, 0].max(1)),
            L(al[:, :, 5].max(1)), L(t["acc_ord"][:, 11]), L(t["acc_hf"]),
            L(gl[:, 0, 1]), L(gl[:, 1, 1]), L(gl[:, 2, 1]),
        ])
    return sets




def inject(set_name, F, ip, inj, fac):
    """Same physical change for every set: in-plane accel 1x (board x and z) multiplied by fac.

    O sets hold x, y, z 1x separately (columns 0-2); the 'all orders' set holds the vector 1x (column 0),
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


SPREAD_FLOOR = 1e-3  # log10 units; --spread-floor


class SpeedNorm:
    """Per-feature healthy curve and spread vs log rpm, from per-duty statistics of training windows.

    The spread combines the within-session spread (robust sd of single windows, reduced for averaged
    windows) with the spread of per-session medians, so slow drift between sessions is part of
    'healthy' and does not make every later session look abnormal."""

    def __init__(self, F, lr, duty, sess, avg=1):
        ds = sorted(set(duty) - {-1})
        self.x = np.array([np.median(lr[duty == d]) for d in ds])
        o = np.argsort(self.x)
        self.x = self.x[o]
        shrink = 1.0 if avg <= 1 else 1.25 / np.sqrt(avg)  # running median of avg windows
        med, spr = [], []
        for d in np.array(ds)[o]:
            md = duty == d
            v = F[md]
            m = np.nanmedian(v, 0)
            sw = []
            per = []
            for s_ in np.unique(sess[md]):
                vs = F[md & (sess == s_)]
                if len(vs) >= max(5, 20 // SUBSAMPLE):  # enough windows for a within-session spread
                    ms = np.nanmedian(vs, 0)
                    per.append(ms)
                    sw.append(1.4826 * np.nanmedian(np.abs(vs - ms), 0))
            s_w = np.nanmedian(sw, 0) if sw else 1.4826 * np.nanmedian(np.abs(v - m), 0)
            s_b = np.nanstd(per, 0, ddof=1) if len(per) > 1 else np.zeros(F.shape[1])
            med.append(m)
            spr.append(np.maximum(np.sqrt((s_w * shrink) ** 2 + s_b ** 2), SPREAD_FLOOR))
        self.med, self.spr = np.array(med), np.array(spr)

    def __call__(self, F, lr):
        Z = np.empty_like(F, dtype=float)
        for j in range(F.shape[1]):
            Z[:, j] = (F[:, j] - np.interp(lr, self.x, self.med[:, j])) / np.interp(lr, self.x, self.spr[:, j])
        return np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)


def running_median(Z, groups, k):
    if k <= 1:
        return Z
    out = Z.copy()
    for g in np.unique(groups):
        idx = np.nonzero(groups == g)[0]
        for n, i in enumerate(idx):
            out[i] = np.median(Z[idx[max(0, n - k + 1):n + 1]], 0)
    return out


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


SUBSAMPLE = 1  # --subsample k: keep every k-th row (8 with 512-sample rows = non-overlapping 4096 windows)


def gather(tabs, sel, set_name, duties):
    F, lr, duty, grp, ss, ip = [], [], [], [], [], []
    for i in sel:
        t = tabs[i]
        m = t["settled"] & t.get("settled_long", True) & np.isfinite(t["rpm"]) & np.isin(t["pwm"], duties)
        m &= np.arange(len(m)) % SUBSAMPLE == 0
        F.append(feature_sets(t)[set_name][m])
        lr.append(np.log10(t["rpm"][m]))
        duty.append(t["pwm"][m])
        grp.append(i * 10000 + t["pwm"][m])
        ss.append(np.full(m.sum(), i))
        ip.append(np.column_stack([t["acc_axis"][m][:, a, 1] for a in INPLANE]))
    return (np.vstack(F), np.concatenate(lr), np.concatenate(duty), np.concatenate(grp),
            np.concatenate(ss), np.vstack(ip))


def evaluate(tabs, train_idx, th_idx, test_idx, duties, set_name, avg, seeds, lodo_duties=()):
    """False alarms and synthetic-fault detection for one split; leave-one-duty-out if lodo_duties."""
    tr = gather(tabs, train_idx, set_name, duties)
    th = gather(tabs, [th_idx], set_name, duties)
    te = gather(tabs, test_idx, set_name, duties)
    norm = SpeedNorm(tr[0], tr[1], tr[2], tr[4], avg)
    Ztr = running_median(norm(tr[0], tr[1]), tr[3], avg)
    Zth = running_median(norm(th[0], th[1]), th[3], avg)
    Zte = running_median(norm(te[0], te[1]), te[3], avg)
    inj = (te[2] >= 400) & (te[2] <= 800)  # synthetic in-plane 1x faults on test windows at 40-80 %
    dets = detectors(Ztr, seeds)
    row = {}
    for dname, score in dets.items():
        thr = np.quantile(score(Zth), 0.99)
        s_te = score(Zte)
        r = {"threshold": float(thr), "FA_test": float((s_te > thr).mean()),
             "FA_per_duty": {int(d): round(100 * float((s_te[te[2] == d] > thr).mean()), 2) for d in np.unique(te[2])}}
        for fac in (1.25, 1.5, 2.0):
            Fi = inject(set_name, te[0], te[5], inj, fac)
            if Fi is not None:
                hit = score(running_median(norm(Fi, te[1]), te[3], avg)) > thr
                r[f"detect_x{fac}"] = float(hit[inj].mean())
                r[f"detect_x{fac}_per_duty"] = {int(d): round(100 * float(hit[inj & (te[2] == d)].mean()), 1)
                                                for d in np.unique(te[2][inj])}
        row[dname] = r
    lodo = {}
    for d in lodo_duties:  # leave-one-duty-out false alarms (unseen speed)
        keep = tr[2] != d
        if keep.sum() < 100 or not (te[2] == d).any():
            continue
        n2 = SpeedNorm(tr[0][keep], tr[1][keep], tr[2][keep], tr[4][keep], avg)
        Z2 = running_median(n2(tr[0][keep], tr[1][keep]), tr[3][keep], avg)
        kth = th[2] != d
        Z2th = running_median(n2(th[0][kth], th[1][kth]), th[3][kth], avg)
        Z2te = running_median(n2(te[0], te[1]), te[3], avg)
        d2 = detectors(Z2, 1)
        for dname in ("max|z|", "Mahalanobis", "AE seed 0"):
            thr = np.quantile(d2[dname](Z2th), 0.99)
            lodo.setdefault(dname, {})[d] = round(100 * float((d2[dname](Z2te)[te[2] == d] > thr).mean()), 2)
    return row, lodo


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
                for metric in ("FA_test", "detect_x1.25", "detect_x1.5", "detect_x2.0"):
                    v = np.array([np.mean([r[k][metric] for k in ks]) for r in runs]) * 100
                    stats[metric] = [float(v.mean()), float(v.min()), float(v.max())]
                pd = {}
                for d in runs[0][ks[0]]["detect_x1.5_per_duty"]:
                    pd[d] = float(np.mean([r[k]["detect_x1.5_per_duty"].get(d, np.nan) for r in runs for k in ks]))
                stats["detect_x1.5_per_duty"] = pd
                out[key][g] = stats
                print(f"  {g:12s} FA {stats['FA_test'][0]:5.2f} [{stats['FA_test'][1]:.2f}-{stats['FA_test'][2]:.2f}] %"
                      + "   detect x1.25/1.5/2: " + " / ".join(
                          f"{stats[m][0]:5.1f} [{stats[m][1]:.0f}-{stats[m][2]:.0f}]"
                          for m in ("detect_x1.25", "detect_x1.5", "detect_x2.0"))
                      + "   x1.5 by duty: " + " ".join(f"{d // 10}%:{v:.0f}" for d, v in pd.items()))
    return out


def main():
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
    ap.add_argument("--subsample", type=int, default=1, help="keep every k-th window row (emulates a longer hop)")
    args = ap.parse_args()
    global SPREAD_FLOOR, SUBSAMPLE
    SPREAD_FLOOR = args.spread_floor
    SUBSAMPLE = args.subsample
    a, b, c = (int(v) for v in args.duties.split(":"))
    duties = tuple(range(a, b + 1, c))
    lo, hi = (int(v) for v in args.lodo.split(":"))
    lodo_duties = [d for d in duties if lo <= d <= hi]
    tabs = load()
    n = len(tabs)
    ntr = max(3, int(round(args.train_frac * n)))
    # Threshold session: the last sweep-type session (all duties) in the training block, held out.
    sweepish = [i for i in range(ntr) if str(tabs[i]["profile"]) in ("speed_sweep", "speed_sweep_fine", "mount_check")]
    th_idx = sweepish[-1] if sweepish else ntr - 1
    train_idx = [i for i in range(ntr) if i != th_idx]
    test_idx = list(range(ntr, n))
    print(f"{n} sessions; train {len(train_idx)}, threshold session {tabs[th_idx]['name']} "
          f"({tabs[th_idx]['profile']}), test {len(test_idx)}; duties {duties}, left out in turn {lodo_duties}")
    if args.rotate:
        print(f"rotating the threshold session over {[str(tabs[i]['name']) for i in sweepish]}")
        res = rotate(tabs, ntr, sweepish, test_idx, duties, sorted({1, args.avg}), args.seeds)
        res["_config"] = {"duties": list(duties), "avg": args.avg, "seeds": args.seeds, "spread_floor": SPREAD_FLOOR,
                          "subsample": SUBSAMPLE,
                          "long_windows": "acc_axis_long" in tabs[0], "rotate": True,
                          "threshold_sessions": [str(tabs[i]["name"]) for i in sweepish],
                          "test": [str(tabs[i]["name"]) for i in test_idx]}
        out = OUT / f"feature_eval{'_' + args.tag if args.tag else ''}.json"
        out.write_text(json.dumps(res, indent=1))
        print("\nwrote", out)
        return
    res = {}
    for avg in sorted({1, args.avg}):
        for set_name in feature_sets(tabs[0]):
            row, lodo = evaluate(tabs, train_idx, th_idx, test_idx, duties, set_name, avg, args.seeds, lodo_duties)
            res[f"{set_name} | avg {avg}"] = {"detectors": row, "leave_one_duty_out_FA_pct": lodo}
            # print compact
            print(f"\n== {set_name} | running median of {avg} window(s)")
            ae_keys = [k for k in row if k.startswith("AE")]
            for dname in ("max|z|", "Mahalanobis"):
                r = row[dname]
                print(f"  {dname:12s} thr {r['threshold']:7.2f}  FA {100 * r['FA_test']:5.2f} %   detect x1.25/1.5/2: "
                      + " / ".join(f"{100 * r.get(f'detect_x{f}', np.nan):5.1f}" for f in (1.25, 1.5, 2.0))
                      + f"   unseen-duty FA {lodo.get(dname)}")
            fa = [row[k]["FA_test"] for k in ae_keys]
            det = {f: [row[k].get(f"detect_x{f}", np.nan) for k in ae_keys] for f in (1.25, 1.5, 2.0)}
            print(f"  {'AE (' + str(len(ae_keys)) + ' seeds)':12s} FA {100 * np.mean(fa):5.2f}±{100 * np.std(fa):.2f} %   detect x1.25/1.5/2: "
                  + " / ".join(f"{100 * np.mean(det[f]):5.1f}" for f in (1.25, 1.5, 2.0))
                  + f"   unseen-duty FA {lodo.get('AE seed 0')}")
    res["_config"] = {"duties": list(duties), "lodo": lodo_duties, "avg": args.avg, "seeds": args.seeds,
                      "spread_floor": SPREAD_FLOOR, "long_windows": "acc_axis_long" in tabs[0],
                      "threshold_session": str(tabs[th_idx]["name"]),
                      "train": [str(tabs[i]["name"]) for i in train_idx],
                      "test": [str(tabs[i]["name"]) for i in test_idx]}
    out = OUT / f"feature_eval{'_' + args.tag if args.tag else ''}.json"
    out.write_text(json.dumps(res, indent=1))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
