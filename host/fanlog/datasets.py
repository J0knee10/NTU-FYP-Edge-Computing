"""Download and load public datasets in data/external/.

    python -m fanlog.datasets uci-accelerometer

Roles (see docs/implementation_plan.md, "Datasets"): the UCI set is for developing steps 1-3 before
our own recordings exist and as a secondary benchmark in step 2. Reported RL and FL results use our
own recordings. Use fanlog.recording to get either source in the common Recording format.
"""

from __future__ import annotations

import argparse
import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = REPO_ROOT / "data" / "external"

DATASETS = {
    # Sampaio et al. 2019, doi:10.24432/C5Q61V (paper doi:10.3390/s19194342, PMC6806350).
    # Akasa AK-FN059 12 cm fan (1900 rpm max) with magnets on the blades, MMA8452Q at +/-8 g,
    # 12-bit, read by an Arduino UNO at 50 Hz (one sample per 20 ms). CC BY 4.0.
    "uci-accelerometer": "https://archive.ics.uci.edu/static/public/846/accelerometer.zip",
}

# The archive's CSV is named "accelerometer (1).csv"; it is saved under this name instead.
UCI_CSV = "accelerometer.csv"
UCI_RATE_HZ = 50.0

# wconfid -> which pair of blades carries a doubled weight. The UCI page calls 1 the "normal"
# configuration, but there is no balanced run: every configuration is an imbalance. Neighbouring
# weights add up and opposite weights largely cancel, and the data agrees (at 80 % speed the RMS
# is ~1.4 g, ~1.0 g and ~0.1 g). Labels are therefore the physical placement, not normal/fault.
UCI_CONDITIONS = {1: "neighbouring", 2: "perpendicular", 3: "opposite"}
# Relative imbalance, 0 = least. Use "opposite" as the reference class for anomaly benchmarks.
UCI_SEVERITY = {"opposite": 0, "perpendicular": 1, "neighbouring": 2}


def download(name: str, out_root: Path) -> Path:
    url = DATASETS[name]
    dest = out_root / name
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    for member in archive.namelist():
        target = (dest / member).resolve()
        if not target.is_relative_to(dest.resolve()):
            raise ValueError(f"unsafe path in archive: {member}")
    archive.extractall(dest)
    if name == "uci-accelerometer":
        _normalise_uci_name(dest)
    print(f"extracted to {dest}: {', '.join(p.name for p in dest.iterdir())}")
    return dest


def _normalise_uci_name(dest: Path) -> None:
    csvs = [p for p in dest.glob("*.csv") if p.name != UCI_CSV]
    if len(csvs) == 1:
        csvs[0].replace(dest / UCI_CSV)


def load_uci_accelerometer(root: Path = EXTERNAL / "uci-accelerometer") -> dict[tuple[str, int], np.ndarray]:
    """Load the UCI set as {(condition, speed_pct): xyz array of shape (n, 3) in g}.

    51 clips: 3 conditions x 17 speeds (20-100 % in 5 % steps), 3,000 samples (1 min at 50 Hz)
    each. Each clip is a separate recording, so clips must not be treated as one continuous stream.
    At 50 Hz the Nyquist limit is 25 Hz, so the 1x rotation frequency aliases above ~80 % speed.
    """
    root = Path(root)
    path = root / UCI_CSV
    if not path.exists():
        _normalise_uci_name(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run: python -m fanlog.datasets uci-accelerometer")
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    clips = {}
    for conf, cond in UCI_CONDITIONS.items():
        for pct in np.unique(data[data[:, 0] == conf, 1]).astype(int):
            rows = (data[:, 0] == conf) & (data[:, 1] == pct)
            clips[(cond, int(pct))] = data[rows, 2:5]
    return clips


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", choices=sorted(DATASETS))
    ap.add_argument("--out", default=str(EXTERNAL))
    args = ap.parse_args()
    download(args.name, Path(args.out))


if __name__ == "__main__":
    main()
