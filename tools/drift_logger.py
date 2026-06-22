#!/usr/bin/env python3
"""
KARNA-17 RTC drift logger.

Samples system clock (NTP reference) vs hardware clock every INTERVAL seconds,
writes to CSV. Stop any time with Ctrl+C — partial data is fully usable.

Reads RTC via /sys/class/rtc/rtc0/{time,date} — no root needed.
Precision trick: waits for the RTC second to tick, records system time at that
exact moment → sub-millisecond sync without hwclock or root access.

Usage:
    python3 drift_logger.py --output data/drift_log.csv          # 3 h default
    python3 drift_logger.py --hours 1 --output data/drift_log.csv

Background (SSH-safe):
    nohup python3 drift_logger.py --output data/drift_log.csv > data/drift_logger.log 2>&1 &
    echo "PID: $!"

Analyse at any point:
    python3 drift_analysis.py data/drift_log.csv
"""

import argparse
import csv
import datetime
import sys
import time
from pathlib import Path

# Force line-buffered stdout so progress is visible in nohup logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

DEFAULT_HOURS    = 3.0
DEFAULT_INTERVAL = 60

RTC_TIME = Path("/sys/class/rtc/rtc0/time")
RTC_DATE = Path("/sys/class/rtc/rtc0/date")


def rtc_sample() -> tuple[float, float] | None:
    """
    Wait for the RTC second to tick, then return (system_unix, rtc_unix).

    Polls sysfs until the RTC time string changes — at that instant t_sys is
    within ~1 ms of the true hardware tick. No root needed; no subprocess.
    Timeout: 2 s (returns None if RTC is not ticking).
    """
    try:
        prev = RTC_TIME.read_text().strip()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            t_sys = time.time()
            cur   = RTC_TIME.read_text().strip()
            if cur != prev:
                date_str = RTC_DATE.read_text().strip()
                rtc_unix = datetime.datetime.fromisoformat(
                    f"{date_str}T{cur}+00:00"
                ).timestamp()
                return t_sys, rtc_unix
        return None
    except Exception:
        return None


def check_rtc() -> bool:
    try:
        RTC_TIME.read_text()
        RTC_DATE.read_text()
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="KARNA-17 RTC drift logger")
    parser.add_argument("--hours",    type=float, default=DEFAULT_HOURS,    metavar="H",
                        help=f"Duration in hours (default: {DEFAULT_HOURS})")
    parser.add_argument("--interval", type=int,   default=DEFAULT_INTERVAL, metavar="S",
                        help=f"Sample interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--output",   type=Path,  required=True,
                        help="Output CSV path, e.g. data/drift_log.csv")
    args = parser.parse_args()

    if not check_rtc():
        print("ERROR: cannot read /sys/class/rtc/rtc0/{time,date}", file=sys.stderr)
        print("       Is rpi-rtc loaded? Check: dmesg | grep rtc", file=sys.stderr)
        sys.exit(1)

    duration_s   = args.hours * 3600
    n_expected   = int(duration_s / args.interval)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print("KARNA-17 RTC drift logger")
    print(f"  Duration : {args.hours:.1f} h  (~{n_expected} samples)")
    print(f"  Interval : {args.interval} s")
    print(f"  Output   : {args.output}")
    print(f"  Method   : sysfs tick-detection (no root needed)")
    print(f"  Ctrl+C to stop early — partial data is analysable")
    print()

    # Take first sample (waits up to 2 s for tick)
    first = rtc_sample()
    if first is None:
        print("ERROR: RTC is not ticking (timeout waiting for second boundary)", file=sys.stderr)
        sys.exit(1)

    start_sys = first[0]

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "elapsed_s", "system_unix", "rtc_unix", "drift_s"])

        sample    = 0
        next_wake = start_sys

        try:
            while True:
                # Sleep until ~0.5 s before the next sample time, then wait for tick
                next_wake += args.interval
                sleep_for  = next_wake - time.time() - 0.5
                if sleep_for > 0:
                    time.sleep(sleep_for)

                result = rtc_sample()
                if result is None:
                    print("\nWARN: RTC read timed out — skipping sample", flush=True)
                    continue

                t_sys, rtc_unix = result
                elapsed = t_sys - start_sys
                drift   = t_sys - rtc_unix

                writer.writerow([
                    sample,
                    round(elapsed, 2),
                    round(t_sys,   4),
                    round(rtc_unix, 4),
                    round(drift,   6),
                ])
                f.flush()

                pct    = min(elapsed / duration_s * 100, 100)
                filled = int(pct / 100 * 30)
                bar    = "█" * filled + "░" * (30 - filled)
                print(
                    f"\r[{bar}] {pct:5.1f}%  "
                    f"t={elapsed/3600:.2f}h  "
                    f"drift={drift*1000:+.1f} ms  "
                    f"n={sample}",
                    end="", flush=True,
                )
                sample += 1

                if elapsed >= duration_s:
                    break

        except KeyboardInterrupt:
            print(f"\nStopped at {elapsed/3600:.2f} h ({sample} samples).")

    print()
    print(f"Done. {sample} samples → {args.output}")
    print(f"Run:  python3 drift_analysis.py {args.output}")


if __name__ == "__main__":
    main()
