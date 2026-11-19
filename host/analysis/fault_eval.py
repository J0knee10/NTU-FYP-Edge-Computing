"""Score real fault blocks with detectors trained on a healthy campaign (secondary A-B-A analysis).

usage: ANALYSIS_OUT=results/own/abtest_<date> python host/analysis/fault_eval.py --train results/own/flat4_healthy
           [--avg 8] [--seeds 3] [--exclude 094906 ...] [--tag name]

Training: every campaign table in --train (with long-window sidecars), the same method as feature_eval.py
(speed-conditioned normalisation, running median of `avg` windows). The alert threshold is the 99th percentile
of a held-out sweep-type session; it is rotated over every sweep-type session and the results averaged.
Test: every table in ANALYSIS_OUT/windows (the A and B blocks; build them first with windows.py and
long_windows.py). Reports, per block and duty, the % of windows flagged: false alarms for A blocks, detection
rate for B blocks, for feature sets O (0.62 s orders) and L (5 s tach-locked orders) and each detector.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import feature_eval as fe  # noqa: E402

DUTIES = (300, 400, 500, 600, 700, 800)
SETS = ("O  11 order features (accel+gyro, per axis)", "L  11 features, 5 s tach-locked orders")


def load_dir(d, campaign_only):
    tabs = []
    for f in sorted(glob.glob(str(Path(d) / "windows" / "*.npz"))):
        z = dict(np.load(f, allow_pickle=True))
        if "acc_axis" not in z or (campaign_only and ("campaign" not in str(z["notes"])
                                                    or str(z.get("fault", "normal")) != "normal")):
            continue
        z["name"] = Path(f).stem
        side = Path(d) / "windows_long" / Path(f).name
        if side.exists():
            z.update(dict(np.load(side)))
        tabs.append(z)
    return tabs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True, help="results folder of a healthy campaign (with windows_long/)")
    ap.add_argument("--avg", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--exclude", nargs="*", default=[], help="training sessions to leave out (name substrings)")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    out_dir = Path(os.environ.get("ANALYSIS_OUT", "results/own/abtest"))
    train = [t for t in load_dir(args.train, True) if not any(e in t["name"] for e in args.exclude)]
    test = load_dir(out_dir, False)
    if not all("acc_axis_long" in t for t in train + test):
        sys.exit("run long_windows.py on both folders first")
    sweepish = [i for i, t in enumerate(train) if str(t["profile"]) in ("speed_sweep", "speed_sweep_fine", "mount_check")]
    print(f"train: {len(train)} healthy sessions, threshold rotated over {len(sweepish)}; test blocks: {len(test)}")
    res = {}
    for set_name in SETS:
        flagged = {}  # (block, detector) -> {duty: [% per rotation]}
        for th_idx in sweepish:
            tr_idx = [i for i in range(len(train)) if i != th_idx]
            tr = fe.gather(train, tr_idx, set_name, DUTIES, args.avg)
            th = fe.gather(train, [th_idx], set_name, DUTIES, args.avg)
            norm = fe.SpeedNorm(*tr)
            Ztr, Zth = norm(tr[0], tr[1]), norm(th[0], th[1])
            dets = fe.detectors(Ztr, args.seeds)
            groups = {"max|z|": ["max|z|"], "Mahalanobis": ["Mahalanobis"], "AE": [k for k in dets if k.startswith("AE")]}
            for b, t in enumerate(test):
                te = fe.gather(test, [b], set_name, DUTIES, args.avg)
                if len(te[0]) == 0:
                    continue
                Zte = norm(te[0], te[1])
                for g, ks in groups.items():
                    hits = np.mean([dets[k](Zte) > np.quantile(dets[k](Zth), 0.99) for k in ks], axis=0)
                    for d in np.unique(te[2]):
                        flagged.setdefault((t["name"], g), {}).setdefault(int(d), []).append(
                            100 * float(hits[te[2] == d].mean()))
        res[set_name] = {}
        print(f"\n== {set_name} | running median of {args.avg}: % of windows flagged (mean over thresholds)")
        duties = sorted({d for v in flagged.values() for d in v})
        print(f"{'block':>34} {'detector':>11} " + " ".join(f"{d // 10:>5}%" for d in duties))
        for t in test:
            for g in ("max|z|", "Mahalanobis", "AE"):
                v = flagged.get((t["name"], g))
                if v is None:
                    continue
                row = {d: float(np.mean(v[d])) for d in v}
                res[set_name].setdefault(t["name"], {"fault": str(t["fault"]), "severity": str(t["severity"])})[g] = row
                lab = f"{t['name'][9:15]} {t['fault']}/{t['severity']}" if g == "max|z|" else ""
                print(f"{lab:>34} {g:>11} " + " ".join(f"{row[d]:6.1f}" if d in row else f"{'-':>6}" for d in duties))
    out = out_dir / f"fault_eval{'_' + args.tag if args.tag else ''}.json"
    out.write_text(json.dumps({"train": args.train, "excluded": args.exclude, "avg": args.avg,
                               "threshold_sessions": [train[i]["name"] for i in sweepish], "results": res}, indent=1))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
