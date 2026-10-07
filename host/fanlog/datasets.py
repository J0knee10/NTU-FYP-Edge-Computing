"""Download public datasets into data/external/.

    python -m fanlog.datasets uci-accelerometer
"""

from __future__ import annotations

import argparse
import io
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATASETS = {
    # Sampaio et al. 2019, doi:10.24432/C5Q61V. Akasa AK-FN059 PC cooler fan with
    # blade weights (normal + two imbalance configurations), MMA8452Q accelerometer.
    "uci-accelerometer": "https://archive.ics.uci.edu/static/public/846/accelerometer.zip",
}


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
    print(f"extracted to {dest}: {', '.join(archive.namelist())}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", choices=sorted(DATASETS))
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "external"))
    args = ap.parse_args()
    download(args.name, Path(args.out))


if __name__ == "__main__":
    main()
