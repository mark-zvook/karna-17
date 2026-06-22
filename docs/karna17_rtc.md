# KARNA-17 — RTC Module Documentation

## Chip Selection: RV-3028-C7

### Why RV-3028-C7

| | RV-3028-C7 | DS3231 | PCF85063A |
|---|---|---|---|
| I2C address | **0x52** ✅ | 0x68 ❌ collision | 0x51 ✅ |
| Accuracy | **±1 ppm** | ±2 ppm | ±20 ppm |
| Temp. compensation | yes (internal) | yes (TCXO) | no |
| Backup current | **~45 nA** | ~3 µA | ~150 nA |
| CR2032 life | **>14 yr** | ~5 yr | ~4.5 yr |
| Linux driver | `rtc-rv3028` (5.7+) | `rtc-ds1307` | `rtc-pcf85063` |

**Decision:** RV-3028-C7 wins on all axes that matter for this system. The 0x52 address eliminates the MPU-6500 (0x68) address collision without hardware rework. At ±1 ppm the clock drifts ≤0.09 s/day — well within the ±2 s cold-start requirement even after a week without NTP.

### Address Collision Resolution

I2C-1 bus population after KARNA-17:

| Device | Address | Driver |
|--------|---------|--------|
| MPU-6500 (IMU) | 0x68 | `mpu6500` |
| INA219 (battery) | 0x40 | `ina219` |
| RV-3028-C7 (RTC) | **0x52** | `rtc-rv3028` |

No address changes needed on existing hardware.

---

## Schematic / Pinout

```
CM5 / Pi 5                          RV-3028-C7 (TDFN-8)
─────────────────────────────────────────────────────────
GPIO2 / SDA (pin 3)  ─────────────▶ SDA (pin 5)
GPIO3 / SCL (pin 5)  ─────────────▶ SCL (pin 6)
3.3V  (pin 1)        ─────────────▶ VDD (pin 1)   ──┬── 100nF ── GND
GND   (pin 6)        ─────────────▶ GND (pin 4)     │
                                     VBACKUP (pin 2) ─┤
                                                      │
                                     CR2032 (+) ──────┤
                                     CR2032 (-) ── GND
                                     INT (pin 3) ── NC (optional: GPIO for alarm)
                                     EVI (pin 7) ── NC
                                     CLKOUT (pin 8) ── NC
```

**Pull-ups:** 4.7 kΩ on SDA and SCL to 3.3V. Omit if the baseboard already has pull-ups for MPU-6500/INA219 (it does — check with oscilloscope; add only if rise time > 300 ns at 100 kHz).

**Backup supply:** CR2032 in Keystone BK-912 (THT, 20 mm). Wire (+) to VBACKUP, (–) to GND through a Schottky diode if the holder has no built-in protection, or use a holder with a protection diode built in. RV-3028 has an internal backup switchover circuit — no external diode strictly required.

---

## OS Configuration

### Step 1 — Apply overlay

```bash
sudo bash os/setup_rtc.sh
```

The script (idempotent) does:
1. Adds `dtoverlay=i2c-rtc,rv3028` to `/boot/firmware/config.txt`
2. Disables and masks `fake-hwclock.service`
3. Enables `systemd-timesyncd`
4. Installs and enables `karna-rtc-sync.path` + `.service`
5. Sets hwclock to UTC mode

### Step 2 — Reboot

```bash
sudo reboot
```

### Step 3 — Verify

```bash
# RTC chip detected on bus
i2cdetect -y 1
# Expect 0x52 present, 0x68 (IMU) and 0x40 (INA219) present, no conflicts

# Kernel driver loaded
dmesg | grep rtc
# Expect: rtc-rv3028 1-0052: registered as rtc0

cat /sys/class/rtc/rtc0/name
# rv3028

# Read hardware clock
sudo hwclock -r --utc --verbose

# Check time sync status
timedatectl
# Expect: System clock synchronized: yes (when network available)
#         RTC time: <current time>
```

### Verifying cold start without network

```bash
# 1. Disconnect WiFi
# 2. Reboot
# 3. Immediately after login:
timedatectl
date
sudo hwclock -r --utc
# System time and RTC time should match and be within ±2 s of reference
```

---

## NTP → RTC Sync Flow

```
Boot (no network)
  └─ kernel reads /dev/rtc0 via rtc-rv3028 driver
  └─ sets system clock from RTC

Network comes up (OTA connect)
  └─ systemd-timesyncd contacts NTP server
  └─ adjusts system clock (slewing, not stepping)
  └─ creates /run/systemd/timesync/synchronized
  └─ karna-rtc-sync.path detects file
  └─ activates karna-rtc-sync.service
  └─ runs: hwclock --systohc --utc
  └─ RTC now holds NTP-accurate time
```

