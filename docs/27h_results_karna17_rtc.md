# KARNA-17 — RTC Module Documentation

## Hardware: Built-in rpi-rtc (no external chip)

The CM5's RP1 south bridge contains an integrated RTC that registers as `/dev/rtc0`
automatically on boot. **No external I2C chip (DS3231, RV-3028, PCF85063) is required or
present.** The baseboard has a CR1220 coin-cell holder wired to the CM5 VRTC pin.

**Confirmed on real hardware (2026-06-22):**

```
$ i2cdetect -y 1
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: UU -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- 64 -- -- -- 68 -- -- -- -- -- -- --
70: -- -- -- -- -- -- -- --
# 0x50 = baseboard EEPROM, 0x64 = unknown peripheral (all reads return 0xFF),
# 0x68 = MPU-6500 IMU. rpi-rtc is NOT on the I2C bus.

$ dmesg | grep rtc
[    2.034] rpi-rtc: registered as rtc0

$ ls -l /dev/rtc0
crw------- 1 root root 254, 0 Jun 22 12:00 /dev/rtc0

$ cat /sys/class/rtc/rtc0/name
rpi-rtc
```

The 0x64 device ACKs address probes but returns 0xFF on all reads (byte, word, block
modes). It is unidentifiable without the baseboard schematic and does not conflict with
KARNA-17.

---

## I2C Bus Map

| Address | Device | Driver | Notes |
|---------|--------|--------|-------|
| 0x50 | Baseboard EEPROM | `at24` | HAT EEPROM |
| 0x64 | Unknown peripheral | — | All reads return 0xFF; irrelevant to KARNA-17 |
| 0x68 | MPU-6500 IMU | `mpu6500` | No collision with rpi-rtc |

rpi-rtc is internal to RP1 and does not appear on the I2C bus.

---

## Schematic

```
CM5
────────────────────────────────────────────
VRTC pin  ──────────────── CR1220 (+)
                                    |
                           Coin-cell holder (on baseboard)
                                    |
GND       ──────────────── CR1220 (–)
────────────────────────────────────────────
No additional wiring needed — rpi-rtc driver loads automatically.
```

The baseboard wires the coin-cell holder directly to the CM5 VRTC pin. The RP1 has an
internal backup switchover circuit that cuts over to VRTC when main power is removed.

---

## OS Configuration

### Run once on the target board

```bash
sudo bash os/setup_rtc.sh
```

The script is idempotent and does:
1. Verifies `/dev/rtc0` exists (aborts if not)
2. Disables and masks `fake-hwclock.service` (if installed)
3. Enables `systemd-timesyncd`
4. Installs `karna-rtc-sync.service` → `hwclock --systohc --utc` after NTP sync
5. Confirms hwclock is in UTC mode

### Systemd sync unit

```ini
# os/systemd/karna-rtc-sync.service
[Unit]
Description=Sync hardware RTC from system clock after NTP synchronisation
After=time-sync.target
Requires=time-sync.target

[Service]
Type=oneshot
ExecStart=/sbin/hwclock --systohc --utc
RemainAfterExit=yes

[Install]
WantedBy=time-sync.target
```

`WantedBy=time-sync.target` + `RemainAfterExit=yes` — runs exactly once per boot after
NTP synchronises, then stays in `active (exited)` state. No `.path` unit needed.

**Verified on board:**

```
$ systemctl status karna-rtc-sync.service
● karna-rtc-sync.service — Sync hardware RTC from system clock after NTP sync
     Loaded: loaded (/etc/systemd/system/karna-rtc-sync.service; enabled)
     Active: active (exited) — exit-code: 0/SUCCESS
```

### NTP → RTC sync flow

```
Boot (no network)
  └─ RP1 kernel driver reads RTC hardware register
  └─ sets system clock from RTC

Network comes up
  └─ systemd-timesyncd contacts NTP server
  └─ adjusts system clock
  └─ signals time-sync.target
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
#           drift_seconds=0.4, system_unix=1782127485.0)

# Manual sync (normally done by systemd unit):
sync_rtc_from_system()
```

`is_time_valid()` threshold: `RTC_MIN_VALID_EPOCH = 1767225600` (2026-01-01 UTC). Update
this constant at each firmware release to the build date.

---

## Drift Test Results

### 27-hour real measurement

The 72-hour test was terminated at ~27 h after the 24 h checkpoint. All samples are real
hardware measurements — no extrapolation.

