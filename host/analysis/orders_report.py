"""Which sensors see the fan? Order SNR per step, per sensor, for one session.

usage: python orders_report.py <session_dir> [--fig out.png]
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import Session, corruption, order_snr, psd  # noqa: E402

sd = sys.argv[1]
s = Session(sd)
print(f"{s.dir.name}: profile={s.meta['profile'].get('name')} rates imu={s.rate['imu']:.1f} "
      f"mag={s.rate['mag']:.1f} audio={s.rate['audio']:.0f} Hz")
sm = s.summary
print(f"quality: crc={sm['crc_errors']} lost={sm['frames_lost']} imu_overruns={sm['imu_overruns']} "
      f"mag_overruns={sm.get('mag_overruns')} audio_dropped={sm['audio_dropped']} "
      f"gaps imu/gyro/mag={len(sm['imu_gaps'])}/{len(sm.get('gyro_gaps', []))}/{len(sm.get('mag_gaps', []))} "
      f"corrupted_acc={corruption(s.z['imu_counts'])}")

streams = [("acc", "imu", 4096), ("gyro", "gyro", 4096), ("mag", "mag", 2048), ("audio", "audio", 16384)]
rows = []
for seg in s.segments:
    r = s.rpm(seg["t0"], seg["t1"])
    f1 = r / 60
    row = dict(label=seg["label"], pwm=seg["pwm"], rpm=r, f1=f1, spec={})
    for name, stream, nper in streams:
        x = s.slice(stream, seg["t0"], seg["t1"])
        if x is None or len(x) < nper:
            continue
        fs = s.stream_rate(stream)
        f, p = psd(x, fs, nper)
        ptot = p.sum(1)
        fmax = 400 if name in ("acc", "gyro") else (fs / 2 * 0.95 if name == "mag" else 3000)
        snr = order_snr(f, ptot, f1, orders=range(1, 41 if name == "audio" else 17), fmax=fmax)
        rms = np.sqrt(((x - x.mean(0)) ** 2).mean(0))
        row["spec"][name] = dict(f=f, p=ptot, snr=snr, rms=rms)
    rows.append(row)

for name, *_ in streams:
    print(f"\n== {name}: dB above floor at rotation orders (top 6 per step)")
    for row in rows:
        d = row["spec"].get(name)
        if not d:
            continue
        top = sorted(((k, v) for k, v in d["snr"].items() if np.isfinite(v)), key=lambda kv: -kv[1])[:6]
        rms = d["rms"]
        rms_s = "/".join(f"{v:.3g}" for v in np.atleast_1d(rms))
        print(f"  {row['label']:>9} {row['rpm']:6.0f} rpm  rms {rms_s:<24} "
              + "  ".join(f"{k}x:{v:4.1f}" for k, v in top))

if "--fig" in sys.argv:
    out = sys.argv[sys.argv.index("--fig") + 1]
    fig, ax = plt.subplots(4, 1, figsize=(12, 14))
    for a, (name, *_ ) in zip(ax, streams):
        for row in rows:
            d = row["spec"].get(name)
            if d:
                a.semilogy(d["f"] / row["f1"], d["p"], lw=0.7, label=f"{row['label']} {row['rpm']:.0f}")
        a.set_xlim(0, 40 if name == "audio" else 16)
        a.set_xticks(range(0, 41 if name == "audio" else 17, 2 if name == "audio" else 1))
        a.grid(alpha=0.3)
        a.set_title(f"{name}: spectrum vs rotation order", fontsize=10)
    ax[0].legend(fontsize=6, ncol=5)
    ax[-1].set_xlabel("order (f / rotation frequency)")
    fig.tight_layout()
    fig.savefig(out, dpi=100)
    print("figure", out)
