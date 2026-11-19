"""Mount check report for one recorded session (profile mount_check).

usage: python mount_report.py data/bringup/<session>
Writes <session>/mount_report.png and prints a per-step table.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks, spectrogram, welch

SETTLE_S = 12.0  # ignore the start of each step while the fan changes speed
sd = Path(sys.argv[1])
meta = json.loads((sd / "meta.json").read_text())
z = dict(np.load(sd / "session.npz"))
events = [json.loads(line) for line in (sd / "events.jsonl").read_text().splitlines()]
rate = float(z["imu_rate_hz_est"])
acc = z["imu_counts"].astype(float) * float(z["imu_g_per_count"])
n = len(acc)
st_t = z["status_t_us"]
st_idx = z["status_imu_samples"]
rpm_st = z["status_rpm"]


def board_t_to_index(raw_t):
    """Event board_t_us (raw u32) -> IMU sample index via the matching STATUS frame."""
    k = np.nonzero((st_t % 2**32) == raw_t)[0]
    return int(st_idx[k[0]]) if len(k) else None


steps = [e for e in events if e["event"] == "step"]
end_ev = [e for e in events if e["event"] == "end"][0]
bounds = [board_t_to_index(e["board_t_us"]) for e in steps] + [n]
segs = []
for e, a, b in zip(steps, bounds[:-1], bounds[1:]):
    a2 = min(b, a + int(SETTLE_S * rate))
    segs.append(dict(label=e["label"], pwm=e["pwm"], a=a, a2=a2, b=b))

# RPM per sample from STATUS.
ok = np.isfinite(rpm_st)
rpm = np.interp(np.arange(n), st_idx[ok], rpm_st[ok])

NPER = 2048  # 0.41 Hz resolution at 833 Hz


def psd(x):
    f, p = welch(x - x.mean(axis=0), fs=rate, nperseg=NPER, axis=0)
    return f, p  # p: (freq, 3)


print(f"session {sd.name}: {n} IMU samples at {rate:.2f} Hz ({n / rate / 60:.1f} min), "
      f"mount={meta.get('mount')}, notes={meta.get('notes')!r}")
summ = json.loads((sd / "summary.json").read_text())
print(f"link: crc={summ['crc_errors']} lost={summ['frames_lost']} imu_gaps={summ['imu_gaps']} "
      f"overruns={summ['imu_overruns']} audio_dropped={summ['audio_dropped']}")
print(f"full scale +-{meta['board_info']['imu_fs_g']} g; max |a| over session = {np.abs(acc).max():.3f} g\n")

print(f"{'step':>9} {'pwm':>4} {'rpm':>6} {'1x Hz':>6} {'rms mg x/y/z':>20} {'1x SNR dB':>9} "
      f"{'strongest orders (SNR dB)':<44} {'unexplained peaks Hz'}")
table = []
all_peaks = []
for s in segs:
    x = acc[s["a2"]:s["b"]]
    if len(x) < NPER * 2:
        continue
    r = float(np.median(rpm[s["a2"]:s["b"]]))
    f1 = r / 60
    f, p = psd(x)
    ptot = p.sum(axis=1)
    band = (f >= 4) & (f <= 400)
    floor = np.median(ptot[band])
    rms = np.sqrt(((x - x.mean(axis=0)) ** 2).mean(axis=0)) * 1000

    def snr_at(freq, tol=1.0):
        m = (f > freq - tol) & (f < freq + tol)
        return 10 * np.log10(ptot[m].max() / floor) if m.any() else np.nan

    orders = {k: snr_at(k * f1) for k in range(1, 16) if k * f1 < 400}
    best = sorted(orders.items(), key=lambda kv: -kv[1])[:5]
    pk, _ = find_peaks(10 * np.log10(ptot / floor), height=12, distance=int(2 / (f[1] - f[0])))
    pk = [i for i in pk if 4 <= f[i] <= 400]
    unexplained = [round(f[i], 1) for i in pk
                   if abs(f[i] / f1 - round(f[i] / f1)) * f1 > 1.5]  # not near an integer order
    all_peaks += [(s["label"], f1, f[i], 10 * np.log10(ptot[i] / floor)) for i in pk]
    table.append(dict(**s, rpm=r, f1=f1, f=f, ptot=ptot, floor=floor, rms=rms, orders=orders))
    print(f"{s['label']:>9} {s['pwm'] / 10:3.0f}% {r:6.0f} {f1:6.1f} "
          f"{rms[0]:6.1f}/{rms[1]:6.1f}/{rms[2]:6.1f} {orders[1]:9.1f} "
          f"{', '.join(f'{k}x {v:.0f}' for k, v in best):<44} {unexplained[:6]}")

# Fixed-frequency peaks across the sweep (mount/structure resonances do not move with speed).
sweep = [t for t in table if t["label"].startswith("duty")]
cands = {}
for lab, f1, fp, snr in all_peaks:
    if not lab.startswith("duty"):
        continue
    key = round(fp / 2) * 2
    cands.setdefault(key, set()).add(lab)
fixed = sorted(k for k, labs in cands.items() if len(labs) >= max(4, len(sweep) // 2))
print(f"\npeaks at a fixed frequency in >= half the sweep steps (likely mount/structure, not the fan): "
      f"{fixed if fixed else 'none'}")

# Mount stability: gravity direction over the session (tape creep shows as a drift).
win = int(10 * rate)
g = np.array([acc[i:i + win].mean(axis=0) for i in range(0, n - win, win)])
gu = g / np.linalg.norm(g, axis=1, keepdims=True)
ang = np.degrees(np.arccos(np.clip(gu @ gu[0], -1, 1)))
print(f"gravity direction drift vs start: max {ang.max():.2f} deg, end {ang[-1]:.2f} deg "
      f"(start g = {np.round(g[0], 3)}, end g = {np.round(g[-1], 3)})")

# Hold stability: thirds of the 70 % hold.
hold = [t for t in table if t["label"] == "hold70"]
if hold:
    h = hold[0]
    L = (h["b"] - h["a2"]) // 3
    parts = []
    for k in range(3):
        x = acc[h["a2"] + k * L: h["a2"] + (k + 1) * L]
        f, p = psd(x)
        parts.append((np.sqrt(((x - x.mean(0)) ** 2).mean(0)) * 1000, p.sum(1)))
    m = (f >= 4) & (f <= 400)
    d01 = np.sqrt(np.mean((10 * np.log10(parts[0][1][m] / parts[2][1][m])) ** 2))
    print(f"hold70 thirds: rms mg = {[np.round(r, 1).tolist() for r, _ in parts]}, "
          f"log-spectral distance first vs last third = {d01:.2f} dB")


def compare(la, lb):
    A = [t for t in table if t["label"] == la]
    B = [t for t in table if t["label"] == lb]
    if not (A and B):
        return
    A, B = A[0], B[0]
    m = (A["f"] >= 4) & (A["f"] <= 400)
    d = np.sqrt(np.mean((10 * np.log10(A["ptot"][m] / B["ptot"][m])) ** 2))
    print(f"{la} vs {lb}: rpm {A['rpm']:.0f} vs {B['rpm']:.0f}, rms mg {np.round(A['rms'], 1)} vs "
          f"{np.round(B['rms'], 1)}, 1x SNR {A['orders'][1]:.1f} vs {B['orders'][1]:.1f} dB, "
          f"log-spectral distance {d:.2f} dB")


compare("duty50", "repeat50")
compare("duty70", "hold70")

# Temperature.
tc = z["status_temp_centi_c"]
tc = tc[tc != -32768] / 100
print(f"temperature: {tc[0]:.2f} -> {tc[-1]:.2f} C")

# Audio per step.
if len(z["audio_pcm"]):
    au = z["audio_pcm"].astype(float)
    a_idx = z["audio_index"] if "audio_index" in z else None
    print(f"audio: {len(au) / 16000 / 60:.1f} min, overall rms {au.std():.0f} counts")

# ---- Figure ----------------------------------------------------------------
fig, ax = plt.subplots(3, 1, figsize=(13, 13), gridspec_kw=dict(height_ratios=[3, 2, 2]))
x = acc - acc.mean(0)
fs_, ts_, S = spectrogram(x, fs=rate, nperseg=1024, noverlap=512, axis=0)
S = S.sum(axis=1)  # sum over axes -> (freq, time)
im = ax[0].pcolormesh(ts_ / 60, fs_, 10 * np.log10(S + 1e-12), shading="auto", cmap="magma",
                      vmin=np.percentile(10 * np.log10(S + 1e-12), 20))
tt = np.arange(n) / rate / 60
for k in (1, 2):
    ax[0].plot(tt[::200], k * rpm[::200] / 60, "c--", lw=0.8, alpha=0.8)
for s in segs:
    ax[0].axvline(s["a"] / rate / 60, color="w", lw=0.5, alpha=0.5)
    ax[0].text(s["a"] / rate / 60, 405, s["label"], color="k", fontsize=7, rotation=45, va="bottom")
ax[0].set_ylim(0, 420)
ax[0].set_ylabel("Hz")
ax[0].set_title(f"Accelerometer spectrogram (x+y+z), dashed = 1x and 2x from tach.  {sd.name}", fontsize=10)
fig.colorbar(im, ax=ax[0], label="dB")
for t in sweep:
    ax[1].semilogy(t["f"], t["ptot"], lw=0.8, label=f"{t['label']} ({t['rpm']:.0f} rpm)")
ax[1].set_xlim(0, 420)
ax[1].set_xlabel("Hz")
ax[1].set_ylabel("PSD (g^2/Hz)")
ax[1].legend(fontsize=7, ncol=4)
ax[1].set_title("Spectrum per sweep step", fontsize=10)
for t in sweep:
    ax[2].semilogy(t["f"] / t["f1"], t["ptot"], lw=0.8, label=t["label"])
ax[2].set_xlim(0, 15)
ax[2].set_xticks(range(0, 16))
ax[2].grid(alpha=0.3)
ax[2].set_xlabel("order (frequency / rotation frequency)")
ax[2].set_ylabel("PSD")
ax[2].set_title("Same spectra against order: fan peaks line up at integers, mount resonances smear", fontsize=10)
fig.tight_layout()
out = sd / "mount_report.png"
fig.savefig(out, dpi=110)
print(f"\nfigure: {out}")
