"""True rotation frequency from spectra (gyro 1x, audio 7x) vs tach-derived references."""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import welch

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session  # noqa: E402

s = Session(sys.argv[1])
strm = (s.st["flags"] & 1).astype(bool)
t = s.st_t[strm]
P = s.st["tach_pulses"].astype(float)[strm]
per = s.st["tach_period_us"].astype(float)[strm]
for seg in s.segments:
    m = (t > seg["t0"]) & (t < seg["t1"])
    if m.sum() < 40:
        continue
    tach_mean = (P[m][-1] - P[m][0]) / 2 / (t[m][-1] - t[m][0]) * 60
    pr = per[m][per[m] > 0]
    per_med = 60e6 / (2 * np.median(pr))
    g = s.slice("gyro", seg["t0"], seg["t1"])
    f, p = welch(g - g.mean(0), fs=s.rate["imu"], nperseg=16384, axis=0)
    p = p.sum(1)
    exp = tach_mean / 60
    band = (f > 0.8 * exp) & (f < 1.2 * exp)
    fg = f[band][np.argmax(p[band])]
    a = s.slice("audio", seg["t0"], seg["t1"])
    fa, pa = welch(a - a.mean(), fs=s.rate["audio"], nperseg=65536)
    band = (fa > 0.9 * 7 * exp) & (fa < 1.1 * 7 * exp)
    f7 = fa[band][np.argmax(pa[band])] / 7
    # period histogram: two half-period populations?
    q = np.percentile(pr, [5, 25, 50, 75, 95])
    print(f"pwm {seg['pwm']}: tach mean {tach_mean:7.1f} rpm | median-period {per_med:7.1f} | gyro 1x peak {fg * 60:7.1f} | "
          f"audio 7x/7 {f7 * 60:7.1f} | period pct us {np.round(q).astype(int)}")
