import re
from pathlib import Path

import numpy as np

from fanlog.protocol import (
    STATUS_FIELDS,
    STATUS_STRUCT,
    FrameParser,
    FrameType,
    crc16_ccitt,
    decode_audio,
    decode_imu,
    decode_info,
    decode_status,
    encode_audio,
    encode_frame,
    encode_imu,
    encode_status,
)

FIRMWARE_PROTOCOL_H = Path(__file__).resolve().parents[2] / "firmware" / "logger" / "protocol.h"


def test_crc_matches_ccitt_false_check_value():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_roundtrip_byte_by_byte():
    xyz = np.arange(30, dtype=np.int16).reshape(10, 3) - 15
    stream = encode_frame(FrameType.IMU, 0, encode_imu(1000, 64, xyz)) + encode_frame(
        FrameType.TEXT, 1, b"OK START"
    )
    parser = FrameParser()
    frames = []
    for i in range(len(stream)):
        frames += parser.feed(stream[i : i + 1])
    assert [f.type for f in frames] == [FrameType.IMU, FrameType.TEXT]
    block = decode_imu(frames[0].payload)
    assert block.t_us == 1000 and block.first_index == 64
    np.testing.assert_array_equal(block.data, xyz)
    assert frames[1].payload == b"OK START"
    assert parser.crc_errors == 0 and parser.bytes_skipped == 0


def test_corrupt_frame_is_skipped_and_parser_resyncs():
    good1 = encode_frame(FrameType.TEXT, 0, b"first")
    bad = bytearray(encode_frame(FrameType.TEXT, 1, b"second"))
    bad[8] ^= 0xFF
    good2 = encode_frame(FrameType.TEXT, 2, b"third")
    parser = FrameParser()
    frames = parser.feed(b"\x00garbage\xA5" + good1 + bytes(bad) + good2)
    assert [f.payload for f in frames] == [b"first", b"third"]
    assert parser.crc_errors == 1
    assert parser.frames_lost == 1  # seq 1 never arrived intact


def test_sequence_gap_counts_lost_frames_with_wraparound():
    parser = FrameParser()
    stream = b"".join(encode_frame(FrameType.TEXT, s, b"x") for s in (254, 255, 2))
    parser.feed(stream)
    assert parser.frames_lost == 2  # 0 and 1 missing


def test_status_and_audio_and_info_decode():
    payload = encode_status(t_us=5, tach_pulses=42, temp_centi_c=-150, humidity_centi=4000, flags=3)
    s = decode_status(payload)
    assert s["t_us"] == 5 and s["tach_pulses"] == 42 and s["temp_centi_c"] == -150 and s["flags"] == 3

    pcm = np.array([-32768, 0, 32767], dtype=np.int16)
    a = decode_audio(encode_audio(7, 256, pcm))
    np.testing.assert_array_equal(a.data, pcm)

    assert decode_info(b"fw=logger-0.1.0 imu_ok=1 imu_rate_hz=951.20") == {
        "fw": "logger-0.1.0",
        "imu_ok": "1",
        "imu_rate_hz": "951.20",
    }


def test_status_layout_matches_firmware_header():
    """Field names, order and total size must match StatusPayload in protocol.h."""
    src = FIRMWARE_PROTOCOL_H.read_text()
    body = re.search(r"struct __attribute__\(\(packed\)\) StatusPayload \{(.*?)\};", src, re.S).group(1)
    fields = re.findall(r"^\s*(u?int\d+)_t\s+(\w+);", body, re.M)
    assert tuple(name for _, name in fields) == STATUS_FIELDS
    size = sum(int(re.search(r"\d+", t).group()) // 8 for t, _ in fields)
    assert size == STATUS_STRUCT.size == 36
