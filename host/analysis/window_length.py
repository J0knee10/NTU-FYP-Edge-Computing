"""How long must a window be to measure 1x on a quiet mount? (step 1 feature design)

usage: python host/analysis/window_length.py <session_dir> ... [--inplane xz] [--out results/own/flat4_healthy/window_length.json]

For each constant-duty step (settled part) and window length T, cut non-overlapping windows and measure, per
window, the narrowband RMS at 1x of the tach speed (Hann, +-2 bins around k * f1, so the band shrinks as T
grows) on the in-plane accelerometer axes, and the same at 0.75x and 1.25x as the background between orders.
Reports, per duty and T: median 1x, median background, their ratio, and the window-to-window spread of
log10(1x). A narrow tach-locked band is cheap on the board (a single-bin DFT per order, O(n)).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session  # noqa: E402
from windows import HANN_RMS, tach_rpm  # noqa: E402

AX = {"x": 0, "y": 1, "z": 2}
LENGTHS = (512, 1024, 2048, 4096, 8192)


def narrow(x, fs, f1, k):
    """RMS per channel in +-2 bins around k * f1 (Hann)."""
    n = len(x)
    x = x - x.mean(0)
    P = np.abs(np.fft.rfft(x * np.hanning(n)[:, None], axis=0)) ** 2
    f = np.fft.rfftfreq(n, 1 / fs)
    m = np.abs(f - k * f1) <= 2 * fs / n
    return HANN_RMS * np.sqrt(P[m].sum(0)) / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--inplane", default="xz")
    ap.add_argument("--out")
    args = ap.parse_args()
    ip = [AX[c] for c in args.inplane]
    acc = {}  # (duty, T) -> lists
    for sd in args.sessions:
        s = Session(sd)
        fs = s.stream_rate("imu")
        for seg in s.segments:
            d = seg["pwm"]
            if d is None or not 300 <= d <= 1000:
                continue
            i0, i1 = s.index_at("imu", seg["t0"]), s.index_at("imu", seg["t1"])
            for T in LENGTHS:
                for a in range(i0, i1 - T + 1, T):
                    tc = seg["t0"] + (a - i0 + T / 2) / fs
                    f1 = float(tach_rpm(s, np.array([tc]), half=T / fs / 2)[0]) / 60
                    if not np.isfinite(f1):
                        continue
                    x = s.acc[a:a + T][:, ip]
                    one = np.sqrt((narrow(x, fs, f1, 1.0) ** 2).sum())
                    bg = np.sqrt(np.mean([(narrow(x, fs, f1, k) ** 2).sum() for k in (0.75, 1.25)]))
                    acc.setdefault((d, T), {"one": [], "bg": []})
                    acc[(d, T)]["one"].append(one * 1e3)
                    acc[(d, T)]["bg"].append(bg * 1e3)
    res = []
    print("duty    T(s)  n   1x mg  backgr mg  1x/bg  sd log10(1x)  z of x1.5 per window")
    for (d, T) in sorted(acc):
        one, bg = np.array(acc[(d, T)]["one"]), np.array(acc[(d, T)]["bg"])
        if len(one) < 3:
            continue
        l1 = np.log10(one)
        sd = 1.4826 * np.median(np.abs(l1 - np.median(l1)))
        r = {"duty": d, "T_samples": T, "T_s": T / 827.4, "n": len(one), "one_mg": float(np.median(one)),
             "bg_mg": float(np.median(bg)), "snr": float(np.median(one) / np.median(bg)), "sd_log10": float(sd)}
        res.append(r)
        print(f"{d:4d} {T / 827.4:6.2f} {len(one):4d} {r['one_mg']:6.2f} {r['bg_mg']:9.2f} {r['snr']:6.1f}"
              f" {sd:13.3f} {np.log10(1.5) / max(sd, 1e-3):9.1f}")
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1))
        print("wrote", args.out)


if __name__ == "__main__":
    main()
