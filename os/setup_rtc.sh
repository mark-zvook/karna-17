#!/usr/bin/env bash
# KARNA-17 — Idempotent RTC setup script
# Chip: RV-3028-C7 @ I2C-1 addr 0x52
#
# Run as root on the target CM5 board:
#   sudo bash os/setup_rtc.sh
#
# Safe to re-run; each step checks current state before modifying.
set -euo pipefail

BOOT_CONFIG=/boot/firmware/config.txt
OVERLAY_FRAGMENT="$(dirname "$0")/overlays/karna-rtc.txt"
SYSTEMD_DIR=/etc/systemd/system
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

info()  { echo "[karna-rtc] $*"; }
warn()  { echo "[karna-rtc] WARN: $*" >&2; }
check() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. Verify running as root
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "Error: run as root (sudo bash $0)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Install i2c-tools if missing
# ---------------------------------------------------------------------------
if ! check i2cdetect; then
  info "Installing i2c-tools..."
  apt-get install -y --no-install-recommends i2c-tools
fi

# ---------------------------------------------------------------------------
# 3. Add dtoverlay to config.txt (idempotent)
# ---------------------------------------------------------------------------
if grep -q "dtoverlay=i2c-rtc,rv3028" "$BOOT_CONFIG" 2>/dev/null; then
  info "dtoverlay=i2c-rtc,rv3028 already present in $BOOT_CONFIG — skipping"
else
  info "Adding RTC overlay to $BOOT_CONFIG"
  {
    echo ""
    echo "# --- KARNA-17 RTC (RV-3028-C7) ---"
    echo "dtparam=i2c_arm=on"
    echo "dtparam=i2c_arm_baudrate=100000"
    echo "dtoverlay=i2c-rtc,rv3028"
  } >> "$BOOT_CONFIG"
fi

# Warn if DS3231 overlay is already present (address collision risk)
if grep -q "dtoverlay=i2c-rtc,ds3231" "$BOOT_CONFIG" 2>/dev/null; then
  warn "ds3231 overlay found in $BOOT_CONFIG — DS3231 is 0x68 and COLLIDES with MPU-6500!"
  warn "Remove 'dtoverlay=i2c-rtc,ds3231' before rebooting."
fi

# ---------------------------------------------------------------------------
# 4. Disable and mask fake-hwclock
# ---------------------------------------------------------------------------
if systemctl is-enabled fake-hwclock.service &>/dev/null || \
   systemctl is-active  fake-hwclock.service &>/dev/null; then
  info "Disabling fake-hwclock..."
  systemctl stop    fake-hwclock.service 2>/dev/null || true
  systemctl disable fake-hwclock.service 2>/dev/null || true
  systemctl mask    fake-hwclock.service
else
  info "fake-hwclock not active — nothing to disable"
fi

# Remove fake-hwclock timestamp so it cannot override RTC on next boot
FAKE_HWCLOCK_DATA=/etc/fake-hwclock.data
if [[ -f "$FAKE_HWCLOCK_DATA" ]]; then
  info "Removing $FAKE_HWCLOCK_DATA"
  rm -f "$FAKE_HWCLOCK_DATA"
fi

# ---------------------------------------------------------------------------
# 5. Enable systemd-timesyncd
# ---------------------------------------------------------------------------
if ! systemctl is-enabled systemd-timesyncd.service &>/dev/null; then
  info "Enabling systemd-timesyncd..."
  systemctl enable systemd-timesyncd.service
fi
if ! systemctl is-active systemd-timesyncd.service &>/dev/null; then
  info "Starting systemd-timesyncd..."
  systemctl start systemd-timesyncd.service || true
fi

# ---------------------------------------------------------------------------
# 6. Install and enable karna-rtc-sync units
# ---------------------------------------------------------------------------
for unit in karna-rtc-sync.service karna-rtc-sync.path; do
  src="$SCRIPT_DIR/systemd/$unit"
  dst="$SYSTEMD_DIR/$unit"
  if [[ ! -f "$src" ]]; then
    warn "Unit file not found: $src — skipping"
    continue
  fi
  if cmp -s "$src" "$dst" 2>/dev/null; then
    info "$unit already up-to-date"
  else
    info "Installing $unit → $dst"
    cp "$src" "$dst"
  fi
done

systemctl daemon-reload
systemctl enable karna-rtc-sync.path
systemctl start  karna-rtc-sync.path 2>/dev/null || true

# ---------------------------------------------------------------------------
# 7. Configure hwclock to use UTC
# ---------------------------------------------------------------------------
ADJTIME=/etc/adjtime
if ! grep -q "^UTC$" "$ADJTIME" 2>/dev/null; then
  info "Setting hwclock to UTC mode"
  hwclock --systohc --utc 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 8. Post-setup verification (best-effort, no failure)
# ---------------------------------------------------------------------------
info "--- Post-setup check ---"

if [[ -e /dev/rtc0 ]]; then
  info "/dev/rtc0 exists — kernel driver loaded"
  RTC_NAME=$(cat /sys/class/rtc/rtc0/name 2>/dev/null || echo "unknown")
  info "RTC name: $RTC_NAME"
  hwclock -r --utc 2>/dev/null && info "hwclock -r OK" || warn "hwclock -r failed (may need reboot)"
else
  warn "/dev/rtc0 not found — reboot required to activate dtoverlay"
fi

if check i2cdetect; then
  info "i2cdetect -y 1:"
  i2cdetect -y 1 2>/dev/null || true
fi

info "Setup complete. Reboot if /dev/rtc0 was not present."
