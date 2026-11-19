"""A-B-A fault test analysis (fixed in advance, before the data exists).

usage: python host/analysis/abtest.py [--inplane xz] [--fig out.png] <session_dir> ... (in recorded order)

Each session is one block (profile ab_block). Blocks with fault == normal are references (A, including
sham-touch blocks); any other block is a test (B), including the hub-mass control (fault other, no U).
Per block and duty step (settled part):
- per-axis Welch spectrum (0.2 Hz bins) of accelerometer and gyro;
- 1x RMS per axis at the step's tach speed (band +-max(0.6 Hz, 1 %)).
Primary measure: in-plane accelerometer 1x, sqrt(x^2 + z^2) for flat4 (rotor plane = board x, z).
Effect of a B block: its value / geometric mean of the nearest A block before and after it.
Null distribution: log ratios between consecutive A blocks; z = log(B/A) / max(sd, 0.02).
Combined effect per block over 50-80 %: mean of the step log ratios weighted by 1 / sd^2; its z uses the
spread of the same weighted mean over the consecutive A pairs (so a drift common to all steps is included).
Decision rule (fixed before the data): an effect counts as detected if the combined z >= 3. z is conservative:
a B between two A blocks has 3/4 of the variance of an A-to-A ratio if block noise is independent.
Severity strings like "0.1g@25mm" give unbalance U = m * r in g*mm for the dose-response.
Secondary measures, same tables: axial accel 1x (the board axis not in --inplane), accel 1x over all axes,
gyro 1x over all axes.
History: combined effect, spread floor and secondaries added 19 Nov after a healthy dry run on flat4 (the 60 %
step is speed-sensitive there and the 1x is mostly axial); NaN handling, step union, input checks and the
empirical combined null added the same day after a code review. All before any fault data.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, psd  # noqa: E402

AX = {"x": 0, "y": 1, "z": 2}
COMBINE = ("duty50", "duty60", "duty70", "duty80")  # steps pooled into one effect per block
# Floor on the A-to-A spread: with few A blocks a step can show a tiny spread by chance (z in the hundreds).
# 0.02 log10 (about 5 %) is the best step-to-step repeatability seen on healthy flat4 sweeps (19 Nov).
SD_FLOOR = 0.02
Z_DETECT = 3.0
MIN_STEP_S = 60


def good(x):
    return x is not None and np.isfinite(x) and x > 0


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
        r = {"rpm": rpm, "seconds": float(seg["t1"] - seg["t0"])}
        for name, stream, scale in (("acc", "imu", 1e3), ("gyr", "gyro", 1.0)):
            x = s.slice(stream, seg["t0"], seg["t1"])
            if x is None or len(x) < 4096 or not np.isfinite(f1):
                continue
            f, p = psd(x, s.stream_rate(stream), 4096)
            for k in (0.5, 1, 2):
                r[f"{name}{k}x"] = [band_rms(f, p[:, a], k * f1, tol) * scale for a in range(3)]
            ip = [AX[c] for c in inplane]
            ax_ = [a for a in range(3) if a not in ip]
            r[f"{name}_inplane"] = float(np.sqrt(sum(r[f"{name}1x"][a] ** 2 for a in ip)))
            r[f"{name}_axial"] = float(np.sqrt(sum(r[f"{name}1x"][a] ** 2 for a in ax_)))
            r[f"{name}_vec"] = float(np.sqrt(sum(v ** 2 for v in r[f"{name}1x"])))
        rows[seg["label"]] = {"duty": d, **r}
    prof = meta.get("profile")
    return {"name": s.dir.name, "kind": "A" if meta.get("fault") == "normal" else "B",
            "fault": str(meta.get("fault")), "severity": str(meta.get("severity")), "notes": meta.get("notes", ""),
            "mount": meta.get("mount"), "profile": prof.get("name") if isinstance(prof, dict) else prof,
            "aborted": bool(meta.get("aborted", False)), "U": unbalance(meta.get("severity")), "steps": rows}


def checks(blocks, steps):
    warn = []
    names = [b["name"] for b in blocks]
    if names != sorted(names):
        warn.append("sessions are not in time order (the nearest A before/after depends on the order given)")
    if len({b["mount"] for b in blocks}) > 1:
        warn.append(f"mixed mounts: {sorted({str(b['mount']) for b in blocks})}")
    if not any(b["kind"] == "A" for b in blocks):
        warn.append("no A blocks")
    for b in blocks:
        tag = f"{b['name']}"
        if b["profile"] != "ab_block":
            warn.append(f"{tag}: profile {b['profile']!r}, not 'ab_block'")
        if b["aborted"]:
            warn.append(f"{tag}: session was aborted")
        for k in steps:
            st = b["steps"].get(k)
            if st is None:
                warn.append(f"{tag}: step {k} missing")
            elif st["seconds"] < MIN_STEP_S:
                warn.append(f"{tag}: step {k} has only {st['seconds']:.0f} s settled")
            elif not good(st.get("acc_inplane")):
                warn.append(f"{tag}: step {k} has no valid 1x (rpm {st['rpm']})")
    return warn


def effects(blocks, steps, measure, verbose=True):
    A = [i for i, b in enumerate(blocks) if b["kind"] == "A"]
    pairs = list(zip(A[:-1], A[1:]))

    def lr_pair(i, j, k):
        a, c = blocks[i]["steps"].get(k, {}).get(measure), blocks[j]["steps"].get(k, {}).get(measure)
        return np.log10(c / a) if good(a) and good(c) else np.nan

    null = {k: [v for v in (lr_pair(i, j, k) for i, j in pairs) if np.isfinite(v)] for k in steps}
    sd_null = {k: (float(np.std(v, ddof=1)) if len(v) > 1 else np.nan) for k, v in null.items()}
    sd_use = {k: max(v, SD_FLOOR) if np.isfinite(v) else np.nan for k, v in sd_null.items()}
    w = {k: 1 / sd_use[k] ** 2 for k in COMBINE if k in sd_use and np.isfinite(sd_use[k])}

    def combine(lrs):  # weighted mean over the COMBINE steps present
        ks = [k for k in w if np.isfinite(lrs.get(k, np.nan))]
        return sum(w[k] * lrs[k] for k in ks) / sum(w[k] for k in ks) if ks else np.nan

    comb_null = [combine({k: lr_pair(i, j, k) for k in w}) for i, j in pairs]
    comb_null = [v for v in comb_null if np.isfinite(v)]
    sd_comb = max(float(np.std(comb_null, ddof=1)), SD_FLOOR) if len(comb_null) > 1 else np.nan
    if verbose:
        print(f"\nA-to-A spread of {measure} (sd of log10 ratio over {len(pairs)} pairs; z uses max(sd, {SD_FLOOR})): "
              + " ".join(f"{k} {v:.3f}" for k, v in sd_null.items()) + f" | combined {sd_comb:.3f}")
    res = []
    for i, b in enumerate(blocks):
        if b["kind"] != "B":
            continue
        cells, lrs = [], {}
        for k in steps:
            v = b["steps"].get(k, {}).get(measure)
            before = [j for j in A if j < i and good(blocks[j]["steps"].get(k, {}).get(measure))]
            after = [j for j in A if j > i and good(blocks[j]["steps"].get(k, {}).get(measure))]
            refs = ([before[-1]] if before else []) + ([after[0]] if after else [])
            if not good(v) or not refs:
                cells.append(f"{'-':>15}")
                continue
            ref = [blocks[j]["steps"][k][measure] for j in refs]
            lr = float(np.log10(v) - np.mean(np.log10(ref)))
            z = lr / sd_use[k] if np.isfinite(sd_use[k]) else np.nan
            lrs[k] = lr
            cells.append(f"x{10 ** lr:5.2f} z{z:+6.1f}")
            res.append({"measure": measure, "block": b["name"], "severity": b["severity"], "U": b["U"], "step": k,
                        "rpm": b["steps"][k]["rpm"], "value": v, "ref": float(10 ** np.mean(np.log10(ref))),
                        "ratio": float(10 ** lr), "z": z})
        c = combine(lrs)
        zc = c / sd_comb if np.isfinite(c) and np.isfinite(sd_comb) else np.nan
        res.append({"measure": measure, "block": b["name"], "severity": b["severity"], "U": b["U"],
                    "step": "combined", "ratio": float(10 ** c) if np.isfinite(c) else np.nan, "z": zc,
                    "detected": bool(np.isfinite(zc) and zc >= Z_DETECT)})
        if verbose:
            flag = "DETECTED" if np.isfinite(zc) and zc >= Z_DETECT else ""
            ctrl = " (control)" if not np.isfinite(b["U"]) else ""
            print(f"{b['name'][9:15]} {b['severity'] + ctrl:>22}: " + " ".join(cells)
                  + f"  | combined 50-80 % x{10 ** c if np.isfinite(c) else np.nan:5.2f} z{zc:+6.1f} {flag}")
    return {"null_sd": sd_null, "null_sd_combined": sd_comb, "effects": res}


def clean(o):
    """NaN -> None so the JSON is strict."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--inplane", default="xz", help="board axes in the rotor plane (flat4: xz)")
    ap.add_argument("--fig")
    ap.add_argument("--out", help="results JSON (default results/own/abtest/<first session>.json)")
    args = ap.parse_args()
    blocks = [block(sd, args.inplane) for sd in args.sessions]
    steps = sorted({k for b in blocks for k in b["steps"] if k.startswith("duty")}, key=lambda k: int(k[4:]))

    for w_ in checks(blocks, steps):
        print("WARNING:", w_)

    print("\nprimary: in-plane accel 1x RMS (mg) per block and step")
    print(f"{'block':>40} {'kind':>4} {'U g*mm':>7} " + " ".join(f"{k:>9}" for k in steps))
    for b in blocks:
        lab = f"{b['name'][9:15]} {b['fault']}/{b['severity']}"
        print(f"{lab:>40} {b['kind']:>4} {b['U']:7.2f} " + " ".join(
            f"{(b['steps'].get(k, {}).get('acc_inplane') or np.nan):9.2f}" for k in steps))

    print("\neffect of each B block: ratio to the geometric mean of the nearest A before and after (z vs A-to-A spread)")
    primary = effects(blocks, steps, "acc_inplane")
    secondary = {}
    for m in ("acc_axial", "acc_vec", "gyr_vec"):
        print(f"\nsecondary: {m}")
        secondary[m] = effects(blocks, steps, m)

    out = Path(args.out) if args.out else Path("results/own/abtest") / f"{Path(args.sessions[0]).name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clean({"blocks": blocks, "steps": steps, "warnings": checks(blocks, steps),
                                     "z_detect": Z_DETECT, "sd_floor": SD_FLOOR, **primary,
                                     "secondary": secondary}), indent=1))
    print("\nwrote", out)

    res = primary["effects"]
    if args.fig and res:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
        comb = [r for r in res if r["step"] == "combined" and np.isfinite(r["U"]) and np.isfinite(r["ratio"])]
        per = [r for r in res if r["step"] != "combined" and np.isfinite(r["U"])]
        ax[0].plot([r["U"] for r in per], [r["ratio"] for r in per], ".", color="0.6", label="single steps")
        ax[0].plot([r["U"] for r in comb], [r["ratio"] for r in comb], "o", color="k", label="combined 50-80 %")
        ax[0].axhline(1, color="0.5", lw=0.8)
        ax[0].set_xlabel("unbalance U = m r (g mm)")
        ax[0].set_ylabel("in-plane accel 1x, B / A")
        ax[0].legend(fontsize=8)
        for name in dict.fromkeys(r["block"] for r in res):  # one line per block, in order
            rr = sorted([r for r in res if r["block"] == name and r["step"] != "combined"], key=lambda r: r["rpm"])
            if rr:
                ax[1].plot([(r["rpm"] / 60 * 2 * np.pi) ** 2 for r in rr], [r["value"] - r["ref"] for r in rr], "o-",
                           label=f"{name[9:15]} {rr[0]['severity']}")
        ax[1].axhline(0, color="0.5", lw=0.8)
        ax[1].set_xlabel("omega^2 (rad^2/s^2)")
        ax[1].set_ylabel("B - A, in-plane accel 1x (mg)")
        ax[1].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(args.fig, dpi=100)
        print("figure", args.fig)


if __name__ == "__main__":
    main()
