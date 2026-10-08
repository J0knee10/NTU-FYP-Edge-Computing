"""Common format for vibration data from any source.

Steps 1-4 (features, models, RL and FL simulators) take Recording objects only, so the same code
runs on the UCI set during development and on our own sessions for the reported results. Never
hard-code a sample rate downstream: use Recording.rate_hz (50 Hz for UCI, ~952 Hz for our board).

    from fanlog.recording import uci_recordings, session_recordings
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .datasets import EXTERNAL, UCI_RATE_HZ, UCI_SEVERITY, load_uci_accelerometer

REPO_ROOT = Path(__file__).resolve().parents[2]
NOMINAL_IMU_RATE_HZ = 952.0


@dataclass
class Recording:
    source: str          # "uci" or "own"
    name: str            # unique within the source
    rate_hz: float
    acc_g: np.ndarray    # (n, 3) acceleration in g, continuous in time
    fan: str             # one fan + mount; becomes one FL client in step 4
    condition: str       # "normal" or a fault label (own); blade placement (UCI)
    severity: str        # as recorded, e.g. "0.2g"; UCI: str of the relative rank 0-2
    speed_pct: float | None = None   # fixed speed, if the whole recording is at one speed
    meta: dict = field(default_factory=dict)


def uci_recordings(root: Path = EXTERNAL / "uci-accelerometer") -> list[Recording]:
    clips = load_uci_accelerometer(root)
    return [
        Recording(
            source="uci",
            name=f"{cond}_{pct}",
            rate_hz=UCI_RATE_HZ,
            acc_g=acc,
            fan="uci_akasa",
            condition=cond,
            severity=str(UCI_SEVERITY[cond]),
            speed_pct=float(pct),
        )
        for (cond, pct), acc in sorted(clips.items())
    ]


def session_recording(session_dir: str | Path) -> Recording:
    """Load one converted session (session.npz from fanlog.session) as a Recording.

    The whole session is returned, including speed changes; split it by profile step with the
    status_pwm_permille / status_t_us arrays in meta["npz"] when a fixed speed is needed.
    """
    session_dir = Path(session_dir)
    meta = json.loads((session_dir / "meta.json").read_text())
    summary_path = session_dir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    if summary.get("imu_gaps"):
        raise ValueError(f"{session_dir}: IMU stream has gaps {summary['imu_gaps']}; not continuous")
    npz = np.load(session_dir / "session.npz")
    rate = float(npz["imu_rate_hz_est"])
    return Recording(
        source="own",
        name=meta.get("session", session_dir.name),
        rate_hz=rate if np.isfinite(rate) else NOMINAL_IMU_RATE_HZ,
        acc_g=npz["imu_counts"].astype(np.float64) * float(npz["imu_g_per_count"]),
        fan=f"{meta.get('fan', '')}@{meta.get('mount', '')}",
        condition=meta.get("fault", ""),
        severity=meta.get("severity", ""),
        meta={"session_dir": str(session_dir), "npz": dict(npz), **meta},
    )


def session_recordings(root: Path = REPO_ROOT / "data" / "raw") -> list[Recording]:
    """All converted sessions under data/raw/ (directories that contain session.npz)."""
    return [session_recording(p.parent) for p in sorted(Path(root).glob("*/session.npz"))]
