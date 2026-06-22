#!/usr/bin/env bash
# KARNA-17 — Idempotent RTC setup for CM5 with built-in rpi-rtc
#
# The CM5's RP1 south bridge has an integrated RTC (driver: rpi-rtc).
# It appears as /dev/rtc0 automatically — no dtoverlay or external chip needed.
# The baseboard provides a CR1220 holder wired to VRTC for backup power.
#
# Run as root on the target board:
#   sudo bash os/setup_rtc.sh
#
# Safe to re-run; each step is idempotent.
set -euo pipefail

SYSTEMD_DIR=/etc/systemd/system
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

info() { echo "[karna-rtc] $*"; }
warn() { echo "[karna-rtc] WARN: $*" >&2; }

if [[ $EUID -ne 0 ]]; then
  echo "Error: run as root (sudo bash $0)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Verify rpi-rtc is active
# ---------------------------------------------------------------------------
if [[ -e /dev/rtc0 ]]; then
  RTC_NAME=$(cat /sys/class/rtc/rtc0/name 2>/dev/null || echo "unknown")
  info "/dev/rtc0 present — driver: $RTC_NAME"
else
  warn "/dev/rtc0 not found. Is this a CM5/Pi5 board? Check: dmesg | grep rtc"
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Disable and mask fake-hwclock
# ---------------------------------------------------------------------------
if systemctl list-unit-files fake-hwclock.service &>/dev/null; then
  if systemctl is-active fake-hwclock.service &>/dev/null; then
    info "Stopping fake-hwclock..."
    systemctl stop fake-hwclock.service
  fi
  systemctl disable fake-hwclock.service 2>/dev/null || true
  systemctl mask    fake-hwclock.service
  info "fake-hwclock masked"
else
  info "fake-hwclock not installed — nothing to disable"
fi

FAKE_DATA=/etc/fake-hwclock.data
if [[ -f "$FAKE_DATA" ]]; then
  info "Removing $FAKE_DATA"
  rm -f "$FAKE_DATA"
fi

# ---------------------------------------------------------------------------
# 3. Enable systemd-timesyncd
# ---------------------------------------------------------------------------
if ! systemctl is-enabled systemd-timesyncd.service &>/dev/null; then
  info "Enabling systemd-timesyncd..."
  systemctl enable systemd-timesyncd.service
fi
if ! systemctl is-active systemd-timesyncd.service &>/dev/null; then
  info "Starting systemd-timesyncd..."
  systemctl start systemd-timesyncd.service || true
fi
info "systemd-timesyncd: $(systemctl is-active systemd-timesyncd.service)"

# ---------------------------------------------------------------------------
# 4. Install karna-rtc-sync.service (hwclock --systohc after NTP sync)
# ---------------------------------------------------------------------------
UNIT=karna-rtc-sync.service
src="$SCRIPT_DIR/systemd/$UNIT"
dst="$SYSTEMD_DIR/$UNIT"
if [[ ! -f "$src" ]]; then
  warn "Unit file not found: $src — aborting"
  exit 1
fi
if cmp -s "$src" "$dst" 2>/dev/null; then
  info "$UNIT already up-to-date"
else
  info "Installing $UNIT"
  cp "$src" "$dst"
fi

systemctl daemon-reload
systemctl enable karna-rtc-sync.service
info "karna-rtc-sync.service enabled (runs once after time-sync.target)"

# ---------------------------------------------------------------------------
# 5. Ensure hwclock is in UTC mode
# ---------------------------------------------------------------------------
if ! grep -q "^UTC$" /etc/adjtime 2>/dev/null; then
  info "Configuring hwclock UTC mode"
  hwclock --systohc --utc 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 6. Verify
# ---------------------------------------------------------------------------
info "--- Verification ---"
info "RTC time : $(hwclock -r --utc 2>/dev/null || echo 'read failed')"
timedatectl | grep -E "RTC time|synchronized|NTP" | while read -r line; do
  info "$line"
done

info "Setup complete."