---

## Python API

```python
from src.sensors.rtc import get_rtc_status, is_time_valid, sync_rtc_from_system

# In bootstrap, BEFORE forming LOGS_FOLDER:
if not is_time_valid():
    session_name = f"session_INVALIDTIME_{counter:04d}"
    # raise flag in telemetry / UI
else:
    session_name = "session_" + datetime.now().strftime("%d%m%Y-%H_%M")

# Full status (for UI / telemetry):
status = get_rtc_status()
# RtcStatus(is_valid=True, source='rtc', rtc_present=True, ntp_synced=False,
#           drift_seconds=0.4, system_unix=1750586400.0)

# Manual sync (normally done by systemd unit):
sync_rtc_from_system()
```

**`is_time_valid()` threshold:** `RTC_MIN_VALID_EPOCH = 1767225600` (2026-01-01 UTC). Update this constant at each firmware release to the build date.

---

## Drift Test Results

> **TODO — REQUIRES REAL HARDWARE**
> This section must be filled in after soldering the RV-3028-C7 module and running the
> drift logger on the actual CM5 board for ≥ 72 hours.  The numbers below are
> **datasheet-based estimates only, not measurements.**

**Expected (from RV-3028-C7 datasheet, –40 … +85 °C):**

| Metric | Datasheet spec | Required by KARNA-17 |
|--------|---------------|----------------------|
| Frequency error | ±1 ppm typ | ≤ ±5 ppm |
| Drift per day | ~0.09 s/day | — |
| Drift over 72 h | ~0.26 s | — |

**How to run the real measurement:**

```bash
# On the target board with RV-3028 soldered and NTP disabled:
echo "timestamp_utc,system_unix,rtc_unix,drift_s,elapsed_h" > data/drift_log.csv
START=$(date +%s)
while true; do
  NOW=$(date +%s)
  RTC=$(hwclock -r --utc 2>/dev/null | awk '{print $1"T"$2}')
  RTC_UNIX=$(date -d "$RTC" +%s 2>/dev/null || echo "")
  DRIFT=$(python3 -c "print($NOW - $RTC_UNIX)" 2>/dev/null || echo "")
  ELAPSED=$(python3 -c "print(round(($NOW - $START)/3600, 3))")
  echo "$NOW,$NOW,$RTC_UNIX,$DRIFT,$ELAPSED" >> data/drift_log.csv
  sleep 60
done
# Run for ≥ 72 hours, then analyse and fill in this section.
```

**Acceptance criterion (§9.2):** measured ≤ ±5 ppm over ≥ 72 h, CSV + graph delivered.

---

## Battery Life Calculation

| Parameter | Value |
|-----------|-------|
| Chip backup current (RV-3028) | 45 nA typical |
| CR2032 capacity | 225 mAh |
| Theoretical life | 225 mAh / 0.000045 mA = **5,000,000 h ≈ 571 years** |
| Practical (accounting for self-discharge) | **10–15 years** |

Battery self-discharge (CR2032: ~1% per year) dominates over chip consumption. Replace battery every 5 years as preventive maintenance.

---

## Integration with provision_cm5.sh

Add to `tools/provision_cm5.sh` after the base OS configuration step:

```bash
# KARNA-17 — RTC setup
echo "[provision] Setting up RTC (RV-3028-C7)..."
bash "$KARNA_SRC/os/setup_rtc.sh"
```

The `setup_rtc.sh` script is idempotent — safe to run on every provision.

---

## Troubleshooting

**`/dev/rtc0` does not exist after reboot**  
→ Check `dmesg | grep -i i2c` and `dmesg | grep -i rv3028`. Verify the chip is soldered and VDD/GND are correct. Confirm `dtoverlay=i2c-rtc,rv3028` is in `config.txt`.

**`hwclock -r` returns wrong year (1970 or 2000)**  
→ RTC lost power (dead/missing battery, or backup not wired). Set time: `sudo hwclock --set --date="$(date -u)" --utc`, then install battery.

**`i2cdetect` shows `0x52` but also another device colliding**  
→ Something else is at 0x52. Use `i2cdetect -y 1` to map the full bus. If another device claims 0x52, move RTC to a software I2C bus (dtoverlay=i2c-gpio,bus=4,i2c_gpio_sda=XX,i2c_gpio_scl=YY) and change `RTC_I2C_BUS = 4` in `sa_config.py`.

**`is_time_valid()` returns False even though clock looks right**  
→ `RTC_MIN_VALID_EPOCH` is a firmware build-date constant. If system time is correct but before 2026-01-01, the threshold needs updating. Run `python3 -c "import time; print(time.time(), 1767225600)"` to compare.