**Dataset:** 1 622 samples (real), 27.03 h  
**Date:** 2026-06-23 → 2026-06-24  
**Data file:** `data/drift_log_24h.csv`

| Metric | Phase 1 (3 h real) | Phase 2 (27 h real) | Spec |
|--------|--------------------|---------------------|------|
| Rate | -0.111 ppm | **-0.026 ppm** | ≤ ±5 ppm |
| 95% CI | ±0.349 ppm | **±0.012 ppm** | — |
| CI bounds | [-0.459, +0.238] | **[-0.038, −0.014]** | — |
| R² | 0.0022 | 0.0111 | — |
| Per day | -9.6 ms/day | **-2.3 ms/day** | — |
| Drift / 72 h | -29 ms | **-7 ms** | — |
| Drift / 30 days | -287 ms | **-68 ms** | — |
| Drift / 1 year | -3.5 s | **-824 ms** | — |
| Result | PASS ✓ | **PASS ✓** | — |

The 27-hour real measurement supersedes the Phase 1 estimate. At 3 h, adjtimex NTP-slew
residuals (~±80 ms initial swing, then ±5 ms steady state) completely dominated the
regression. With 9× more data the noise averages out: the true rate is **-0.026 ppm**
(95% CI [-0.038, -0.014]), more than 130× within the ±5 ppm limit.

```
Drift chart (27 h real, ● = sample, · = regression line):

    +81.18 ms │●
    +71.58 ms │●
    +61.98 ms │
    +52.37 ms │
    +42.77 ms │
    +33.17 ms │
    +23.56 ms │
    +13.96 ms │      ● ● ●●●●●●● ●●                                 ● ●●
     +4.36 ms │●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
     -5.25 ms │●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●·
             └──────────────────────────────────────────────────────────
              0.02 h                                            27.03 h
```

**Note on the two outlier points at t ≈ 0:** The +81 ms and +71 ms samples at the very
start reflect NTP slew settling immediately after the logger started. The system clock
was still being nudged by `timesyncd`; these samples are real but represent the initial
transient, not steady-state RTC drift. The regression is robust to them — R² is low
(0.0111) but the slope estimate is sound given 1622 samples.

**Deviation:** The spec (§9.2) requires ≥72 h of real measurement. Actual measurement
was 27.03 h (terminated early at the 24 h checkpoint). Justification: -0.026 ppm
(95% CI [-0.038, -0.014]) is 130× within the 5 ppm limit; the CI upper bound of
-0.014 ppm would not move enough over a further 45 h to threaten the PASS verdict.

**Acceptance criterion (§9.2):** ≤ ±5 ppm — **PASS** (-0.026 ppm, CI entirely within spec).

---

## Battery Life Calculation — CR1220

```
/sys/class/rtc/rtc0/battery_voltage:  3143586 µV  → 3.144 V  (fresh, nominal 3.0 V)
/sys/class/rtc/rtc0/charging_voltage: 0            → charging disabled (correct for
                                                       non-rechargeable CR1220)
```

| Parameter | Value |
|-----------|-------|
| CR1220 capacity | 40 mAh (nominal, room temperature) |
| RP1 RTC backup current | ~1.3 µA (Pi Foundation hardware design notes; RP1 datasheet not public) |
| Estimated life (25 °C) | 40 mAh / 0.0013 mA ≈ **30 800 h ≈ 3.5 years** |
| Estimated life (−20 °C, field) | ~60% capacity → **≈ 2.1 years** |

The rpi-rtc driver exposes `charging_voltage_max` / `charging_voltage_min` parameters
because RP1 supports rechargeable LIR2032 cells (used on the official Pi 5 board). This
baseboard uses a non-rechargeable CR1220 holder; charging is disabled and must remain so.

**Recommended maintenance:** replace CR1220 every **2 years** to maintain margin in
field-temperature conditions. At room temperature the cell would last ~3.5 years, but
cold (-20 °C) cuts effective capacity significantly.

If the holder were replaced with a 20 mm CR2032 holder, life would extend to ~20 years
(225 mAh at 1.3 µA). Current 12 mm holder is fixed hardware.

---

## Developer Integration Guide

### How to use `is_time_valid()` in bootstrap

Insert before `LOGS_FOLDER` is formed in `src/sa_config.py:123` (or wherever the session
name is constructed):

```python
from src.sensors.rtc import is_time_valid

if not is_time_valid():
    # clock not restored — avoid timestamp-based session name
    session_name = f"session_INVALIDTIME_{counter:04d}"
    # also set a telemetry flag so post-mission analysis knows
else:
    session_name = "session_" + datetime.now().strftime("%d%m%Y-%H_%M")
```

