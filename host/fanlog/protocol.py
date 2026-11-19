"""Frame encoding/decoding for the logger firmware (firmware/logger/protocol.h).

Frame layout, little-endian:

    0xA5 0x5A | type u8 | seq u8 | len u16 | payload[len] | crc16 u16

crc16 is CRC-16/CCITT-FALSE over type..payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

SYNC = b"\xA5\x5A"
MAX_PAYLOAD = 4096


class FrameType(IntEnum):
    IMU = 1
    AUDIO = 2
    STATUS = 3
    INFO = 4
    TEXT = 5
    GYRO = 6  # same layout as IMU; same sample indices as the accelerometer
    MAG = 7   # same layout as IMU; own sample index (magnetometer rate)
    ENV = 8   # pressure and ambient light, ~1 Hz


@dataclass(frozen=True)
class Frame:
    type: int
    seq: int
    payload: bytes


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def encode_frame(ftype: int, seq: int, payload: bytes) -> bytes:
    body = struct.pack("<BBH", ftype, seq & 0xFF, len(payload)) + payload
    return SYNC + body + struct.pack("<H", crc16_ccitt(body))


class FrameParser:
    """Incremental parser: feed arbitrary byte chunks, get complete frames.

    Corrupt frames are skipped by searching for the next sync word.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.bytes_skipped = 0
        self.frames_lost = 0  # inferred from gaps in the sequence counter
        self._last_seq: int | None = None

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        while True:
            start = self._buf.find(SYNC)
            if start < 0:
                # Keep a trailing 0xA5 that may be the first half of a sync word.
                keep = 1 if self._buf[-1:] == SYNC[:1] else 0
                self.bytes_skipped += len(self._buf) - keep
                del self._buf[: len(self._buf) - keep]
                return frames
            if start > 0:
                self.bytes_skipped += start
                del self._buf[:start]
            if len(self._buf) < 6:
                return frames
            ftype, seq, length = struct.unpack_from("<BBH", self._buf, 2)
            if length > MAX_PAYLOAD:
                self._skip_sync()
                continue
            total = 6 + length + 2
            if len(self._buf) < total:
                return frames
            body = bytes(self._buf[2 : 6 + length])
            (crc,) = struct.unpack_from("<H", self._buf, 6 + length)
            if crc != crc16_ccitt(body):
                self.crc_errors += 1
                self._skip_sync()
                continue
            del self._buf[:total]
            if self._last_seq is not None:
                self.frames_lost += (seq - self._last_seq - 1) & 0xFF
            self._last_seq = seq
            frames.append(Frame(ftype, seq, body[4:]))

    def _skip_sync(self) -> None:
        del self._buf[:2]
        self.bytes_skipped += 2


# ---- Payload decoders -----------------------------------------------------

_SAMPLE_HEADER = struct.Struct("<IIH")  # t_us, first_index, n

STATUS_STRUCT = struct.Struct("<IIIIIIIHhHBBIIII")
STATUS_FIELDS = (
    "t_us",
    "imu_samples",
    "imu_overruns",
    "audio_samples",
    "audio_dropped",
    "tach_pulses",
    "tach_period_us",
    "pwm_permille",
    "temp_centi_c",
    "humidity_centi",
    "flags",
    "reserved",
    "mag_samples",
    "mag_overruns",
    "tach_edge_us",
    "tach_rejected",
)
# Older firmware sent fewer fields; the missing ones decode as 0.
STATUS_STRUCT_V1 = struct.Struct("<IIIIIIIHhHBB")  # before logger-0.3.0 (36 bytes)
STATUS_STRUCT_V2 = struct.Struct("<IIIIIIIHhHBBII")  # logger-0.3.0 (44 bytes)

ENV_STRUCT = struct.Struct("<IIhHHHHBB")
ENV_FIELDS = (
    "t_us",
    "pressure_centi_pa",
    "baro_temp_centi_c",
    "light_clear",
    "light_red",
    "light_green",
    "light_blue",
    "flags",
    "reserved",
)

STATUS_STREAMING = 1 << 0
STATUS_AUDIO_ON = 1 << 1
STATUS_PWM_SET = 1 << 2
STATUS_TH_OK = 1 << 3  # temperature/humidity sensor found
STATUS_IMU_FIFO = 1 << 4


@dataclass(frozen=True)
class SampleBlock:
    t_us: int
    first_index: int
    data: np.ndarray  # IMU: (n, 3) int16 counts; audio: (n,) int16 PCM


def decode_imu(payload: bytes) -> SampleBlock:
    t_us, first, n = _SAMPLE_HEADER.unpack_from(payload)
    data = np.frombuffer(payload, dtype="<i2", count=3 * n, offset=_SAMPLE_HEADER.size)
    return SampleBlock(t_us, first, data.reshape(n, 3))


def decode_audio(payload: bytes) -> SampleBlock:
    t_us, first, n = _SAMPLE_HEADER.unpack_from(payload)
    data = np.frombuffer(payload, dtype="<i2", count=n, offset=_SAMPLE_HEADER.size)
    return SampleBlock(t_us, first, data)


def decode_status(payload: bytes) -> dict[str, int]:
    for old in (STATUS_STRUCT_V1, STATUS_STRUCT_V2):
        if len(payload) == old.size:
            values = old.unpack(payload)
            values += (0,) * (len(STATUS_FIELDS) - len(values))
            return dict(zip(STATUS_FIELDS, values))
    return dict(zip(STATUS_FIELDS, STATUS_STRUCT.unpack(payload)))


decode_gyro = decode_imu
decode_mag = decode_imu


def decode_env(payload: bytes) -> dict[str, int]:
    return dict(zip(ENV_FIELDS, ENV_STRUCT.unpack(payload)))


def decode_info(payload: bytes) -> dict[str, str]:
    """Parse 'key=value key=value' text into a dict."""
    return dict(item.split("=", 1) for item in payload.decode("ascii", "replace").split() if "=" in item)


# ---- Encoders for tests and simulated boards -------------------------------

def encode_imu(t_us: int, first_index: int, xyz: np.ndarray) -> bytes:
    xyz = np.asarray(xyz, dtype="<i2").reshape(-1, 3)
    return _SAMPLE_HEADER.pack(t_us, first_index, len(xyz)) + xyz.tobytes()


def encode_audio(t_us: int, first_index: int, pcm: np.ndarray) -> bytes:
    pcm = np.asarray(pcm, dtype="<i2").ravel()
    return _SAMPLE_HEADER.pack(t_us, first_index, len(pcm)) + pcm.tobytes()


def encode_status(**fields: int) -> bytes:
    return STATUS_STRUCT.pack(*(fields.get(name, 0) for name in STATUS_FIELDS))


def encode_env(**fields: int) -> bytes:
    return ENV_STRUCT.pack(*(fields.get(name, 0) for name in ENV_FIELDS))
