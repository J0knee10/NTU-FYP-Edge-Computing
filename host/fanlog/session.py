"""Convert a recorded session (raw serial bytes) into numpy arrays.

A session directory written by ``fanlog.record`` contains:

    meta.json     labels and settings (fan, fault, severity, profile, board INFO, ...)
    events.jsonl  host-side events: commands sent, profile steps
    stream.bin    raw bytes from the board, exactly as received (source of truth)

``convert`` parses stream.bin and writes session.npz next to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .protocol import (
    ENV_FIELDS,
    FrameParser,
    FrameType,
    STATUS_FIELDS,
    decode_audio,
    decode_env,
    decode_imu,
    decode_status,
)


def unwrap_u32(values: np.ndarray) -> np.ndarray:
    """Undo uint32 wrap-around (micros() wraps every ~71.6 minutes)."""
    v = np.asarray(values, dtype=np.int64)
    if v.size == 0:
        return v
    steps = np.diff(v)
    wraps = np.concatenate([[0], np.cumsum(steps < -(1 << 31))])
    return v + (wraps << 32)


def _concat_blocks(blocks, width: int | None):
    if not blocks:
        shape = (0, width) if width else (0,)
        return np.zeros(shape, np.int16), np.zeros(0, np.int64), np.zeros((0, 2), np.int64)
    data = np.concatenate([b.data for b in blocks])
    index = np.concatenate([np.arange(b.first_index, b.first_index + len(b.data)) for b in blocks])
    # (first_index, n) per block, for gap checks and timing fits
    block_info = np.array([(b.first_index, len(b.data)) for b in blocks], dtype=np.int64)
    return data, index, block_info


def _find_gaps(block_info: np.ndarray) -> list[tuple[int, int]]:
    """Return (expected_index, got_index) wherever blocks are not contiguous."""
    gaps = []
    for (prev_first, prev_n), (first, _) in zip(block_info[:-1], block_info[1:]):
        if first != prev_first + prev_n:
            gaps.append((int(prev_first + prev_n), int(first)))
    return gaps


def _fit_rate(last_index: np.ndarray, t_us: np.ndarray) -> tuple[float, float]:
    """Fit t = t0 + index / rate using each block's last sample and send time.

    Send time lags the true sample time by a variable FIFO delay, so this is a
    coarse estimate; per-sample timing should come from index / rate.
    """
    if len(last_index) < 2:
        return float("nan"), float("nan")
    slope, intercept = np.polyfit(last_index.astype(float), t_us.astype(float), 1)
    return 1e6 / slope, intercept


def convert(session_dir: str | Path) -> dict:
    session_dir = Path(session_dir)
    meta = json.loads((session_dir / "meta.json").read_text())
    raw = (session_dir / "stream.bin").read_bytes()

    parser = FrameParser()
    frames = parser.feed(raw)

    # Unwrap all board timestamps together, in arrival order.
    stamped = [f for f in frames if f.type in (FrameType.IMU, FrameType.AUDIO, FrameType.STATUS,
                                               FrameType.GYRO, FrameType.MAG, FrameType.ENV)]
    t_all = unwrap_u32(np.array([int.from_bytes(f.payload[:4], "little") for f in stamped]))
    t_of = {id(f): t for f, t in zip(stamped, t_all)}

    imu_blocks, imu_t = [], []
    gyro_blocks, gyro_t = [], []
    mag_blocks, mag_t = [], []
    env_rows, env_t = [], []
    audio_blocks, audio_t = [], []
    status_rows, status_t = [], []
    texts = []
    for f in frames:
        if f.type == FrameType.IMU:
            imu_blocks.append(decode_imu(f.payload))
            imu_t.append(t_of[id(f)])
        elif f.type == FrameType.GYRO:
            gyro_blocks.append(decode_imu(f.payload))
            gyro_t.append(t_of[id(f)])
        elif f.type == FrameType.MAG:
            mag_blocks.append(decode_imu(f.payload))
            mag_t.append(t_of[id(f)])
        elif f.type == FrameType.ENV:
            env_rows.append(decode_env(f.payload))
            env_t.append(t_of[id(f)])
        elif f.type == FrameType.AUDIO:
            audio_blocks.append(decode_audio(f.payload))
            audio_t.append(t_of[id(f)])
        elif f.type == FrameType.STATUS:
            status_rows.append(decode_status(f.payload))
            status_t.append(t_of[id(f)])
        elif f.type in (FrameType.TEXT, FrameType.INFO):
            texts.append(f.payload.decode("ascii", "replace"))

    imu, imu_index, imu_blocks_info = _concat_blocks(imu_blocks, 3)
    gyro, gyro_index, gyro_blocks_info = _concat_blocks(gyro_blocks, 3)
    mag, mag_index, mag_blocks_info = _concat_blocks(mag_blocks, 3)
    audio, audio_index, audio_blocks_info = _concat_blocks(audio_blocks, None)
    imu_t = np.array(imu_t, dtype=np.int64)
    gyro_t = np.array(gyro_t, dtype=np.int64)
    mag_t = np.array(mag_t, dtype=np.int64)
    audio_t = np.array(audio_t, dtype=np.int64)

    imu_rate, _ = _fit_rate(imu_blocks_info.sum(axis=1) - 1, imu_t) if len(imu_t) else (float("nan"), 0)
    mag_rate, _ = _fit_rate(mag_blocks_info.sum(axis=1) - 1, mag_t) if len(mag_t) > 1 else (float("nan"), 0)
    env = {name: np.array([r[name] for r in env_rows], dtype=np.int64) for name in ENV_FIELDS}
    env["t_us"] = np.array(env_t, dtype=np.int64)

    status = {name: np.array([r[name] for r in status_rows], dtype=np.int64) for name in STATUS_FIELDS}
    status["t_us"] = np.array(status_t, dtype=np.int64)

    # Fan speed from tach pulse deltas between consecutive STATUS frames.
    ppr = int(meta.get("tach_pulses_per_rev", 2))
    rpm = np.full(len(status_t), np.nan)
    if len(status_t) > 1:
        dp = np.diff(status["tach_pulses"])
        dt = np.diff(status["t_us"]) / 1e6
        rpm[1:] = np.where(dt > 0, dp / ppr / dt * 60.0, np.nan)

    info = meta.get("board_info", {})
    mg_per_lsb = float(info.get("imu_mg_per_lsb", "nan"))
    mdps_per_lsb = float(info.get("gyro_mdps_per_lsb", "nan"))
    lsb_per_gauss = float(info.get("mag_lsb_per_gauss", "nan"))
    out = session_dir / "session.npz"
    np.savez_compressed(
        out,
        imu_counts=imu,
        imu_index=imu_index,
        imu_block_info=imu_blocks_info,
        imu_block_t_us=imu_t,
        imu_g_per_count=np.float64(mg_per_lsb / 1000.0),
        imu_rate_hz_est=np.float64(imu_rate),
        gyro_counts=gyro,
        gyro_index=gyro_index,
        gyro_dps_per_count=np.float64(mdps_per_lsb / 1000.0),
        mag_counts=mag,
        mag_index=mag_index,
        mag_block_info=mag_blocks_info,
        mag_block_t_us=mag_t,
        mag_gauss_per_count=np.float64(1.0 / lsb_per_gauss),
        mag_rate_hz_est=np.float64(mag_rate),
        **{f"env_{k}": v for k, v in env.items()},
        audio_pcm=audio,
        audio_index=audio_index,
        audio_block_t_us=audio_t,
        status_rpm=rpm,
        **{f"status_{k}": v for k, v in status.items()},
    )

    summary = {
        "frames": len(frames),
        "crc_errors": parser.crc_errors,
        "frames_lost": parser.frames_lost,
        "bytes_skipped": parser.bytes_skipped,
        "imu_samples": int(len(imu)),
        "imu_gaps": _find_gaps(imu_blocks_info),
        "imu_overruns": int(status["imu_overruns"][-1]) if len(status_t) else 0,
        "imu_rate_hz_est": round(imu_rate, 2) if imu_rate == imu_rate else None,
        "gyro_samples": int(len(gyro)),
        "gyro_gaps": _find_gaps(gyro_blocks_info),
        "mag_samples": int(len(mag)),
        "mag_gaps": _find_gaps(mag_blocks_info),
        "mag_overruns": int(status["mag_overruns"][-1]) if len(status_t) else 0,
        "mag_rate_hz_est": round(mag_rate, 2) if mag_rate == mag_rate else None,
        "env_frames": len(env_rows),
        "audio_samples": int(len(audio)),
        "audio_gaps": _find_gaps(audio_blocks_info),
        "audio_dropped": int(status["audio_dropped"][-1]) if len(status_t) else 0,
        "status_frames": len(status_t),
        "board_messages": texts,
        "npz": str(out),
    }
    (session_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert recorded sessions to session.npz")
    ap.add_argument("sessions", nargs="+", help="session directories")
    args = ap.parse_args()
    for s in args.sessions:
        summary = convert(s)
        summary.pop("board_messages")
        print(s, json.dumps(summary))


if __name__ == "__main__":
    main()