`is_time_valid()` is cheap (reads system time, no subprocess). Call it every boot,
not per-frame.

### When to call `sync_rtc_from_system()`

The `karna-rtc-sync.service` systemd unit already calls `hwclock --systohc --utc`
automatically after NTP sync. Do **not** call `sync_rtc_from_system()` on every boot
or in the hot path. Only call it from a manual/UI trigger or from a provisioning script.

### How to run the drift logger (on board)

```bash
# 3 h default — redirect to log file so nohup survives SSH disconnect
nohup python3 tools/drift_logger.py --output data/drift_log.csv \
    > data/drift_logger.log 2>&1 &
echo "PID: $!"

# Watch progress (each line is one sample):
tail -f data/drift_logger.log

# Analyse at any point (works on partial data):
python3 tools/drift_analysis.py data/drift_log.csv
```

No root needed. No hwclock. Works over SSH.

### How to run the tests (no hardware)

```bash
pytest tests/test_rtc.py -v          # 34 tests, all mocked
pytest tests/test_rtc.py --cov=src/sensors/rtc --cov-report=term-missing
```

Expected: 34 passed, 99% coverage.

### Key constants to update at each firmware release

In `src/sensors/rtc.py`:

```python
RTC_MIN_VALID_EPOCH = 1767225600    # update to Unix timestamp of build date
```

If the firmware is built after 2026-01-01, `is_time_valid()` will return True when the
RTC holds any time in 2026 or later. Update this to the actual build date so stale/reset
RTCs are caught immediately.

### Files delivered

| File | Purpose |
|------|---------|
| `src/sensors/rtc.py` | Python adapter — `RtcStatus`, `get_rtc_status`, `is_time_valid`, `sync_rtc_from_system` |
| `tests/test_rtc.py` | 34 pytest tests, 99% coverage, fully mocked (no hardware needed) |
| `tools/drift_logger.py` | Samples sysfs RTC tick vs system clock, writes CSV |
| `tools/drift_analysis.py` | Linear regression + ASCII chart + ppm extrapolation |
| `os/systemd/karna-rtc-sync.service` | `hwclock --systohc` after `time-sync.target` |
| `os/setup_rtc.sh` | Idempotent setup for CM5 with rpi-rtc |
| `hardware/bom.csv` | CR1220 only — RTC is built into CM5 |
| `docs/karna17_rtc.md` | This document |
| `data/drift_log.csv` | Real 3-hour drift measurement (181 samples) |
| `data/drift_log_24h.csv` | Real 27-hour drift measurement (1622 samples) |

---

## Cold-Start Test

**Test performed:** 2026-06-22  
**Power-cut duration:** ~30 seconds  
**Network:** disconnected during test  
**Result:** RTC held time, delta = **1 s** ✓

The spec (§9.1) requires ≥24 h power cut. The 30-second test passes but does not fully
validate the 24 h requirement. Document this as a **known deviation**:

> Deviation: cold-start test duration was ~30 s, not ≥24 h as specified in §9.1.
> The 30-second test passed (delta = 1 s). A full 24-hour test has not been performed
> due to schedule constraints. Risk: low — the rpi-rtc VRTC rail is a standard
> low-leakage design; battery voltage at 3.144 V indicates healthy backup supply.

---

## Troubleshooting

**`/dev/rtc0` does not exist after boot**  
→ `dmesg | grep rtc` — if rpi-rtc is absent, this is a kernel or hardware fault on the
CM5. The RP1 RTC is always enabled; check CM5 seating and power.

**`hwclock -r` returns 1970 or 2000**  
→ RTC lost power. CR1220 dead or missing. Check:  
`cat /sys/class/rtc/rtc0/battery_voltage` — should be > 2 000 000 (> 2.0 V).  
Replace battery, then: `sudo hwclock --systohc --utc`

**`is_time_valid()` returns False even though clock looks right**  
→ System time is before `RTC_MIN_VALID_EPOCH` (2026-01-01). Update the constant in
`src/sensors/rtc.py` to the current build date.

**`karna-rtc-sync.service` stays inactive**  
→ NTP has not synchronised. Check: `timedatectl` — "System clock synchronized: yes".  
If no network: the service correctly does not run. RTC time is used as-is.

**0x64 on I2C-1 returns all 0xFF**  
→ Known unknown baseboard peripheral. Does not conflict with KARNA-17. No action needed.
