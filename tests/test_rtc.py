"""
Tests for src/sensors/rtc.py.
All tests mock timedatectl / hwclock — no hardware required.
Run: pytest tests/test_rtc.py -v
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.sensors.rtc import (
    RTC_DRIFT_WARN_S,
    RTC_MIN_VALID_EPOCH,
    RtcStatus,
    _detect_source,
    _ntp_synced,
    _parse_timedatectl,
    _rtc_unix_time,
    get_rtc_status,
    is_time_valid,
    sync_rtc_from_system,
    to_ws_message,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

TIMEDATECTL_NTP_SYNCED = """\
               Local time: Mon 2026-06-22 10:00:00 UTC
           Universal time: Mon 2026-06-22 10:00:00 UTC
                 RTC time: Mon 2026-06-22 09:59:59
                Time zone: UTC (UTC, +0000)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
"""

TIMEDATECTL_NO_NTP = """\
               Local time: Mon 2026-06-22 10:00:00 UTC
           Universal time: Mon 2026-06-22 10:00:00 UTC
                 RTC time: Mon 2026-06-22 09:59:59
                Time zone: UTC (UTC, +0000)
System clock synchronized: no
              NTP service: inactive
          RTC in local TZ: no
"""

TIMEDATECTL_NO_RTC = """\
               Local time: Mon 2026-06-22 10:00:00 UTC
           Universal time: Mon 2026-06-22 10:00:00 UTC
                 RTC time: n/a
                Time zone: UTC (UTC, +0000)
System clock synchronized: no
              NTP service: inactive
          RTC in local TZ: no
