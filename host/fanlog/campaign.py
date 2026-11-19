"""Run a long unattended recording campaign: back-to-back fanlog.record sessions.

    python -m fanlog.campaign --fan pc01 --mount tapeCorner --fault normal --until 07:30

Plan: a mount_check at the start and at the end (to see whether the mounting drifted),
and in between a repeating cycle of speed_sweep, speed_sweep_fine (5 % steps), constant_10min, benign_drift and a
30 min steady run at a different duty each cycle. Every session records audio.

Stops starting new sessions after --until (local time) or when <out>/STOP exists.
Keeps Windows awake while running. A failed session (board unplugged, port busy) is
logged and retried after a pause. Progress goes to <out>/campaign_<start>.log.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES = REPO_ROOT / "host" / "profiles"
STEADY_DUTIES = [500, 900, 300, 600, 800, 400, 1000, 700]


def keep_awake(on: bool) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def plan(cycle: int) -> list[tuple[str, list[str]]]:
    duty = STEADY_DUTIES[cycle % len(STEADY_DUTIES)]
    return [
        ("speed_sweep", ["--profile", str(PROFILES / "speed_sweep.json")]),
        # 5 % steps: the healthy curve of each feature vs speed needs finer sampling than 10 %.
        ("speed_sweep_fine", ["--profile", str(PROFILES / "speed_sweep_fine.json")]),
        ("constant_10min", ["--profile", str(PROFILES / "constant_10min.json")]),
        ("benign_drift", ["--profile", str(PROFILES / "benign_drift.json")]),
        (f"steady{duty // 10}", ["--pwm", str(duty), "--duration", "1800"]),
    ]


def until_time(text: str) -> datetime:
    now = datetime.now()
    hh, mm = (int(x) for x in text.split(":"))
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--fan", required=True)
    ap.add_argument("--mount", required=True)
    ap.add_argument("--fault", default="normal")
    ap.add_argument("--severity", default="none")
    ap.add_argument("--notes", default="")
    ap.add_argument("--until", default="07:30", help="local time HH:MM; no new session starts after it")
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "raw"))
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stop_at = until_time(args.until)
    log_path = out / f"campaign_{datetime.now():%Y%m%d-%H%M%S}.log"
    log = log_path.open("a", encoding="utf-8")

    def say(msg: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    def should_stop() -> bool:
        return datetime.now() >= stop_at or (out / "STOP").exists()

    def record(label: str, extra: list[str]) -> bool:
        cmd = [sys.executable, "-m", "fanlog.record", "--fan", args.fan, "--mount", args.mount,
               "--fault", args.fault, "--severity", args.severity, "--out", str(out),
               "--notes", f"{args.notes} [campaign {label}]".strip(), *extra]
        if args.port:
            cmd += ["--port", args.port]
        if not args.no_audio:
            cmd.append("--audio")
        session_log = out / f"campaign_{datetime.now():%Y%m%d-%H%M%S}_{label}.out"
        say(f"start {label}")
        with session_log.open("w", encoding="utf-8") as f:
            rc = subprocess.run(cmd, cwd=REPO_ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
        tail = session_log.read_text(encoding="utf-8", errors="replace").replace("\r", "\n").splitlines()
        summary = [t for t in tail if t.startswith(("saved", "  imu:", "  audio:", "  WARNING"))]
        say(f"end {label} rc={rc} " + " | ".join(s.strip() for s in summary))
        return rc == 0

    keep_awake(True)
    say(f"campaign start: fan={args.fan} mount={args.mount} fault={args.fault} until {stop_at:%H:%M}, log {log_path}")
    try:
        queue = [("mount_check_start", ["--profile", str(PROFILES / "mount_check.json")])]
        cycle = 0
        failures = 0
        while not should_stop():
            if not queue:
                queue = plan(cycle)
                cycle += 1
            label, extra = queue.pop(0)
            if record(label, extra):
                failures = 0
            else:
                failures += 1
                queue.insert(0, (label, extra))
                wait = min(600, 30 * failures)
                say(f"session failed ({failures} in a row); retrying in {wait} s")
                time.sleep(wait)
        if not (out / "STOP").exists():
            record("mount_check_end", ["--profile", str(PROFILES / "mount_check.json")])
    finally:
        keep_awake(False)
        say("campaign end")
        log.close()


if __name__ == "__main__":
    main()
