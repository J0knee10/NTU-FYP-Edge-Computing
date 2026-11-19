"""A-B-A fault test analysis (fixed in advance, before the data exists).

usage: python host/analysis/abtest.py [--inplane xz] [--fig out.png] <session_dir> ... (in recorded order)

Each session is one block (profile ab_block). Blocks with fault == normal are references (A, including
sham-touch blocks); any other block is a test (B). Per block and duty step (settled part):
- per-axis Welch spectrum (0.2 Hz bins) of accelerometer and gyro;
- 1x RMS per axis at the step's tach speed (band +-max(0.6 Hz, 1 %)).
Primary measure: in-plane accelerometer 1x, sqrt(x^2 + z^2) for flat4 (rotor plane = board x, z).
Effect of a B block: its value / geometric mean of the nearest A block before and after it.
Null distribution: ratios between consecutive A blocks; z = log(B/A) / sd(log A-to-A ratios).
Severity strings like "0.1g@25mm" give unbalance U = m * r in g*mm for the dose-response.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, psd  # noqa: E402

AX = {"x": 0, "y": 1, "z": 2}


def band_rms(f, p, fc, tol):
    m = (f > fc - tol) & (f < fc + tol)
    return float(np.sqrt(p[m].sum() * (f[1] - f[0]))) if m.any() else np.nan


def unbalance(sev):
    m = re.match(r"([\d.]+)\s*g\s*@\s*([\d.]+)\s*mm", str(sev))
    return float(m.group(1)) * float(m.group(2)) if m else np.nan


def block(sd, inplane):
    s = Session(sd)
    meta = s.meta
    rows = {}
    for seg in s.segments:
        d = seg["pwm"]
        if d is None:
            continue
        rpm = s.rpm(seg["t0"], seg["t1"])
        f1 = rpm / 60
        tol = max(0.6, 0.01 * f1)
        r = {"rpm": rpm}
        for name, stream, scale in (("acc", "imu", 1e3), ("gyr", "gyro", 1.0)):
            x = s.slice(stream, seg["t0"], seg["t1"])
            if x is None or len(x) < 4096:
                continue
            f, p = psd(x, s.stream_rate(stream), 4096)
            for k in (0.5, 1, 2):
                v = [band_rms(f, p[:, a], k * f1, tol) * scale for a in range(3)]
                r[f"{name}{k}x"] = v
            ip = [AX[c] for c in inplane]
            r[f"{name}_inplane"] = float(np.sqrt(sum(r[f"{name}1x"][a] ** 2 for a in ip)))
        key = seg["label"]
        rows[key] = {"duty": d, **r}
    kind = "A" if meta.get("fault") == "normal" else "B"
    return {"name": s.dir.name, "kind": kind, "fault": meta.get("fault"), "severity": meta.get("severity"),
            "notes": meta.get("notes", ""), "U": unbalance(meta.get("severity")), "steps": rows}


ap = argparse.ArgumentParser()
ap.add_argument("sessions", nargs="+")
ap.add_argument("--inplane", default="xz", help="board axes in the rotor plane (flat4: xz)")
ap.add_argument("--fig")
ap.add_argument("--out", help="results JSON (default results/own/abtest/<first session>.json)")
args = ap.parse_args()
blocks = [block(sd, args.inplane) for sd in args.sessions]
steps = [k for k in blocks[0]["steps"] if k.startswith("duty")]

print("primary: in-plane accel 1x RMS (mg) per block and step")
print(f"{'block':>36} {'kind':>4} {'U g*mm':>7} " + " ".join(f"{k:>9}" for k in steps))
for b in blocks:
    lab = f"{b['name'][9:15]} {b['fault']}/{b['severity']}"
    print(f"{lab:>36} {b['kind']:>4} {b['U']:7.2f} " + " ".join(
        f"{b['steps'].get(k, {}).get('acc_inplane', np.nan):9.2f}" for k in steps))

# null: consecutive A-to-A log ratios
A = [i for i, b in enumerate(blocks) if b["kind"] == "A"]
null = {k: [] for k in steps}
for i, j in zip(A[:-1], A[1:]):
    for k in steps:
        a, c = blocks[i]["steps"].get(k, {}).get("acc_inplane"), blocks[j]["steps"].get(k, {}).get("acc_inplane")
        if a and c:
            null[k].append(np.log10(c / a))
sd_null = {k: (float(np.std(v, ddof=1)) if len(v) > 1 else np.nan) for k, v in null.items()}
print("\nA-to-A spread (sd of log10 ratio): " + " ".join(f"{k} {v:.3f}" for k, v in sd_null.items()))

print("\neffect of each B block: ratio to the geometric mean of the nearest A before and after (z vs A-to-A spread)")
results = []
for i, b in enumerate(blocks):
    if b["kind"] != "B":
        continue
    before = [j for j in A if j < i]
    after = [j for j in A if j > i]
    refs = ([before[-1]] if before else []) + ([after[0]] if after else [])
    cells = []
    for k in steps:
        v = b["steps"].get(k, {}).get("acc_inplane")
        ref = [blocks[j]["steps"].get(k, {}).get("acc_inplane") for j in refs]
        ref = [r for r in ref if r]
        if not v or not ref:
            cells.append(f"{'-':>15}")
            continue
        lr = np.log10(v) - np.mean(np.log10(ref))
        z = lr / sd_null[k] if np.isfinite(sd_null[k]) and sd_null[k] > 0 else np.nan
        cells.append(f"x{10 ** lr:5.2f} z{z:+6.1f}")
        results.append({"block": b["name"], "severity": b["severity"], "U": b["U"], "step": k,
                        "rpm": b["steps"][k]["rpm"], "ratio": float(10 ** lr), "z": float(z)})
    print(f"{b['name'][9:15]} {b['severity']:>12}: " + " ".join(cells))

out = Path(args.out) if args.out else Path("results/own/abtest") / f"{Path(args.sessions[0]).name}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"blocks": blocks, "null_sd": sd_null, "effects": results}, indent=1, default=float))
print("\nwrote", out)

if args.fig and results:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for k in steps:
        rr = [r for r in results if r["step"] == k and np.isfinite(r["U"])]
        if rr:
            ax[0].plot([r["U"] for r in rr], [r["ratio"] for r in rr], "o", label=k)
    ax[0].axhline(1, color="0.5", lw=0.8)
    ax[0].set_xlabel("unbalance U = m r (g mm)")
    ax[0].set_ylabel("in-plane accel 1x, B / A")
    ax[0].legend(fontsize=8)
    for sev in sorted({r["severity"] for r in results}):
        rr = sorted([r for r in results if r["severity"] == sev], key=lambda r: r["rpm"])
        ax[1].plot([(r["rpm"] / 60 * 2 * np.pi) ** 2 for r in rr], [r["ratio"] for r in rr], "o-", label=sev)
    ax[1].set_xlabel("omega^2 (rad^2/s^2)")
    ax[1].set_ylabel("B / A")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.fig, dpi=100)
    print("figure", args.fig)
