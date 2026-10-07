"""Record a labelled session from the logger firmware.

Examples:

    python -m fanlog.record --list-ports
    python -m fanlog.record --fan pc01 --mount plateA --fault normal \
        --profile host/profiles/speed_sweep.json
    python -m fanlog.record --fan pc01 --mount plateA --fault imbalance --severity 0.2g \
        --pwm 700 --duration 300 --audio

Each run creates data/raw/<timestamp>_<fan>_<fault>_<severity>/ with meta.json,
events.jsonl, stream.bin and (after conversion) session.npz and summary.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports

from .protocol import FrameParser, FrameType, decode_info, decode_status
from .session import convert

ARDUINO_VID = 0x2341
FAULTS = ("normal", "imbalance", "blade_damage", "loose_mount", "bearing_wear", "obstruction", "other")
REPO_ROOT = Path(__file__).resolve().parents[2]


class BoardLink:
    """Serial link that parses frames and optionally tees raw bytes to a file."""

    def __init__(self, port: str) -> None:
        self.ser = serial.Serial(port, 115200, timeout=0.05)
        self.parser = FrameParser()
        self.raw = None
        self.last_status: dict | None = None
        self.prev_status: dict | None = None
        self.info: dict | None = None
        self.texts: list[str] = []

    def start_raw(self, path: Path) -> None:
        self.raw = path.open("wb")

    def close(self) -> None:
        if self.raw:
            self.raw.close()
        self.ser.close()

    def send(self, cmd: str) -> None:
        self.ser.write((cmd + "\n").encode("ascii"))

    def pump(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while True:
            data = self.ser.read(self.ser.in_waiting or 1)
            if data:
                if self.raw:
                    self.raw.write(data)
                for f in self.parser.feed(data):
                    if f.type == FrameType.STATUS:
                        self.prev_status, self.last_status = self.last_status, decode_status(f.payload)
                    elif f.type == FrameType.INFO:
                        self.info = decode_info(f.payload)
                    elif f.type == FrameType.TEXT:
                        self.texts.append(f.payload.decode("ascii", "replace"))
            if time.monotonic() >= end:
                return

    def command(self, cmd: str, timeout: float = 1.5) -> str | None:
        """Send a command and wait for its OK/ERR/PONG reply."""
        n = len(self.texts)
        self.send(cmd)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            if len(self.texts) > n:
                return self.texts[-1]
        return None


def find_port() -> str:
    ports = [p.device for p in list_ports.comports() if p.vid == ARDUINO_VID]
    if len(ports) != 1:
        sys.exit(f"Could not pick a board automatically (Arduino ports: {ports}). Use --port.")
    return ports[0]


def load_profile(args) -> dict:
    if args.profile:
        profile = json.loads(Path(args.profile).read_text())
        profile.setdefault("name", Path(args.profile).stem)
        return profile
    if args.duration is None:
        sys.exit("Give either --profile or --duration (with optional --pwm).")
    return {"name": "constant", "steps": [{"pwm": args.pwm, "seconds": args.duration, "label": "constant"}]}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", text).strip("-") or "none"


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def live_line(link: BoardLink, ppr: int) -> str:
    s, p = link.last_status, link.prev_status
    if not s or not p:
        return "waiting for status..."
    dt = ((s["t_us"] - p["t_us"]) & 0xFFFFFFFF) / 1e6 or float("nan")
    rpm = (s["tach_pulses"] - p["tach_pulses"]) / ppr / dt * 60
    imu_rate = (s["imu_samples"] - p["imu_samples"]) / dt
    temp = s["temp_centi_c"] / 100 if s["temp_centi_c"] != -32768 else float("nan")
    return (
        f"pwm={s['pwm_permille'] / 10:5.1f}%  rpm={rpm:6.0f}  imu={imu_rate:6.1f} Hz  "
        f"overruns={s['imu_overruns']}  audio_drop={s['audio_dropped']}  temp={temp:4.1f}C  "
        f"crc_err={link.parser.crc_errors}  lost={link.parser.frames_lost}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    ap.add_argument("--port", help="serial port (default: the only Arduino found)")
    ap.add_argument("--fan", help="fan id, e.g. pc01")
    ap.add_argument("--mount", default="default", help="mounting setup id, e.g. plateA")
    ap.add_argument("--fault", choices=FAULTS, help="fault label for the whole session")
    ap.add_argument("--severity", default="none", help="e.g. 0.2g, mild, 25pct")
    ap.add_argument("--notes", default="", help="free-text notes")
    ap.add_argument("--profile", help="JSON speed profile (see host/profiles)")
    ap.add_argument("--pwm", type=int, default=None, help="constant duty in permille (with --duration)")
    ap.add_argument("--duration", type=float, help="seconds, for a constant-speed session")
    ap.add_argument("--audio", action="store_true", help="also stream the microphone")
    ap.add_argument("--tach-ppr", type=int, default=2, help="tach pulses per revolution (PC fans: 2)")
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "raw"), help="output root")
    args = ap.parse_args()

    if args.list_ports:
        for p in list_ports.comports():
            tag = "  <- Arduino" if p.vid == ARDUINO_VID else ""
            print(f"{p.device}: {p.description}{tag}")
        return
    if not args.fan or not args.fault:
        ap.error("--fan and --fault are required")

    profile = load_profile(args)
    link = BoardLink(args.port or find_port())

    # Bring the board to a known state and read its configuration.
    link.send("STOP")
    link.pump(0.3)
    link.send("INFO")
    link.pump(1.0)
    if link.info is None:
        link.close()
        sys.exit("No INFO frame from the board. Is the logger firmware flashed?")
    if link.info.get("imu_ok") != "1":
        link.close()
        sys.exit(f"Board reports no IMU: {link.info}")
    has_pwm = int(link.info.get("pwm_pin", "-1")) >= 0

    started = datetime.now()
    name = f"{started:%Y%m%d-%H%M%S}_{slug(args.fan)}_{args.fault}_{slug(args.severity)}"
    session_dir = Path(args.out) / name
    session_dir.mkdir(parents=True)
    meta = {
        "session": name,
        "fan": args.fan,
        "mount": args.mount,
        "fault": args.fault,
        "severity": args.severity,
        "notes": args.notes,
        "audio": args.audio,
        "tach_pulses_per_rev": args.tach_ppr,
        "profile": profile,
        "board_info": link.info,
        "host_start": started.isoformat(timespec="seconds"),
        "git_commit": git_commit(),
    }
    (session_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    events = (session_dir / "events.jsonl").open("w")

    def log_event(event: str, **fields) -> None:
        board_t = link.last_status["t_us"] if link.last_status else None
        record = {"host_time": datetime.now().isoformat(timespec="milliseconds"), "board_t_us": board_t, "event": event}
        record.update(fields)
        events.write(json.dumps(record) + "\n")
        events.flush()

    def command(cmd: str, **fields) -> None:
        reply = link.command(cmd)
        log_event("command", cmd=cmd, reply=reply, **fields)
        if not reply or reply.startswith("ERR"):
            print(f"warning: '{cmd}' -> {reply}")

    link.start_raw(session_dir / "stream.bin")
    print(f"Recording {name}  ({'with' if args.audio else 'no'} audio)")
    aborted = False
    try:
        command(f"AUDIO {int(args.audio)}")
        first_pwm = profile["steps"][0].get("pwm")
        if has_pwm and first_pwm is not None:
            command(f"PWM {first_pwm}")
        command("START")
        for i, step in enumerate(profile["steps"]):
            pwm = step.get("pwm")
            if pwm is not None:
                if has_pwm:
                    command(f"PWM {pwm}", step=i)
                else:
                    print("warning: profile sets PWM but the board has no PWM pin; ignoring")
            log_event("step", step=i, label=step.get("label"), pwm=pwm, seconds=step["seconds"])
            print(f"step {i + 1}/{len(profile['steps'])}: {step.get('label', '')} pwm={pwm} for {step['seconds']} s")
            step_end = time.monotonic() + step["seconds"]
            while time.monotonic() < step_end:
                link.pump(min(1.0, step_end - time.monotonic()))
                print("  " + live_line(link, args.tach_ppr), end="\r")
            print()
    except KeyboardInterrupt:
        aborted = True
        print("\ninterrupted, stopping...")
    finally:
        command("STOP")
        link.pump(0.5)
        log_event("end", aborted=aborted)
        events.close()
        link.close()

    meta["host_end"] = datetime.now().isoformat(timespec="seconds")
    meta["aborted"] = aborted
    (session_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    summary = convert(session_dir)
    problems = []
    if summary["crc_errors"] or summary["frames_lost"]:
        problems.append(f"{summary['crc_errors']} CRC errors, {summary['frames_lost']} frames lost")
    if summary["imu_gaps"] or summary["imu_overruns"]:
        problems.append(f"IMU gaps {summary['imu_gaps'][:3]}, overruns {summary['imu_overruns']}")
    if summary["audio_dropped"] or summary["audio_gaps"]:
        problems.append(f"audio dropped {summary['audio_dropped']} samples")
    print(f"saved {session_dir}")
    print(f"  imu: {summary['imu_samples']} samples, est. rate {summary['imu_rate_hz_est']} Hz")
    if args.audio:
        print(f"  audio: {summary['audio_samples']} samples")
    for p in problems:
        print(f"  WARNING: {p}")


if __name__ == "__main__":
    main()
