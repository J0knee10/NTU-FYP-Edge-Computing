"""Common format for vibration data from any source.

Steps 1-4 (features, models, RL and FL simulators) take Recording objects only, so the same code
runs on public datasets during development and on our own sessions for the reported results. Never
hard-code a sample rate downstream: use Recording.rate_hz, or resample() to the board's rate first.

    from fanlog.recording import fraunhofer_recordings, uci_recordings, session_recordings
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

import numpy as np

from .datasets import EXTERNAL, UCI_RATE_HZ, UCI_SEVERITY, load_uci_accelerometer

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_RATE_HZ = 833.0    # LSM6DS33 accelerometer ODR used by firmware/logger (nominal)
NORMAL = "normal"
UCI_MAX_RPM = 1900.0


@dataclass
class Recording:
    source: str          # "own", "fraunhofer" or "uci"
    name: str            # unique within the source
    rate_hz: float
    acc: np.ndarray      # (n, 3) vibration, continuous in time
    acc_units: str
    fan: str             # one machine + mount; becomes one FL client in step 4
    condition: str       # "normal" or a fault label
    severity: int        # 0 = normal / least; higher = worse, comparable within a source only
    speed_pct: float | None = None   # fixed speed, if the whole recording is at one speed
    rpm: np.ndarray | None = None    # (n,) speed per sample, if measured
    meta: dict = field(default_factory=dict)

    @property
    def is_fault(self) -> bool:
        return self.condition != NORMAL


def resample(rec: Recording, rate_hz: float = BOARD_RATE_HZ) -> Recording:
    """Resample to rate_hz with an anti-alias filter, e.g. 4096 Hz public data -> our 833 Hz."""
    if rec.rate_hz == rate_hz:
        return rec
    from scipy.signal import resample_poly

    ratio = Fraction(rate_hz / rec.rate_hz).limit_denominator(1000)
    acc = resample_poly(rec.acc.astype(np.float64), ratio.numerator, ratio.denominator, axis=0)
    rpm = None
    if rec.rpm is not None:
        t_out = np.arange(len(acc)) / rate_hz
        rpm = np.interp(t_out, np.arange(len(rec.rpm)) / rec.rate_hz, rec.rpm).astype(np.float32)
    return replace(rec, rate_hz=rate_hz, acc=acc.astype(np.float32), rpm=rpm)


# ---- UCI cooler fan (50 Hz; see fanlog.datasets) -------------------------------------------

def uci_recordings(root: Path = EXTERNAL / "uci-accelerometer") -> list[Recording]:
    clips = load_uci_accelerometer(root)
    return [
        Recording(
            source="uci",
            name=f"{cond}_{pct}",
            rate_hz=UCI_RATE_HZ,
            acc=acc.astype(np.float32),
            acc_units="g",
            fan="uci_akasa",
            # No balanced run exists; the least-imbalanced placement stands in for normal.
            condition=NORMAL if UCI_SEVERITY[cond] == 0 else f"imbalance_{cond}",
            severity=UCI_SEVERITY[cond],
            speed_pct=float(pct),
            # nominal: 1900 rpm max per the dataset page; the actual speed was not measured
            rpm=np.full(len(acc), UCI_MAX_RPM * pct / 100, np.float32),
        )
        for (cond, pct), acc in sorted(clips.items())
    ]


# ---- Fraunhofer unbalance (4096 Hz; see fanlog.datasets) -----------------------------------

FRAUNHOFER_DIR = EXTERNAL / "fraunhofer-unbalance"
FRAUNHOFER_RATE_HZ = 4096.0
FRAUNHOFER_SKIP = 50_000   # warm-up samples the authors drop from the start of each file
FRAUNHOFER_UNBALANCE_MMG = {0: 0.0, 1: 45.9, 2: 60.7, 3: 75.5, 4: 152.1}


def fraunhofer_recordings(
    split: str = "D", rate_hz: float | None = BOARD_RATE_HZ, root: Path = FRAUNHOFER_DIR
) -> list[Recording]:
    """Load the five files of one split (D = development, E = evaluation) as Recordings.

    Resampled to rate_hz (default: our board's 833 Hz; None keeps 4096 Hz). The first load parses
    the CSVs from the zip and caches float32 arrays in <root>/cache/.
    """
    return [_fraunhofer_one(f"{level}{split}", rate_hz, Path(root)) for level in range(5)]


def _fraunhofer_one(file_id: str, rate_hz: float | None, root: Path) -> Recording:
    rate = rate_hz or FRAUNHOFER_RATE_HZ
    cache = root / "cache" / f"{file_id}_{rate:g}hz.npz"
    if cache.exists():
        z = np.load(cache)
        acc, rpm = z["acc"], z["rpm"]
    else:
        raw = _fraunhofer_read_csv(root, file_id)
        rec = Recording("fraunhofer", file_id, FRAUNHOFER_RATE_HZ, raw[:, 2:5], "", "", "", 0, rpm=raw[:, 1])
        rec = resample(rec, rate)
        acc, rpm = rec.acc, rec.rpm
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, acc=acc, rpm=rpm)
    # Measured_RPM updates once per second and has rare bad 1 s readings (up to ~4000 rpm, a few per
    # file); a 3 s median removes them.
    from scipy.ndimage import median_filter
    rpm = median_filter(rpm, size=int(3 * rate) | 1, mode="nearest")
    level = int(file_id[0])
    return Recording(
        source="fraunhofer",
        name=file_id,
        rate_hz=rate,
        acc=acc,
        acc_units="sensor output (units not stated by the dataset)",
        # The unbalance was dismantled and reassembled between D and E: treat as two mounts.
        fan=f"fraunhofer_{file_id[1]}",
        condition=NORMAL if level == 0 else "unbalance",
        severity=level,
        rpm=rpm,
        meta={"unbalance_mm_g": FRAUNHOFER_UNBALANCE_MMG[level]},
    )


def _fraunhofer_read_csv(root: Path, file_id: str) -> np.ndarray:
    import pandas as pd

    zips = sorted(root.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"no zip in {root}; run: python -m fanlog.datasets fraunhofer-unbalance")
    with zipfile.ZipFile(zips[0]) as zf:
        member = next(n for n in zf.namelist() if Path(n).name == f"{file_id}.csv")
        with zf.open(member) as f:
            df = pd.read_csv(f, usecols=["V_in", "Measured_RPM", "Vibration_1", "Vibration_2", "Vibration_3"],
                             dtype="float32")
    cols = df[["V_in", "Measured_RPM", "Vibration_1", "Vibration_2", "Vibration_3"]].to_numpy()
    return cols[FRAUNHOFER_SKIP:]


# ---- Our own sessions (fanlog.record -> fanlog.session) --------------------------------------

def session_recording(session_dir: str | Path) -> Recording:
    """Load one converted session (session.npz from fanlog.session) as a Recording.

    The whole session is returned, including speed changes; rpm (from the tach) follows them.
    """
    session_dir = Path(session_dir)
    meta = json.loads((session_dir / "meta.json").read_text())
    summary_path = session_dir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    if summary.get("imu_gaps"):
        raise ValueError(f"{session_dir}: IMU stream has gaps {summary['imu_gaps']}; not continuous")
    npz = dict(np.load(session_dir / "session.npz"))
    rate = float(npz["imu_rate_hz_est"])
    rate = rate if np.isfinite(rate) else BOARD_RATE_HZ
    n = len(npz["imu_counts"])
    rpm = None
    status_rpm = npz["status_rpm"]
    if np.isfinite(status_rpm).any():
        # STATUS frames carry imu_samples = index of the next IMU sample, so they map onto samples.
        ok = np.isfinite(status_rpm)
        rpm = np.interp(np.arange(n), npz["status_imu_samples"][ok], status_rpm[ok]).astype(np.float32)
    fault = meta.get("fault", "")
    return Recording(
        source="own",
        name=meta.get("session", session_dir.name),
        rate_hz=rate,
        acc=(npz["imu_counts"].astype(np.float64) * float(npz["imu_g_per_count"])).astype(np.float32),
        acc_units="g",
        fan=f"{meta.get('fan', '')}@{meta.get('mount', '')}",
        condition=fault,
        severity=0 if fault == NORMAL else 1,   # refined by rank_severities()
        rpm=rpm,
        meta={"session_dir": str(session_dir), **meta},
    )


def session_recordings(root: Path = REPO_ROOT / "data" / "raw") -> list[Recording]:
    """All converted sessions under data/raw/ (directories that contain session.npz)."""
    return rank_severities([session_recording(p.parent) for p in sorted(Path(root).glob("*/session.npz"))])


def rank_severities(recs: list[Recording]) -> list[Recording]:
    """Set severity 1, 2, ... by the number in meta["severity"] (e.g. "0.2g"), per fan and fault."""
    groups: dict[tuple[str, str], set[float]] = {}
    for r in recs:
        if r.is_fault:
            groups.setdefault((r.fan, r.condition), set()).add(_leading_number(r.meta.get("severity", "")))
    for r in recs:
        if r.is_fault:
            levels = sorted(groups[(r.fan, r.condition)])
            r.severity = levels.index(_leading_number(r.meta.get("severity", ""))) + 1
    return recs


def _leading_number(text: str) -> float:
    m = re.match(r"\s*([0-9]*\.?[0-9]+)", str(text))
    return float(m.group(1)) if m else 0.0


def load(source: str, **kwargs) -> list[Recording]:
    """Recordings by source name: "own", "fraunhofer" (kwarg split="D"/"E") or "uci"."""
    if source == "own":
        return session_recordings(**kwargs)
    if source == "fraunhofer":
        return fraunhofer_recordings(**kwargs)
    if source == "uci":
        return uci_recordings(**kwargs)
    raise ValueError(f"unknown source {source!r}")
