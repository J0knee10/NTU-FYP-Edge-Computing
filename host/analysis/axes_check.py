"""Which board axes carry the 1x and 0.5x motion? (accel per axis, gyro per axis), plus gravity."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, order_amp, psd  # noqa: E402

s = Session(sys.argv[1])
w = np.load(Path("results/own/overnight/windows") / f"{s.dir.name}.npz", allow_pickle=True)
print("gravity (g):", np.round(s.acc.mean(0), 3))
for seg in s.segments:
    if seg["pwm"] not in (400, 700, 900, 1000) or not str(seg["label"]).startswith("duty"):
        continue
    m = (w["tc"] > seg["t0"]) & (w["tc"] < seg["t1"]) & w["settled"]
    f1 = float(np.median(w["rpm"][m])) / 60
    row = []
    for name, stream in (("acc mg", "imu"), ("gyro mdps", "gyro")):
        x = s.slice(stream, seg["t0"], seg["t1"])
        f, p = psd(x, s.rate["imu"], 4096)
        for k in (0.5, 1, 2):
            a = [order_amp(f, p[:, ax], f1, k, tol_hz=0.6) * 1000 for ax in range(3)]
            row.append(f"{name} {k}x " + "/".join(f"{v:6.2f}" for v in a))
    print(f"pwm {seg['pwm']} ({f1 * 60:.0f} rpm):")
    for r in row:
        print("   x/y/z", r)
