# KARNA-17 RTC — Delivery Package

**Chip:** RV-3028-C7 · **I2C addr:** 0x52 · **Accuracy:** ±1 ppm · **Linux driver:** `rtc-rv3028`

---

## What was done

1. **Chip selected:** RV-3028-C7 (addr 0x52) — no collision with MPU-6500 (0x68) or INA219 (0x40), ±1 ppm, 45 nA backup current, >10 yr battery life on CR2032.
2. **OS config:** `dtoverlay=i2c-rtc,rv3028`, `fake-hwclock` masked, `systemd-timesyncd` enabled. Applied via idempotent `os/setup_rtc.sh`.
3. **Auto NTP→RTC sync:** `karna-rtc-sync.path` watches `/run/systemd/timesync/synchronized`; on appearance runs `karna-rtc-sync.service` → `hwclock --systohc --utc`.
4. **Python adapter:** `src/sensors/rtc.py` — `RtcStatus` dataclass, `get_rtc_status()`, `is_time_valid()`, `sync_rtc_from_system()`. Reads `timedatectl` and `hwclock` only; never touches I2C chip directly.
5. **Session collision guard:** `is_time_valid()` → False triggers monotonic counter suffix (`session_INVALIDTIME_0001`) instead of `datetime.now()` in LOGS_FOLDER.
6. **Tests:** 12 test classes, mocks for timedatectl/hwclock, no hardware needed.
7. **Drift test:** ⚠️ NOT MEASURED — requires real RV-3028 hardware. `data/drift_log.csv` is a placeholder. See `docs/karna17_rtc.md` for the measurement script and acceptance criterion (≤ ±5 ppm over ≥ 72 h).

---

## Address collision solution

DS3231 = 0x68 = same as MPU-6500 → not usable without hardware rework.  
**RV-3028-C7 = 0x52** → no conflict. Verify: `i2cdetect -y 1` should show 0x40, 0x52, 0x68 simultaneously.

---

## Install

```bash
# On target CM5 (as root):
sudo bash os/setup_rtc.sh
sudo reboot

# Verify:
i2cdetect -y 1                        # expect 0x52 present
cat /sys/class/rtc/rtc0/name          # rv3028
sudo hwclock -r --utc
timedatectl
```

---

## Tests

```bash
pip install pytest
pytest tests/test_rtc.py -v
```

No hardware required — all external calls are mocked.

---

## Drift test reproduction

```bash
# Start logging (runs ~1 sample/min for 72 h):
while true; do
  echo "$(date -u +%s),$(hwclock -r --utc 2>/dev/null | awk '{print $1"T"$2}')" >> data/drift_log.csv
  sleep 60
done

# Analyse:
python3 -c "
import csv
rows = list(csv.DictReader(open('data/drift_log.csv')))
# ... compute ppm from first/last row
"
```

---

## Provision integration

Add to `tools/provision_cm5.sh`:

```bash
bash "\$KARNA_SRC/os/setup_rtc.sh"
```

---

## Files

```
hardware/bom.csv                       BOM (RV-3028, CR2032, passives)
hardware/karna17_rtc_schematic.pdf     Pinout schematic
os/overlays/karna-rtc.txt              config.txt fragment
os/systemd/karna-rtc-sync.service      hwclock --systohc unit
os/systemd/karna-rtc-sync.path         NTP sync watcher
os/setup_rtc.sh                        Idempotent setup
src/sensors/rtc.py                     Python adapter
tests/test_rtc.py                      pytest suite
docs/karna17_rtc.md                    Full documentation
data/drift_log.csv                     72 h drift measurement
attachments/                           Contractor context files
```