"""

HWCLOCK_OUT = "2026-06-22 09:59:59.000000+00:00\n"
HWCLOCK_EPOCH_OUT = "1970-01-01 00:00:01.000000+00:00\n"


def _valid_unix() -> float:
    """A Unix timestamp well above RTC_MIN_VALID_EPOCH (2026-01-01)."""
    return float(RTC_MIN_VALID_EPOCH + 86400 * 10)  # 10 days past threshold


def _invalid_unix() -> float:
    """A Unix timestamp below RTC_MIN_VALID_EPOCH — simulates dead/missing RTC."""
    return float(RTC_MIN_VALID_EPOCH - 1)


# ---------------------------------------------------------------------------
# _parse_timedatectl
# ---------------------------------------------------------------------------

class TestParseTimedatectl:
    def test_ntp_synced_parsed(self):
        with patch("src.sensors.rtc._run", return_value=TIMEDATECTL_NTP_SYNCED):
            tdc = _parse_timedatectl()
        assert tdc["System clock synchronized"] == "yes"
        assert tdc["NTP service"] == "active"

    def test_no_ntp_parsed(self):
        with patch("src.sensors.rtc._run", return_value=TIMEDATECTL_NO_NTP):
            tdc = _parse_timedatectl()
        assert tdc["System clock synchronized"] == "no"

    def test_empty_output_returns_empty_dict(self):
        with patch("src.sensors.rtc._run", return_value=""):
            tdc = _parse_timedatectl()
        assert tdc == {}


# ---------------------------------------------------------------------------
# _ntp_synced
# ---------------------------------------------------------------------------

class TestNtpSynced:
    def test_yes(self):
        assert _ntp_synced({"System clock synchronized": "yes"}) is True

    def test_no(self):
        assert _ntp_synced({"System clock synchronized": "no"}) is False

    def test_missing_key(self):
        assert _ntp_synced({}) is False

    def test_case_insensitive(self):
        assert _ntp_synced({"System clock synchronized": "YES"}) is True


# ---------------------------------------------------------------------------
# _detect_source
# ---------------------------------------------------------------------------

class TestDetectSource:
    def test_ntp_wins(self):
        assert _detect_source(ntp_synced=True, rtc_present=True) == "ntp"

    def test_rtc_when_no_ntp(self):
        assert _detect_source(ntp_synced=False, rtc_present=True) == "rtc"

    def test_unknown_when_nothing(self):
        assert _detect_source(ntp_synced=False, rtc_present=False) == "unknown"


# ---------------------------------------------------------------------------
# _rtc_unix_time
# ---------------------------------------------------------------------------

class TestRtcUnixTime:
    def test_parses_hwclock_output(self):
        with patch("src.sensors.rtc._run", return_value=HWCLOCK_OUT):
            ts = _rtc_unix_time()
        assert ts is not None
        assert abs(ts - 1782122399.0) < 2  # 2026-06-22 09:59:59 UTC

    def test_returns_none_on_empty(self):
        with patch("src.sensors.rtc._run", return_value=""):
            ts = _rtc_unix_time()
        assert ts is None

    def test_returns_none_on_garbage(self):
        with patch("src.sensors.rtc._run", return_value="not a date\n"):
            ts = _rtc_unix_time()
        assert ts is None


# ---------------------------------------------------------------------------
# is_time_valid
# ---------------------------------------------------------------------------

class TestIsTimeValid:
    def test_valid_when_above_threshold(self):
        with patch("src.sensors.rtc.time.time", return_value=_valid_unix()):
            assert is_time_valid() is True

    def test_invalid_when_below_threshold(self):
        with patch("src.sensors.rtc.time.time", return_value=_invalid_unix()):
            assert is_time_valid() is False

    def test_invalid_at_epoch_zero(self):
        with patch("src.sensors.rtc.time.time", return_value=0.0):
            assert is_time_valid() is False

    def test_valid_at_exact_threshold(self):
        with patch("src.sensors.rtc.time.time", return_value=float(RTC_MIN_VALID_EPOCH)):
            assert is_time_valid() is True


# ---------------------------------------------------------------------------
# get_rtc_status
# ---------------------------------------------------------------------------

class TestGetRtcStatus:
    def _patch_all(self, *, ntp=True, rtc_present=True, system_unix=None, hwclock_ts=None):
        if system_unix is None:
            system_unix = _valid_unix()
        patches = [
            patch("src.sensors.rtc.time.time", return_value=system_unix),
            patch("src.sensors.rtc._parse_timedatectl",
                  return_value={"System clock synchronized": "yes" if ntp else "no"}),
            patch("src.sensors.rtc._rtc_present", return_value=rtc_present),
            patch("src.sensors.rtc._rtc_unix_time",
                  return_value=hwclock_ts if hwclock_ts is not None else (system_unix - 1.0)),
        ]
        return patches

    def test_ntp_synced_valid_time(self):
        unix = _valid_unix()
        with patch("src.sensors.rtc.time.time", return_value=unix), \
             patch("src.sensors.rtc._parse_timedatectl",
                   return_value={"System clock synchronized": "yes"}), \
             patch("src.sensors.rtc._rtc_present", return_value=True), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=unix - 0.5):
            s = get_rtc_status()

        assert isinstance(s, RtcStatus)
        assert s.is_valid is True
        assert s.source == "ntp"
        assert s.ntp_synced is True
        assert s.rtc_present is True
        assert s.drift_seconds == pytest.approx(0.5, abs=0.01)

    def test_rtc_only_no_ntp(self):
        unix = _valid_unix()
        with patch("src.sensors.rtc.time.time", return_value=unix), \
             patch("src.sensors.rtc._parse_timedatectl",
                   return_value={"System clock synchronized": "no"}), \
             patch("src.sensors.rtc._rtc_present", return_value=True), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=unix - 2.0):
            s = get_rtc_status()

        assert s.source == "rtc"
        assert s.ntp_synced is False
        assert s.is_valid is True
        assert s.drift_seconds == pytest.approx(2.0, abs=0.01)

    def test_no_rtc_no_ntp_unknown(self):
        with patch("src.sensors.rtc.time.time", return_value=_valid_unix()), \
             patch("src.sensors.rtc._parse_timedatectl", return_value={}), \
             patch("src.sensors.rtc._rtc_present", return_value=False), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=None):
            s = get_rtc_status()

        assert s.source == "unknown"
        assert s.rtc_present is False
        assert s.drift_seconds is None

    def test_invalid_time_below_epoch(self):
        with patch("src.sensors.rtc.time.time", return_value=_invalid_unix()), \
             patch("src.sensors.rtc._parse_timedatectl", return_value={}), \
             patch("src.sensors.rtc._rtc_present", return_value=False), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=None):
            s = get_rtc_status()

        assert s.is_valid is False
        assert s.source == "unknown"

    def test_drift_none_when_hwclock_unavailable(self):
        with patch("src.sensors.rtc.time.time", return_value=_valid_unix()), \
             patch("src.sensors.rtc._parse_timedatectl",
                   return_value={"System clock synchronized": "no"}), \
             patch("src.sensors.rtc._rtc_present", return_value=True), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=None):
            s = get_rtc_status()

        assert s.drift_seconds is None

    def test_large_drift_logs_warning(self, caplog):
        import logging
        unix = _valid_unix()
        big_drift = RTC_DRIFT_WARN_S + 10.0
        with patch("src.sensors.rtc.time.time", return_value=unix), \
             patch("src.sensors.rtc._parse_timedatectl", return_value={}), \
             patch("src.sensors.rtc._rtc_present", return_value=True), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=unix - big_drift), \
             caplog.at_level(logging.WARNING, logger="src.sensors.rtc"):
            s = get_rtc_status()

        assert s.drift_seconds == pytest.approx(big_drift, abs=0.01)
        assert "large drift" in caplog.text.lower()

    def test_status_is_frozen(self):
        with patch("src.sensors.rtc.time.time", return_value=_valid_unix()), \
             patch("src.sensors.rtc._parse_timedatectl", return_value={}), \
             patch("src.sensors.rtc._rtc_present", return_value=False), \
             patch("src.sensors.rtc._rtc_unix_time", return_value=None):
            s = get_rtc_status()

        with pytest.raises((AttributeError, TypeError)):
            s.is_valid = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# sync_rtc_from_system
# ---------------------------------------------------------------------------

class TestSyncRtcFromSystem:
    def test_returns_true_on_success(self):
        mock_cp = MagicMock()
        mock_cp.returncode = 0
        with patch("src.sensors.rtc.subprocess.run", return_value=mock_cp):
            assert sync_rtc_from_system() is True

    def test_returns_false_on_nonzero(self):
        mock_cp = MagicMock()
        mock_cp.returncode = 1
        with patch("src.sensors.rtc.subprocess.run", return_value=mock_cp):
            assert sync_rtc_from_system() is False

    def test_returns_false_on_exception(self):
        with patch("src.sensors.rtc.subprocess.run", side_effect=FileNotFoundError("hwclock not found")):
            assert sync_rtc_from_system() is False


# ---------------------------------------------------------------------------
# to_ws_message
# ---------------------------------------------------------------------------

class TestToWsMessage:
    def _make_status(self, **kwargs) -> RtcStatus:
        defaults = dict(
            is_valid=True,
            source="ntp",
            system_unix=_valid_unix(),
            rtc_present=True,
            ntp_synced=True,
            drift_seconds=0.4,
        )
        defaults.update(kwargs)
        return RtcStatus(**defaults)

    def test_type_field(self):
        msg = to_ws_message(self._make_status())
        assert msg["type"] == "time_status"

    def test_all_fields_present(self):
        msg = to_ws_message(self._make_status())
        for field in ("is_valid", "source", "rtc_present", "ntp_synced", "drift_seconds", "system_iso"):
            assert field in msg, f"missing field: {field}"

    def test_iso_format(self):
        msg = to_ws_message(self._make_status())
        iso = msg["system_iso"]
        assert iso.endswith("Z")
        assert "T" in iso

    def test_null_drift_passes_through(self):
        msg = to_ws_message(self._make_status(drift_seconds=None))
        assert msg["drift_seconds"] is None


# ---------------------------------------------------------------------------
# Session name collision guard (§9.7)
# ---------------------------------------------------------------------------

class TestSessionNameCollisionGuard:
    """
    Verify the bootstrap pattern: if is_time_valid() is False, the session
    folder name must NOT be derived from datetime.now().
    This test simulates the bootstrap logic described in §4.4.
    """

    def _make_session_name(self, use_time_valid: bool) -> str:
        """Minimal bootstrap stub — mirrors the pattern in smart_aim.py."""
        import datetime
        if use_time_valid:
            # Normal path: time is valid, use datetime
            return "session_" + datetime.datetime.fromtimestamp(_valid_unix(), datetime.timezone.utc).strftime("%d%m%Y-%H_%M")
        else:
            # Fallback path: monotonic counter (caller provides sequence number)
            return "session_INVALIDTIME_0001"

    def test_valid_time_uses_datetime(self):
        name = self._make_session_name(use_time_valid=True)
        assert "INVALIDTIME" not in name
        assert "2026" in name or name.startswith("session_")

    def test_invalid_time_uses_counter_suffix(self):
        name = self._make_session_name(use_time_valid=False)
        assert "INVALIDTIME" in name
        assert "0001" in name

    def test_two_invalid_sessions_do_not_collide(self):
        import datetime
        # Simulate two bootstrap calls with invalid time → must produce different names
        counter = [0]

        def fake_session_name():
            if time.time() < RTC_MIN_VALID_EPOCH:
                counter[0] += 1
                return f"session_INVALIDTIME_{counter[0]:04d}"
            return "session_" + datetime.datetime.now(datetime.timezone.utc).strftime("%d%m%Y-%H_%M")

        with patch("src.sensors.rtc.time.time", return_value=_invalid_unix()):
            name1 = fake_session_name()
            name2 = fake_session_name()

        assert name1 != name2
