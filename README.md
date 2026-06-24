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

**Drift test:** ✅ 27 h real measurement — **-0.026 ppm**, 95% CI [-0.038, -0.014] ppm, PASS (130× within ±5 ppm spec). See `docs/3h_results_karna17_rtc.md §Drift Test Results`.

---

## Install

```bash
sudo bash os/setup_rtc.sh
```

---

## Drift measurement (on the board)

```bash
# Start logger in background (72 h full run):
nohup bash tools/drift_watch.sh > data/drift_watch.log 2>&1 &
echo "Watch PID: $!"

# Or a shorter ad-hoc run:
nohup python3 tools/drift_logger.py --output data/drift_log.csv > data/drift_logger.log 2>&1 &
echo $!

# Check progress any time:
tail -f data/drift_watch.log        # watch script status + checkpoints
tail -f data/drift_logger.log       # raw logger output

# Analyse (works on partial data):
python3 tools/drift_analysis.py data/drift_log_72h.csv

# Stop early if needed:
pkill -f drift_logger.py && pkill -f drift_watch.sh
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
tools/drift_analysis.py                Linear regression + extrapolation to 72h/30d/1y
tools/drift_watch.sh                   72h watch script with 24h/48h/72h checkpoints
docs/3h_results_karna17_rtc.md         Full documentation + drift test results
data/drift_log.csv                     Phase 1: 3h real measurement (181 samples)
data/drift_log_24h.csv                 Phase 2: 27h real measurement (1622 samples)
```
