"""Per-window feature table for one session, all sensors, cached as npz.

usage: python host/analysis/windows.py <session_dir> [...]   -> $ANALYSIS_OUT/windows/<session>.npz

Amplitudes at rotation orders are RMS (g, dps, gauss or audio counts), calibrated for the Hann window.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from explore import SETTLE_S, Session  # noqa: E402

from features.extract import window_features  # noqa: E402
from features.spec import DEFAULT_SPEC  # noqa: E402

OUT = Path(os.environ.get("ANALYSIS_OUT", "results/own/overnight")) / "windows"  # ANALYSIS_OUT: one results folder per campaign
W = DEFAULT_SPEC.window  # 512 IMU samples, ~0.61 s
ORDERS = np.arange(1, 13)
AX_ORDERS = np.array([0.5, 1, 1.5, 2, 3, 7])  # per-axis orders: looseness, imbalance, misalignment, blade pass
# sqrt(band power)/n of a Hann-windowed FFT is 0.433 x the RMS of a sine; this factor makes it RMS.
HANN_RMS = np.sqrt(16 / 3)


def order_amps(x, fs, f1, orders=ORDERS, per_channel=False):
    """RMS amplitude in a band of +-max(1.5 bins, 3 %) around each order k x f1.

    x: (n, ch). Returns (len(orders),), the vector RMS over channels, or (ch, len(orders)) per channel.
    """
    n, ch = x.shape
    shape = (ch, len(orders)) if per_channel else (len(orders),)
    out = np.full(shape, np.nan)
    if n < 16 or not np.isfinite(f1) or f1 <= 0:
        return out
    x = x - x.mean(0)
    P = np.abs(np.fft.rfft(x * np.hanning(n)[:, None], axis=0)) ** 2  # (nf, ch)
    f = np.fft.rfftfreq(n, 1 / fs)
    tol = max(1.5 * fs / n, 0.03 * f1)
    for i, k in enumerate(orders):
        m = (f > k * f1 - tol) & (f < k * f1 + tol)
        if m.any() and k * f1 + tol < fs / 2:
            band = P[m].sum(0)
            if per_channel:
                out[:, i] = HANN_RMS * np.sqrt(band) / n
            else:
                out[i] = HANN_RMS * np.sqrt(band.sum()) / n
    return out


def band_rms(x, fs, lo, hi):
    x = x - x.mean(0)
    p = (np.abs(np.fft.rfft(x, axis=0)) ** 2).sum(1)
    f = np.fft.rfftfreq(len(x), 1 / fs)
    m = (f >= lo) & (f < hi)
    return np.sqrt(2 * p[m].sum()) / len(x)


def has_tach_edges(s):
    return "tach_edge_us" in s.st and bool((s.st["tach_edge_us"][s.streaming] != 0).any())


def tach_rpm(s, tc, half=2.0):
    """Mean speed over tc +- half from tach pulses. Uses the board's 1 MHz edge timestamps when the
    firmware sends them (logger >= 0.3.1), else pulses / STATUS time."""
    t = s.st_t[s.streaming]
    P = s.st["tach_pulses"].astype(float)[s.streaming]
    if has_tach_edges(s):
        e = s.st["tach_edge_us"].astype(np.int64)[s.streaming]
        ok = e != 0  # 0 = no edge since boot
        t, P, e = t[ok], P[ok], e[ok]
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
    """Speed from the audio blade-pass peak (k x rotation) in a 2 s window around each window.
    Keeps `base` where the peak is weak (< min_prom x the band median) or sits on the band edge."""
    out = base.copy()
    ok = np.zeros(len(tc), bool)
    if s.audio is None or not np.isfinite(s.rate["audio"]):
        return out, ok
    fs_a = s.rate["audio"]
    nfft = 1 << 16
    f = np.fft.rfftfreq(nfft, 1 / fs_a)
    for i in range(len(tc)):
        if not np.isfinite(base[i]) or base[i] < 300:
            continue
        a0, a1 = s.index_at("audio", tc[i] - half), s.index_at("audio", tc[i] + half)
        x = s.audio[a0:a1]
        if len(x) < 8192:
            continue
        x = (x - x.mean()) * np.hanning(len(x))
        p = np.abs(np.fft.rfft(x, nfft)) ** 2
        fk = k * base[i] / 60
        m = np.nonzero((f > fk * (1 - search)) & (f < fk * (1 + search)))[0]
        j = m[np.argmax(p[m])]
        if p[j] < min_prom * np.median(p[m]) or not m[0] < j < m[-1]:
            continue
        y0, y1, y2 = np.log(p[j - 1:j + 2])
        if y1 < y0 or y1 < y2:
            continue
        d = float(np.clip(0.5 * (y0 - y2) / (y0 - 2 * y1 + y2), -0.5, 0.5))
        out[i] = (f[j] + d * (f[1] - f[0])) / k * 60
        ok[i] = True
    return out, ok


def build(sd):
    s = Session(sd)
    gaps = {k: s.summary.get(k) for k in ("imu_gaps", "gyro_gaps", "mag_gaps") if s.summary.get(k)}
    if gaps:
        # Streams are sliced by array position, so a lost frame would shift everything after it.
        print(f"{sd}: skipped, stream gaps {gaps}")
        return None
    n_win = len(s.acc) // W
    if n_win == 0:
        return None
    starts = np.arange(n_win) * W
    # Board time at each window centre, from the IMU counter in STATUS frames sent while streaming.
    tc = np.interp(starts + W / 2, s.st["imu_samples"].astype(float)[s.streaming], s.st_t[s.streaming])
    frames = np.stack([s.acc[k:k + W] for k in starts])
    X48 = window_features(frames, s.rate["imu"], DEFAULT_SPEC)

    # Speed reference.
    # - logger >= 0.3.1: tach pulses over +-2 s timed on the board's 1 MHz clock (exact). The audio
    #   blade-pass speed is kept only as a cross-check (it would be circular for audio features and
    #   does not exist on the device).
    # - logger 0.3.0 counted 1-1.6 % extra tach pulses under PWM, so the audio blade-pass peak is used
    #   where it is clear (audio order features of those sessions are therefore optimistic).
    rpm_status = np.interp(tc, s.rpm_t, s.rpm_v) if len(s.rpm_t) else np.full(n_win, np.nan)
    rpm_tach = tach_rpm(s, tc)
    rpm_audio, rpm_audio_ok = audio_refine(s, tc, rpm_tach)
    if has_tach_edges(s):
        rpm, speed_source = rpm_tach, "tach"
    else:
        rpm, speed_source = rpm_audio, "audio_refined"
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
    acc_axis = np.full((n_win, 3, len(AX_ORDERS)), np.nan)
    gyr_ord = np.full((n_win, len(ORDERS)), np.nan)
    gyr_axis = np.full((n_win, 3, len(AX_ORDERS)), np.nan)
    gyr_rms = np.full((n_win, 3), np.nan)
    mag_ord = np.full((n_win, len(ORDERS)), np.nan)
    mag_rms = np.full((n_win, 3), np.nan)
    aud_ord = np.full((n_win, len(ORDERS)), np.nan)
    aud_db = np.full(n_win, np.nan)
    aud_bands = np.full((n_win, 6), np.nan)  # 0-250, 250-500, 0.5-1k, 1-2k, 2-4k, 4-8k Hz
    acc_hf = np.zeros(n_win)  # 150-400 Hz rms (broadband / impacts)
    edges = [0, 250, 500, 1000, 2000, 4000, 8000]
    for i, k in enumerate(starts):
        a = s.acc[k:k + W]
        acc_ord[i] = order_amps(a, fs_i, f1[i])
        acc_axis[i] = order_amps(a, fs_i, f1[i], AX_ORDERS, per_channel=True)
        acc_hf[i] = band_rms(a, fs_i, 150, 400)
        if s.gyro is not None and len(s.gyro) >= k + W:
            g = s.gyro[k:k + W]
            gyr_ord[i] = order_amps(g, fs_i, f1[i])
            gyr_axis[i] = order_amps(g, fs_i, f1[i], AX_ORDERS, per_channel=True)
            gyr_rms[i] = g.std(0)
        t0, t1 = tc[i] - W / fs_i / 2, tc[i] + W / fs_i / 2
        if s.mag is not None and len(s.mag) and np.isfinite(fs_m):
            m0, m1 = s.index_at("mag", t0), s.index_at("mag", t1)
            if m1 - m0 > 32:
                mm = s.mag[m0:m1]
                mag_ord[i] = order_amps(mm, fs_m, f1[i])
                mag_rms[i] = mm.std(0)
        if s.audio is not None and np.isfinite(fs_a):
            a0, a1 = s.index_at("audio", t0), s.index_at("audio", t1)
            if a1 - a0 > 1024 and a1 <= len(s.audio):
                au = s.audio[a0:a1, None]
                aud_ord[i] = order_amps(au, fs_a, f1[i])
                aud_db[i] = 20 * np.log10(au.std() + 1e-9)
                for b in range(6):
                    aud_bands[i, b] = band_rms(au, fs_a, edges[b], edges[b + 1])

    # context at window centres
    def interp_status(key, invalid):
        v = s.st[key].astype(float)
        ok = (v != invalid) & s.streaming
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
        mount=s.meta.get("mount", ""), fault=s.meta.get("fault", ""), severity=s.meta.get("severity", ""),
        fw=s.info.get("fw", ""), speed_source=speed_source,
        tc=tc, clock=clock, rpm=rpm, rpm_tach=rpm_tach, rpm_status=rpm_status, rpm_audio=rpm_audio,
        rpm_audio_ok=rpm_audio_ok, label=label.astype(str), pwm=pwm, settled=settled, X48=X48,
        acc_ord=acc_ord, acc_axis=acc_axis, acc_1x_axis=acc_axis[:, :, 1], ax_orders=AX_ORDERS, acc_hf=acc_hf,
        acc_rms=s.acc[:n_win * W].reshape(n_win, W, 3).std(1), acc_mean=s.acc[:n_win * W].reshape(n_win, W, 3).mean(1),
        gyr_ord=gyr_ord, gyr_axis=gyr_axis, gyr_rms=gyr_rms, mag_ord=mag_ord, mag_rms=mag_rms,
        aud_ord=aud_ord, aud_db=aud_db, aud_bands=aud_bands,
        temp=temp, hum=hum, pres=pres, light=light,
        rate_imu=s.rate["imu"], rate_mag=s.rate["mag"], rate_audio=s.rate["audio"],
    )
    return out, n_win


if __name__ == "__main__":
    for sd in sys.argv[1:]:
        r = build(sd)
        print(sd, "->", r)
