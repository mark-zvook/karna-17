# Stub: RtcStatus dataclass + function signatures (contract from §4)
# Full implementation: src/sensors/rtc.py

from dataclasses import dataclass
from typing import Literal, Optional

TimeSource = Literal["rtc", "ntp", "unknown", "manual"]

@dataclass(frozen=True)
class RtcStatus:
    is_valid: bool                  # system_unix >= RTC_MIN_VALID_EPOCH
    source: TimeSource              # how system time was set
    system_unix: float              # time.time() at sampling instant
    rtc_present: bool               # /dev/rtc0 exists (kernel driver active)
    ntp_synced: bool                # systemd-timesyncd synchronized
    drift_seconds: Optional[float]  # system − rtc; None if hwclock unavailable


def get_rtc_status() -> RtcStatus:
    """Sample time state. Cheap: timedatectl + optional hwclock. Not for hot-path."""
    ...

def is_time_valid() -> bool:
    """True if time.time() >= RTC_MIN_VALID_EPOCH. Call in bootstrap before LOGS_FOLDER."""
    ...

def sync_rtc_from_system() -> bool:
    """Run hwclock --systohc. Returns True on success. Normally done by systemd unit."""
    ...
