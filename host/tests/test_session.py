import json

import numpy as np

from fanlog.protocol import FrameType, encode_audio, encode_frame, encode_imu, encode_status
from fanlog.session import convert, unwrap_u32

RATE_HZ = 952.0


def _write_session(tmp_path, n_batches=60, drop_batch=None, t0_us=0xFFFFFFFF - 20_000):
    """Simulate the firmware: 32-sample IMU batches, 4 Hz status, audio chunks.

    t0_us starts just before the uint32 wrap so conversion must unwrap it.
    """
    rng = np.random.default_rng(0)
    seq = 0
    out = bytearray()

    def frame(ftype, payload):
        nonlocal seq
        out.extend(encode_frame(ftype, seq, payload))
        seq = (seq + 1) & 0xFF

    pulses = 0
    next_status_us = 0.0
    for b in range(n_batches):
        first = b * 32
        t_rel = (first + 31) / RATE_HZ * 1e6
        while next_status_us <= t_rel:
            pulses = int(next_status_us / 1e6 * 50 * 2)  # 3000 rpm, 2 pulses/rev
            frame(
                FrameType.STATUS,
                encode_status(
                    t_us=(t0_us + int(next_status_us)) & 0xFFFFFFFF,
                    imu_samples=first,
                    tach_pulses=pulses,
                    pwm_permille=700,
                ),
            )
            next_status_us += 250_000
        if b == drop_batch:
            continue
        xyz = rng.integers(-500, 500, size=(32, 3))
        frame(FrameType.IMU, encode_imu((t0_us + int(t_rel)) & 0xFFFFFFFF, first, xyz))
        if b % 4 == 0:
            frame(FrameType.AUDIO, encode_audio((t0_us + int(t_rel)) & 0xFFFFFFFF, (b // 4) * 256, np.zeros(256)))

    (tmp_path / "stream.bin").write_bytes(bytes(out))
    (tmp_path / "meta.json").write_text(
        json.dumps({"tach_pulses_per_rev": 2, "board_info": {"imu_mg_per_lsb": "0.122"}})
    )
    return tmp_path


def test_unwrap_u32():
    np.testing.assert_array_equal(unwrap_u32([4294967290, 4294967295, 3, 10]), [4294967290, 4294967295, 4294967299, 4294967306])


def test_convert_clean_session(tmp_path):
    summary = convert(_write_session(tmp_path))
    data = np.load(tmp_path / "session.npz")

    assert summary["crc_errors"] == 0 and summary["frames_lost"] == 0
    assert summary["imu_samples"] == 60 * 32 and summary["imu_gaps"] == []
    assert data["imu_counts"].shape == (60 * 32, 3)
    np.testing.assert_array_equal(data["imu_index"], np.arange(60 * 32))
    assert abs(summary["imu_rate_hz_est"] - RATE_HZ) < 1.0
    assert np.all(np.diff(data["status_t_us"]) > 0)  # wrap was undone
    assert np.nanmedian(data["status_rpm"]) == np.float64(3000.0)
    assert np.isclose(data["imu_g_per_count"], 0.000122)
    assert summary["audio_samples"] == 15 * 256


def test_convert_reports_missing_imu_batch(tmp_path):
    summary = convert(_write_session(tmp_path, drop_batch=10))
    assert summary["imu_gaps"] == [(320, 352)]
