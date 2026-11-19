"""Per-window feature table for one session, all sensors, cached as npz.

usage: python windows.py <session_dir> [...]   -> results/own/overnight/windows/<session>.npz
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import SETTLE_S, Session  # noqa: E402

from features.extract import window_features  # noqa: E402
from features.spec import DEFAULT_SPEC  # noqa: E402

REPO = Path(__file__).resolve()
OUT = Path("results/own/overnight/windows")
W = DEFAULT_SPEC.window  # 512 IMU samples, ~0.61 s
ORDERS = np.arange(1, 13)


def order_amps(x, fs, f1, orders=ORDERS):
    """x: (n, ch) -> amplitude (sqrt of band power, summed over channels) at each order."""
    n = len(x)
    if n < 16 or not np.isfinite(f1) or f1 <= 0:
        return np.full(len(orders), np.nan)
    x = x - x.mean(0)
    p = (np.abs(np.fft.rfft(x * np.hanning(n)[:, None], axis=0)) ** 2).sum(1)
    f = np.fft.rfftfreq(n, 1 / fs)
    tol = max(1.5 * fs / n, 0.03 * f1)
    out = np.full(len(orders), np.nan)
    for i, k in enumerate(orders):
        m = (f > k * f1 - tol) & (f < k * f1 + tol)
        if m.any() and k * f1 + tol < fs / 2:
            out[i] = np.sqrt(p[m].sum()) / n
    return out


def band_rms(x, fs, lo, hi):
    x = x - x.mean(0)
    p = (np.abs(np.fft.rfft(x, axis=0)) ** 2).sum(1)
    f = np.fft.rfftfreq(len(x), 1 / fs)
    m = (f >= lo) & (f < hi)
    return np.sqrt(2 * p[m].sum()) / len(x)


def tach_rpm(s, tc, half=2.0):
    """Mean speed over tc +- half from tach pulses. Uses the board's 1 MHz edge timestamps when the
    firmware sends them (logger >= 0.3.1), else pulses / STATUS time."""
    strm = (s.st["flags"] & 1).astype(bool)
    t = s.st_t[strm]
    P = s.st["tach_pulses"].astype(float)[strm]
    if "tach_edge_us" in s.st and s.st["tach_edge_us"][strm].any():
        e = s.st["tach_edge_us"].astype(np.int64)[strm]
        E = np.concatenate([[0], np.cumsum(np.diff(e) % (1 << 32))]).astype(float) / 1e6
        ia = np.clip(np.searchsorted(t, tc - half), 0, len(t) - 1)
        ib = np.clip(np.searchsorted(t, tc + half), 0, len(t) - 1)
        dE = E[ib] - E[ia]
        # The edge clock is the crystal; STATUS/board time runs on the RC oscillator (~0.2 % fast).
        # Express speed in board-time Hz so it matches the stream rates used for the spectra.
        board_per_edge = (t[-1] - t[0]) / (E[-1] - E[0])
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(dE > 0, (P[ib] - P[ia]) / 2 / dE * 60 / board_per_edge, np.nan)
    p1, p0 = np.interp(tc + half, t, P), np.interp(tc - half, t, P)
    return (p1 - p0) / 2 / (2 * half) * 60


def audio_refine(s, tc, base, k=7, search=0.04, half=1.0, min_prom=10.0):
    """Refine speed from the audio blade-pass peak (k x rotation) in a 2 s window. Keeps the tach
    value where the peak is weak (< min_prom x the median power of the search band)."""
    out = base.copy()
    ok = np.zeros(len(tc), bool)
    if s.audio is None or not np.isfinite(s.rate["audio"]):
        return out, ok
    fs_a = s.rate["audio"]
    aud_cnt = s.st["audio_samples"].astype(float)
    nfft = 1 << 16
    f = np.fft.rfftfreq(nfft, 1 / fs_a)
    for i in range(len(tc)):
        if not np.isfinite(base[i]) or base[i] < 300:
            continue
        a0 = int(np.interp(tc[i] - half, s.st_t, aud_cnt))
        a1 = int(np.interp(tc[i] + half, s.st_t, aud_cnt))
        x = s.audio[a0:a1]
        if len(x) < 8192:
            continue
        x = (x - x.mean()) * np.hanning(len(x))
        p = np.abs(np.fft.rfft(x, nfft)) ** 2
        fk = k * base[i] / 60
        m = np.nonzero((f > fk * (1 - search)) & (f < fk * (1 + search)))[0]
        j = m[np.argmax(p[m])]
        if p[j] < min_prom * np.median(p[m]) or not 0 < j < len(p) - 1:
            continue
        y0, y1, y2 = np.log(p[j - 1:j + 2])
        d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
        out[i] = (f[j] + d * (f[1] - f[0])) / k * 60
        ok[i] = True
    return out, ok


def build(sd):
    s = Session(sd)
    acc_counts = s.z["imu_counts"]
    n_win = len(s.acc) // W
    if n_win == 0:
        return None
    starts = np.arange(n_win) * W
    # board time at each window centre, from the IMU counter in STATUS frames
    # Only STATUS frames sent while streaming: before START they still carry the previous
    # session's counter, which then resets to 0 (not monotonic).
    strm = (s.st["flags"] & 1).astype(bool)
    imu_cnt = s.st["imu_samples"].astype(float)[strm]
    tc = np.interp(starts + W / 2, imu_cnt, s.st_t[strm])
    frames = np.stack([s.acc[k:k + W] for k in starts])
    X48 = window_features(frames, s.rate["imu"], DEFAULT_SPEC)
    # Speed reference. The per-STATUS rpm (pulses per 250 ms) has 120 rpm steps, and logger 0.3.0
    # counts ~1-1.5 % extra tach pulses under PWM (glitch filter defeated by the 1 ms micros()).
    # Use pulses over +-2 s, refined by the audio blade-pass peak where it is clear.
    rpm_status = np.interp(tc, s.rpm_t, s.rpm_v) if len(s.rpm_t) else np.full(n_win, np.nan)
    rpm_tach = tach_rpm(s, tc)
    rpm, rpm_audio_ok = audio_refine(s, tc, rpm_tach)
    f1 = rpm / 60

    # segment label / settled flag
    label = np.full(n_win, "", dtype=object)
    pwm = np.full(n_win, -1)
    settled = np.zeros(n_win, bool)
    for seg in s.segments:
        m = (tc >= seg["t0"] - SETTLE_S) & (tc < seg["t1"])
        label[m] = seg["label"]
        pwm[m] = seg["pwm"] if seg["pwm"] is not None else -1
        settled[(tc >= seg["t0"]) & (tc < seg["t1"])] = True

    fs_i, fs_m, fs_a = s.rate["imu"], s.rate["mag"], s.rate["audio"]
    acc_ord = np.zeros((n_win, len(ORDERS)))
    acc_ord_ax = np.zeros((n_win, 3))  # 1x per axis
    gyr_ord = np.full((n_win, len(ORDERS)), np.nan)
    gyr_rms = np.full((n_win, 3), np.nan)
    mag_ord = np.full((n_win, len(ORDERS)), np.nan)
    mag_rms = np.full((n_win, 3), np.nan)
    aud_ord = np.full((n_win, len(ORDERS)), np.nan)
    aud_db = np.full(n_win, np.nan)
    aud_bands = np.full((n_win, 6), np.nan)  # 0-250, 250-500, 0.5-1k, 1-2k, 2-4k, 4-8k Hz
    acc_hf = np.zeros(n_win)  # 150-400 Hz rms (broadband / impacts)
    edges = [0, 250, 500, 1000, 2000, 4000, 8000]
    mag_cnt = s.st["mag_samples"].astype(float)
    aud_cnt = s.st["audio_samples"].astype(float)
    for i, k in enumerate(starts):
        a = s.acc[k:k + W]
        acc_ord[i] = order_amps(a, fs_i, f1[i])
        for ax in range(3):
            acc_ord_ax[i, ax] = order_amps(a[:, ax:ax + 1], fs_i, f1[i], [1])[0]
        acc_hf[i] = band_rms(a, fs_i, 150, 400)
        if s.gyro is not None and len(s.gyro) >= k + W:
            g = s.gyro[k:k + W]
            gyr_ord[i] = order_amps(g, fs_i, f1[i])
            gyr_rms[i] = g.std(0)
        t0, t1 = tc[i] - W / fs_i / 2, tc[i] + W / fs_i / 2
        if s.mag is not None and len(s.mag) and np.isfinite(fs_m):
            m0, m1 = int(np.interp(t0, s.st_t, mag_cnt)), int(np.interp(t1, s.st_t, mag_cnt))
            if m1 - m0 > 32:
                mm = s.mag[m0:m1]
                mag_ord[i] = order_amps(mm, fs_m, f1[i])
                mag_rms[i] = mm.std(0)
        if s.audio is not None and np.isfinite(fs_a):
            a0, a1 = int(np.interp(t0, s.st_t, aud_cnt)), int(np.interp(t1, s.st_t, aud_cnt))
            if a1 - a0 > 1024 and a1 <= len(s.audio):
                au = s.audio[a0:a1, None]
                aud_ord[i] = order_amps(au, fs_a, f1[i])
                aud_db[i] = 20 * np.log10(au.std() + 1e-9)
                for b in range(6):
                    aud_bands[i, b] = band_rms(au, fs_a, edges[b], edges[b + 1])

    # context at window centres
    def interp_status(key, invalid):
        v = s.st[key].astype(float)
        ok = v != invalid
        return np.interp(tc, s.st_t[ok], v[ok]) if ok.any() else np.full(n_win, np.nan)

    temp = interp_status("temp_centi_c", -32768) / 100
    hum = interp_status("humidity_centi", 0xFFFF) / 100
    env_t = s.z["env_t_us"].astype(float) / 1e6 if "env_t_us" in s.z else np.zeros(0)
    if len(env_t):
        p = s.z["env_pressure_centi_pa"].astype(float)
        ok = p > 0
        pres = np.interp(tc, env_t[ok], p[ok] / 100) if ok.any() else np.full(n_win, np.nan)
        lc = s.z["env_light_clear"].astype(float)
        ok = lc != 0xFFFF
        light = np.interp(tc, env_t[ok], lc[ok]) if ok.any() else np.full(n_win, np.nan)
    else:
        pres = light = np.full(n_win, np.nan)
    host0 = datetime.fromisoformat(s.meta["host_start"])
    clock = np.array([(host0 + timedelta(seconds=float(t - s.st_t[0]))).timestamp() for t in tc])

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{s.dir.name}.npz"
    np.savez_compressed(
        out, session=s.dir.name, profile=s.meta["profile"].get("name"), notes=s.meta.get("notes", ""),
        tc=tc, clock=clock, rpm=rpm, rpm_tach=rpm_tach, rpm_status=rpm_status, rpm_audio_ok=rpm_audio_ok,
        label=label.astype(str), pwm=pwm, settled=settled, X48=X48,
        acc_ord=acc_ord, acc_1x_axis=acc_ord_ax, acc_hf=acc_hf, acc_rms=s.acc[:n_win * W].reshape(n_win, W, 3).std(1),
        gyr_ord=gyr_ord, gyr_rms=gyr_rms, mag_ord=mag_ord, mag_rms=mag_rms,
        aud_ord=aud_ord, aud_db=aud_db, aud_bands=aud_bands,
        temp=temp, hum=hum, pres=pres, light=light,
        corrupted=np.int64(0), rate_imu=s.rate["imu"], rate_mag=s.rate["mag"], rate_audio=s.rate["audio"],
    )
    return out, n_win


if __name__ == "__main__":
    for sd in sys.argv[1:]:
        r = build(sd)
        print(sd, "->", r)
