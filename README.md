# KARNA-17 RTC — Delivery Package

**RTC:** Built-in CM5 `rpi-rtc` (RP1 south bridge) · **Backup:** CR1220 coin cell · **Driver:** `rpi-rtc` (loaded automatically)

---

## What was found / done

The CM5 has a **built-in RTC** in its RP1 south bridge. No external I2C chip (DS3231/RV-3028) is needed or present. The baseboard has a CR1220 holder wired to the CM5 `VRTC` pin.

**Hardware state confirmed on the real board:**
```
i2cdetect -y 1:  0x50 (EEPROM), 0x64 (unknown), 0x68 (MPU-6500)
dmesg:           rpi-rtc registered as rtc0
/dev/rtc0:       exists, driver = rpi-rtc
Cold-start test: RTC held time across full power cut, delta = 1 s  ✓
```

**What was done:**
1. Inserted CR1220 battery into the baseboard holder (wired to VRTC)
2. Synced time via NTP: `timedatectl set-ntp true`
3. Wrote system time to RTC: `hwclock --systohc --utc`
4. Cold-start tested: time survived full power cut within ±1 s  ✓
5. OS config: `fake-hwclock` disabled, `systemd-timesyncd` enabled, `karna-rtc-sync.service` auto-syncs RTC after NTP

**Drift test:** ✅ Measured on real hardware — -0.111 ppm, 95% CI [-0.459, +0.238] ppm, PASS. See `docs/karna17_rtc.md §Drift Test Results`.

---

## Install

```bash
sudo bash os/setup_rtc.sh
```

---

## Drift measurement (on the board)

```bash
# Start logger in background (3 h default):
nohup python3 tools/drift_logger.py --output data/drift_log.csv > data/drift_logger.log 2>&1 &
echo $!

# Check progress any time:
tail -f data/drift_logger.log

# Analyse (works on partial data):
python3 tools/drift_analysis.py data/drift_log.csv
```

---

## Tests (no hardware needed)

```bash
pytest tests/test_rtc.py -v
```

---

## Files

```
hardware/bom.csv                       CR1220 battery only (RTC is built-in)
os/overlays/karna-rtc.txt              Notes (no dtoverlay needed for rpi-rtc)
os/systemd/karna-rtc-sync.service      hwclock --systohc after NTP sync (After=time-sync.target)
os/setup_rtc.sh                        Idempotent setup
src/sensors/rtc.py                     Python adapter (RtcStatus, is_time_valid, …)
tests/test_rtc.py                      34 pytest tests, all mocked
tools/drift_logger.py                  Samples hwclock vs system, writes CSV
tools/drift_analysis.py               Linear regression + extrapolation to 72h/30d/1y
docs/karna17_rtc.md                    Full documentation
data/drift_log.csv                     Drift measurements (fill by running drift_logger)
```
