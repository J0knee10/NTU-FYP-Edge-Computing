"""Follow the campaign log: build window tables for finished sessions, refresh the summary after
each cycle, exit on a failed session (code 2) or at campaign end (code 0)."""
import re
import subprocess
import sys
import time
from pathlib import Path

LOG = Path(sys.argv[1])
SP = Path(__file__).parent
PY = sys.executable
done = set()


def run(script, *args):
    r = subprocess.run([PY, str(SP / script), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


while True:
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        m = re.search(r"end (\S+) rc=0 saved (\S+)", line)
        if m and m.group(2) not in done:
            done.add(m.group(2))
            out = Path("results/own/overnight/windows") / (Path(m.group(2)).name + ".npz")
            if not out.exists():
                rc, txt = run("windows.py", m.group(2))
                print(f"processed {m.group(1)} {Path(m.group(2)).name} rc={rc}", flush=True)
                if rc:
                    print(txt, flush=True)
            if m.group(1).startswith("steady") or m.group(1) == "mount_check_end":
                rc, txt = run("night_summary.py", "--blades", "7")
                print(f"summary refreshed rc={rc}", flush=True)
    if any("failed" in l for l in lines[-3:]):
        print("SESSION FAILED:", lines[-3:], flush=True)
        sys.exit(2)
    if any("campaign end" in l for l in lines):
        rc, txt = run("night_summary.py", "--blades", "7")
        print("campaign ended; final summary rc", rc, flush=True)
        print(txt, flush=True)
        sys.exit(0)
    time.sleep(30)
