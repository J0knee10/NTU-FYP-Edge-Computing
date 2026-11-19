"""Shared loaders for overnight exploration of own sessions (all sensors)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.signal import welch

SETTLE_S = 12.0


class Session:
    def __init__(self, sd: str | Path):
        self.dir = Path(sd)
        self.meta = json.loads((self.dir / "meta.json").read_text())
        self.summary = json.loads((self.dir / "summary.json").read_text())
        z = dict(np.load(self.dir / "session.npz"))
        self.z = z
        self.info = self.meta.get("board_info", {})
        # STATUS: board time and per-stream sample counters at that time.
        self.st_t = z["status_t_us"].astype(float) / 1e6
        self.st = {k[7:]: z[k] for k in z if k.startswith("status_")}
        self.acc = z["imu_counts"].astype(float) * float(z["imu_g_per_count"])
        self.gyro = z["gyro_counts"].astype(float) * float(z["gyro_dps_per_count"]) if "gyro_counts" in z else None
        self.mag = z["mag_counts"].astype(float) * float(z["mag_gauss_per_count"]) if "mag_counts" in z else None
        self.audio = z["audio_pcm"].astype(float) if len(z["audio_pcm"]) else None
        self.rate = {
            "imu": self._rate("imu_samples"),
            "mag": self._rate("mag_samples") if self.mag is not None else np.nan,
            "audio": self._rate("audio_samples") if self.audio is not None else np.nan,
        }
        ok = np.isfinite(self.st["rpm"])
        self.rpm_t, self.rpm_v = self.st_t[ok], self.st["rpm"][ok]
        self.segments = self._segments()

    def _rate(self, key):
        s = self.st[key].astype(float)
        m = np.nonzero(np.diff(s) > 0)[0]
        if len(m) < 4:
            return np.nan
        i0, i1 = m[0] + 1, m[-1]
        return (s[i1] - s[i0]) / (self.st_t[i1] - self.st_t[i0])

    def _segments(self):
        """Profile steps as board-time intervals (settling time removed)."""
        events = [json.loads(line) for line in (self.dir / "events.jsonl").read_text().splitlines()]
        raw_t = self.z["status_t_us"] % 2**32
        steps = [e for e in events if e["event"] == "step"]
        t_end = self.st_t[np.nonzero(self.st["flags"] & 1)[0][-1]] if (self.st["flags"] & 1).any() else self.st_t[-1]
        out = []
        starts = []
        for e in steps:
            k = np.nonzero(raw_t == e["board_t_us"])[0]
            starts.append(self.st_t[k[0]] if len(k) else np.nan)
        starts.append(t_end)
        for e, a, b in zip(steps, starts[:-1], starts[1:]):
            if np.isfinite(a) and np.isfinite(b) and b - a > SETTLE_S + 5:
                out.append(dict(label=e.get("label") or "constant", pwm=e.get("pwm"), t0=a + SETTLE_S, t1=b))
        return out

    def index_at(self, stream: str, t: float) -> int:
        """Sample index of a stream at board time t (from STATUS counters)."""
        return int(np.interp(t, self.st_t, self.st[f"{stream}_samples"].astype(float)))

    def slice(self, stream: str, t0: float, t1: float):
        data = {"imu": self.acc, "gyro": self.gyro, "mag": self.mag, "audio": self.audio}[stream]
        key = "imu" if stream in ("imu", "gyro") else stream
        return data[self.index_at(key, t0): self.index_at(key, t1)]

    def rpm(self, t0, t1):
        m = (self.rpm_t >= t0) & (self.rpm_t <= t1)
        return float(np.median(self.rpm_v[m])) if m.any() else np.nan

    def stream_rate(self, stream):
        return self.rate["imu" if stream in ("imu", "gyro") else stream]


def psd(x, fs, nper):
    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x[:, None]
    f, p = welch(x - x.mean(0), fs=fs, nperseg=min(nper, len(x)), axis=0)
    return f, p


def order_snr(f, p, f1, orders=range(1, 17), tol_hz=None, fmax=None):
    """dB above the median floor at each rotation order (max within +-tol)."""
    tol = tol_hz if tol_hz else max(1.0, 0.03 * f1)
    fmax = fmax or f[-1]
    band = (f > 3) & (f < fmax)
    floor = np.median(p[band])
    out = {}
    for k in orders:
        fk = k * f1
        if fk + tol >= fmax:
            break
        m = (f > fk - tol) & (f < fk + tol)
        out[k] = 10 * np.log10(p[m].max() / floor) if m.any() else np.nan
    return out


def order_amp(f, p, f1, k=1, tol_hz=None):
    """RMS amplitude in a band around order k (sqrt of integrated PSD)."""
    tol = tol_hz if tol_hz else max(1.0, 0.03 * f1)
    m = (f > k * f1 - tol) & (f < k * f1 + tol)
    df = f[1] - f[0]
    return float(np.sqrt(p[m].sum() * df)) if m.any() else np.nan


def corruption(acc_counts):
    c = acc_counts.astype(int)
    if len(c) < 3:
        return 0
    d1 = np.abs(c[1:-1] - c[:-2]).max(1)
    d2 = np.abs(c[1:-1] - c[2:]).max(1)
    dn = np.abs(c[2:] - c[:-2]).max(1)
    same3 = ((c[:, 0] == c[:, 1]) & (c[:, 1] == c[:, 2])).sum()
    return int(((d1 > 2500) & (d2 > 2500) & (dn < 1000)).sum() + same3)
