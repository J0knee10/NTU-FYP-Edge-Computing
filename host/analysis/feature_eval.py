"""Feature-set and detector evaluation with session-level validation (step 1 groundwork).

usage: python host/analysis/feature_eval.py [--seeds 5] [--avg 8]

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
- **Unseen speeds.** Leave one duty (40-80 %) out of training, then test false alarms at that duty.
- **Synthetic faults.** Multiply the in-plane accelerometer 1x (board x and z) of test windows at 40-80 %
  by 1.25 / 1.5 / 2 (and optionally gyro 1x too), then count detections at the same threshold.
- **Detectors** on the residuals: max |z|, Mahalanobis distance, and the MLP autoencoder (several seeds).
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
    return {
        "A  48 fixed-Hz bands": np.asarray(t["X48"], float),
        "O  11 order features (accel+gyro, per axis)": compact,
        "O+ O plus audio 7x": np.column_stack([compact, L(t["aud_ord"][:, 6])]),
        "Oall all orders (acc 1-9, gyro 1-6, mag 1-3)": np.column_stack(
            [L(t["acc_ord"][:, :9]), L(t["gyr_ord"][:, :6]), L(t["mag_ord"][:, :3])]),
    }


DUTIES = (300, 400, 500, 600, 700, 800)  # 90-100 % excluded: tapeCorner rocked there (a different regime)


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
                if len(vs) >= 20:
                    ms = np.nanmedian(vs, 0)
                    per.append(ms)
                    sw.append(1.4826 * np.nanmedian(np.abs(vs - ms), 0))
            s_w = np.nanmedian(sw, 0) if sw else 1.4826 * np.nanmedian(np.abs(v - m), 0)
            s_b = np.nanstd(per, 0, ddof=1) if len(per) > 1 else np.zeros(F.shape[1])
            med.append(m)
            spr.append(np.maximum(np.sqrt((s_w * shrink) ** 2 + s_b ** 2), 1e-3))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--avg", type=int, default=8)
    ap.add_argument("--train-frac", type=float, default=0.6)
    args = ap.parse_args()
    tabs = load()
    n = len(tabs)
    ntr = max(3, int(round(args.train_frac * n)))
    # Threshold session: the last sweep-type session (all duties) in the training block, held out.
    sweepish = [i for i in range(ntr) if str(tabs[i]["profile"]) in ("speed_sweep", "mount_check")]
    th_idx = sweepish[-1] if sweepish else ntr - 1
    train_idx = [i for i in range(ntr) if i != th_idx]
    test_idx = list(range(ntr, n))
    print(f"{n} sessions; train {len(train_idx)}, threshold session {tabs[th_idx]['name']} "
          f"({tabs[th_idx]['profile']}), test {len(test_idx)}")
    res = {}
    for avg in sorted({1, args.avg}):
        for set_name in feature_sets(tabs[0]):
            def gather(sel):
                F, lr, duty, grp, ss, ip = [], [], [], [], [], []
                for i in sel:
                    t = tabs[i]
                    m = t["settled"] & np.isfinite(t["rpm"]) & np.isin(t["pwm"], DUTIES)
                    F.append(feature_sets(t)[set_name][m])
                    lr.append(np.log10(t["rpm"][m]))
                    duty.append(t["pwm"][m])
                    grp.append(i * 10000 + t["pwm"][m])
                    ss.append(np.full(m.sum(), i))
                    ip.append(np.column_stack([t["acc_axis"][m][:, a, 1] for a in INPLANE]))
                return (np.vstack(F), np.concatenate(lr), np.concatenate(duty), np.concatenate(grp),
                        np.concatenate(ss), np.vstack(ip))

            tr = gather(train_idx)
            th = gather([th_idx])
            te = gather(test_idx)
            norm = SpeedNorm(tr[0], tr[1], tr[2], tr[4], avg)
            Ztr = running_median(norm(tr[0], tr[1]), tr[3], avg)
            Zth = running_median(norm(th[0], th[1]), th[3], avg)
            Zte = running_median(norm(te[0], te[1]), te[3], avg)
            # synthetic in-plane 1x faults on test windows at 40-80 %
            inj = np.isin(te[2], [400, 500, 600, 700, 800])
            Fte_raw = te[0]
            dets = detectors(Ztr, args.seeds)
            row = {}
            for dname, score in dets.items():
                thr = np.quantile(score(Zth), 0.99)
                s_te = score(Zte)
                r = {"threshold": float(thr), "FA_test": float((s_te > thr).mean()),
                     "FA_per_duty": {int(d): round(100 * float((s_te[te[2] == d] > thr).mean()), 2) for d in np.unique(te[2])}}
                for fac in (1.25, 1.5, 2.0):
                    Fi = inject(set_name, Fte_raw, te[5], inj, fac)
                    if Fi is not None:
                        Zi = running_median(norm(Fi, te[1]), te[3], avg)
                        r[f"detect_x{fac}"] = float((score(Zi)[inj] > thr).mean())
                row[dname] = r
            # leave-one-duty-out false alarms (unseen speed)
            lodo = {}
            for d in (400, 500, 600, 700, 800):
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
    (OUT / "feature_eval.json").write_text(json.dumps(res, indent=1))
    print("\nwrote", OUT / "feature_eval.json")


if __name__ == "__main__":
    main()
