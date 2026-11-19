"""One-line health check of a finished campaign session against the campaign's first mount check.

usage: python host/analysis/session_check.py <session_dir>
Needs the session's window table (windows.py) under ANALYSIS_OUT. Prints one line starting with
SESSIONCHECK, ending in OK or WARN(reasons), then a few detail lines.
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight"))
L = lambda v: np.log10(np.maximum(v, 1e-9))  # noqa: E731


def feats(t):
    return {
        "acc1": t["acc_ord"][:, 0], "acc1_x": t["acc_1x_axis"][:, 0], "acc1_y": t["acc_1x_axis"][:, 1],
        "acc1_z": t["acc_1x_axis"][:, 2], "gyr1": t["gyr_ord"][:, 0], "mag2": t["mag_ord"][:, 1],
        "aud7": t["aud_ord"][:, 6], "acc_hf": t["acc_hf"],
    }


def per_duty(t):
    F = feats(t)
    out = {}
    for d in sorted(set(t["pwm"][t["settled"]]) - {-1}):
        m = t["settled"] & (t["pwm"] == d)
        if m.sum() < 20:
            continue
        out[int(d)] = {"rpm": float(np.median(t["rpm"][m])), "n": int(m.sum()),
                       **{k: float(np.nanmedian(L(v[m]))) for k, v in F.items()}}
    return out


sd = Path(sys.argv[1])
summ = json.loads((sd / "summary.json").read_text())
meta = json.loads((sd / "meta.json").read_text())
t = dict(np.load(OUT / "windows" / f"{sd.name}.npz", allow_pickle=True))
label = str(meta.get("notes", "")).split("[campaign")[-1].strip(" ]") or str(t["profile"])

warn = []
# ---- data quality ----
q = {k: summ.get(k, 0) for k in ("crc_errors", "frames_lost", "imu_overruns", "audio_dropped")}
gaps = sum(len(summ.get(k, [])) for k in ("imu_gaps", "gyro_gaps", "mag_gaps"))
if q["crc_errors"] or q["frames_lost"] or q["imu_overruns"] or gaps:
    warn.append(f"data loss {q} gaps={gaps}")
if q["audio_dropped"] > 512:
    warn.append(f"audio dropped {q['audio_dropped']}")
z = np.load(sd / "session.npz")
if "status_tach_rejected" in z.files:
    rej = z["status_tach_rejected"].astype(float)
    pulses = z["status_tach_pulses"].astype(float)
    rej_rate = (rej[-1] - rej[0]) / max(1.0, pulses[-1] - pulses[0])
    if rej_rate > 0.05:
        warn.append(f"tach rejects {100 * rej_rate:.1f}% of pulses")
else:
    rej_rate = float("nan")

# ---- reference: first mount check of this campaign (same mount) ----
cands = []
for f in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
    r = np.load(f, allow_pickle=True)
    if "campaign" in str(r["notes"]) and str(r["profile"]) == "mount_check":
        cands.append(f)
ref_name = Path(cands[0]).stem if cands else None
lines = []
if ref_name and ref_name != sd.name:
    ref = per_duty(dict(np.load(cands[0], allow_pickle=True)))
    cur = per_duty(t)
    for d, c in cur.items():
        if d not in ref:
            continue
        r = ref[d]
        dr = 100 * (c["rpm"] / r["rpm"] - 1)
        ch = {k: 100 * (10 ** (c[k] - r[k]) - 1) for k in ("acc1", "acc1_x", "acc1_z", "gyr1", "mag2", "aud7", "acc_hf")}
        lines.append(f"   {d // 10:3d}%: rpm {c['rpm']:6.0f} ({dr:+.1f}%) | " + " ".join(f"{k} {v:+.0f}%" for k, v in ch.items()))
        if abs(dr) > 2:
            warn.append(f"rpm {dr:+.1f}% at {d // 10}%")
        # Flag big changes at 50-80 % duty, where the healthy baseline is steady.
        if 500 <= d <= 800:
            for k in ("acc1", "gyr1"):
                if abs(ch[k]) > 30:
                    warn.append(f"{k} {ch[k]:+.0f}% at {d // 10}%")

# ---- impulsive disturbances ----
hf = t["acc_hf"]
ev = 0
for d in set(t["pwm"][t["settled"]]) - {-1}:
    m = t["settled"] & (t["pwm"] == d)
    if m.sum() > 30:
        med = np.median(hf[m])
        mad = np.median(np.abs(hf[m] - med)) + 1e-12
        ev += int(((hf[m] - med) / (1.4826 * mad) > 8).sum())
temp = np.nanmedian(t["temp"])
verdict = "OK" if not warn else "WARN(" + "; ".join(warn) + ")"
print(f"SESSIONCHECK {label} {sd.name}: {len(t['tc'])} windows, temp {temp:.1f}C, bumps {ev}, "
      f"tach rejects {100 * rej_rate:.2f}%, vs {ref_name or 'no reference yet'}: {verdict}", flush=True)
for line in lines:
    print(line, flush=True)
