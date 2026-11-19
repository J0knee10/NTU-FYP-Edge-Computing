"""Long tach-locked order amplitudes for every row of the window tables (sidecar files).

usage: python host/analysis/long_windows.py [--len 4096]      (reads ANALYSIS_OUT/windows/*.npz)

For each short window (row) of a session table, takes LEN IMU samples centred on it and measures per-axis
narrowband RMS at the orders AX_ORDERS (0.5, 1, 1.5, 2, 3, 7) of the tach speed, in +-2 bins (Hann), for the
accelerometer and the gyro. A long window narrows the band, so the background between orders drops as
1/sqrt(T) while a stable order line stays (see window_length.py). On the board this is a single-bin DFT per
order and axis, O(LEN). A row counts as `settled_long` only if the whole long window lies in one settled step.

Writes ANALYSIS_OUT/windows_long/<session>.npz with acc_axis_long, gyr_axis_long (n, 3, 6), settled_long (n,).
The short-window tables are not changed.
"""
import argparse
import glob
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session  # noqa: E402
from windows import AX_ORDERS, HANN_RMS, W, tach_rpm  # noqa: E402

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight"))
RAW = Path("data/raw")


def narrow_orders(x, fs, f1, orders):
    """(ch, len(orders)) RMS in +-2 bins around k * f1."""
    n = len(x)
    x = x - x.mean(0)
    P = np.abs(np.fft.rfft(x * np.hanning(n)[:, None], axis=0)) ** 2
    f = np.fft.rfftfreq(n, 1 / fs)
    out = np.full((x.shape[1], len(orders)), np.nan)
    tol = 2 * fs / n
    for i, k in enumerate(orders):
        m = np.abs(f - k * f1) <= tol
        if m.any() and k * f1 + tol < fs / 2:
            out[:, i] = HANN_RMS * np.sqrt(P[m].sum(0)) / n
    return out


def build(table, L):
    t = np.load(table, allow_pickle=True)
    name = Path(table).stem
    s = Session(RAW / name)
    fs = s.stream_rate("imu")
    n = len(t["tc"])
    acc_l = np.full((n, 3, len(AX_ORDERS)), np.nan)
    gyr_l = np.full_like(acc_l, np.nan)
    settled_l = np.zeros(n, bool)
    half_rows = L // W // 2
    pwm, settled = t["pwm"], t["settled"]
    f1 = tach_rpm(s, t["tc"], half=L / fs / 2) / 60
    for i in range(n):
        a = i * W + W // 2 - L // 2
        if a < 0 or a + L > len(s.acc) or not np.isfinite(f1[i]):
            continue
        lo, hi = i - half_rows, i + half_rows - 1
        if lo >= 0 and hi < n:
            settled_l[i] = bool(settled[lo:hi + 1].all() and (pwm[lo:hi + 1] == pwm[i]).all())
        acc_l[i] = narrow_orders(s.acc[a:a + L], fs, f1[i], AX_ORDERS)
        gyr_l[i] = narrow_orders(s.gyro[a:a + L], fs, f1[i], AX_ORDERS)
    return acc_l, gyr_l, settled_l


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--len", type=int, default=4096)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out = OUT / "windows_long"
    out.mkdir(parents=True, exist_ok=True)
    for table in sorted(glob.glob(str(OUT / "windows" / "*.npz"))):
        dst = out / Path(table).name
        if dst.exists() and not args.force:
            continue
        if not (RAW / Path(table).stem).exists():
            print("no raw session for", Path(table).stem)
            continue
        acc_l, gyr_l, settled_l = build(table, args.len)
        np.savez_compressed(dst, acc_axis_long=acc_l, gyr_axis_long=gyr_l, settled_long=settled_l,
                            long_len=args.len)
        print(f"{Path(table).stem}: {settled_l.sum()} settled long windows of {len(settled_l)}", flush=True)


if __name__ == "__main__":
    main()
