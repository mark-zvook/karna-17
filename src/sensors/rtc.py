"""
RTC adapter for KARNA-17.

Reads time validity state from the OS (timedatectl, hwclock) — never touches
the I2C chip directly in hot-path.  Kernel driver (rtc-rv3028) owns the chip.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Literal, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrors sa_config.py RTC_I2C_* block)
# ---------------------------------------------------------------------------
RTC_I2C_BUS         = 1
RTC_I2C_ADDRESS     = 0x52          # RV-3028-C7; DS3231 = 0x68 (collision!), PCF85063A = 0x51
RTC_MIN_VALID_EPOCH = 1767225600    # 2026-01-01 00:00:00 UTC — update per firmware release date
RTC_DRIFT_WARN_S    = 5.0           # |system - rtc| threshold for UI warning

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
TimeSource = Literal["rtc", "ntp", "unknown", "manual"]


@dataclass(frozen=True)
class RtcStatus:
    is_valid: bool                  # system_unix >= RTC_MIN_VALID_EPOCH
    source: TimeSource              # how current system time was set
    system_unix: float              # time.time() at sampling instant
    rtc_present: bool               # kernel driver active + /dev/rtc0 accessible
    ntp_synced: bool                # systemd-timesyncd reports synchronized
    drift_seconds: Optional[float]  # system − rtc reading; None if hwclock unavailable


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: float = 3.0) -> str:
    """Run a command, return stdout. Returns '' on any failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception as exc:
        log.debug("RTC: %s failed: %s", " ".join(cmd), exc)
        return ""


def _parse_timedatectl() -> dict[str, str]:
    """Parse timedatectl output into a key→value dict."""
    out = _run(["timedatectl"])
    result: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _rtc_present() -> bool:
    """True if kernel RTC driver is active (device node exists and is readable)."""
    return os.path.exists("/dev/rtc0")


def _ntp_synced(tdc: dict[str, str]) -> bool:
    return tdc.get("System clock synchronized", "no").lower() == "yes"


def _rtc_unix_time() -> Optional[float]:
    """Read hardware clock via hwclock -r --utc. Returns Unix timestamp or None."""
    out = _run(["hwclock", "-r", "--utc"])
    # output: "2026-06-16 11:42:07.123456+00:00"
    if not out:
        return None
    try:
        import datetime
        ts = out.strip()
        # hwclock may emit trailing " seconds" on some versions — strip it
        ts = ts.split(" seconds")[0].strip()
        dt = datetime.datetime.fromisoformat(ts)
        return dt.timestamp()
    except Exception as exc:
        log.debug("RTC: hwclock parse failed: %s — raw: %r", exc, out)
        return None


def _detect_source(ntp_synced: bool, rtc_present: bool) -> TimeSource:
    if ntp_synced:
        return "ntp"
    if rtc_present:
        return "rtc"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_rtc_status() -> RtcStatus:
    """
    Sample RTC / time state.  Cheap: one subprocess call to timedatectl,
    one optional call to hwclock.  Not for per-frame use.
    """
    now = time.time()
    tdc = _parse_timedatectl()
    rtc_present = _rtc_present()
    ntp_ok = _ntp_synced(tdc)
    source = _detect_source(ntp_ok, rtc_present)
    is_valid = now >= RTC_MIN_VALID_EPOCH

    drift: Optional[float] = None
    if rtc_present:
        rtc_ts = _rtc_unix_time()
        if rtc_ts is not None:
            drift = now - rtc_ts

    if drift is not None and abs(drift) > RTC_DRIFT_WARN_S:
        log.warning(
            "RTC: large drift %.1f s (threshold %.1f s)", drift, RTC_DRIFT_WARN_S
        )

    return RtcStatus(
        is_valid=is_valid,
        source=source,
        system_unix=now,
        rtc_present=rtc_present,
        ntp_synced=ntp_ok,
        drift_seconds=drift,
    )


def is_time_valid() -> bool:
    """
    True if system clock is at or after RTC_MIN_VALID_EPOCH.
    Call in bootstrap BEFORE forming LOGS_FOLDER to avoid session name collisions.
    """
    return time.time() >= RTC_MIN_VALID_EPOCH


def sync_rtc_from_system() -> bool:
    """
    Write system clock to hardware RTC (hwclock --systohc).
    Normally done automatically by karna-rtc-sync.service after NTP sync;
    this function exists for manual / UI-triggered calls.
    Returns True on success.
    """
    out = _run(["hwclock", "--systohc"])
    # hwclock --systohc exits 0 and prints nothing on success
    success = out == "" or out.strip() == ""
    # Re-run with explicit check via return code — _run hides it, so use subprocess directly
    try:
        cp = subprocess.run(
            ["hwclock", "--systohc"],
            capture_output=True,
            timeout=5,
        )
        success = cp.returncode == 0
    except Exception as exc:
        log.error("RTC: hwclock --systohc failed: %s", exc)
        return False
    if success:
        log.info("RTC: hardware clock updated from system time")
    else:
        log.error("RTC: hwclock --systohc returned non-zero")
    return success


def to_ws_message(status: RtcStatus) -> dict:
    """Serialise RtcStatus to WebSocket JSON payload (§4.3 contract)."""
    import datetime
    return {
        "type": "time_status",
        "is_valid": status.is_valid,
        "source": status.source,
        "rtc_present": status.rtc_present,
        "ntp_synced": status.ntp_synced,
        "drift_seconds": status.drift_seconds,
        "system_iso": datetime.datetime.fromtimestamp(
            status.system_unix, datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
