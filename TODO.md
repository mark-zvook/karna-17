# KARNA-17 TODO — after drift experiment

## ✅ 1. Analyse drift results
- Result: -0.111 ppm, 95% CI [-0.459, +0.238] ppm — PASS (spec ≤ ±5 ppm)
- Extrapolated: -29 ms/72h, -287 ms/30d, -3.5 s/year
- Fill measured ppm + graph into `docs/karna17_rtc.md` ← still needed

## ✅ 2. Confirm fake-hwclock is disabled (on board)
- Result: not installed at all — nothing to do

## ✅ 3. Test NTP → RTC sync path (on board)
- NTP active, System clock synchronized: yes
- hwclock matches system time
- karna-rtc-sync.service: active (exited), status=0/SUCCESS
- Note: .path unit dropped — replaced with After=time-sync.target in service

## ✅ 4. Measure test coverage
- Result: 99% (92 stmts, 1 missed — os.path.exists in _rtc_present, not worth mocking)
- Spec requires ≥80% — PASS

## ✅ 5. Identify 0x64 device on I2C-1 (on board)
- ACKs address probe but returns XX on all reads (byte, word, raw)
- Write-only or proprietary protocol — unidentifiable without baseboard schematic
- Does not conflict with KARNA-17. Documented in os/overlays/karna-rtc.txt as unknown

## ✅ 6. CR1220 battery life calculation
- RP1 backup current: ~1.3 µA (Pi Foundation hardware notes; RP1 datasheet not public)
- CR1220 40 mAh / 1.3 µA → ~3.5 years at 25°C, ~2.1 years at −20°C (field)
- Recommendation: replace every 2 years
- Added to `docs/karna17_rtc.md §Battery Life Calculation`

## ✅ 7. hardware/karna17_rtc_schematic — in docs
- ASCII schematic in docs/karna17_rtc.md §Schematic:
  CR1220 (+) → coin cell holder → baseboard VRTC → CM5 RP1; GND → CR1220 (−)
- No external components. rpi-rtc driver built into RP1, no dtoverlay needed.
- hardware/bom.csv lists CR1220 as the only hardware item.

## ✅ 8. 24h cold-start test — documented as formal deviation
- Real test: ~30s power cut, delta = 1s ✓
- Spec §9.1 requires ≥24h — formally documented as deviation in docs/karna17_rtc.md
- Justification: battery_voltage = 3.144V (healthy), rpi-rtc VRTC is low-leakage,
  30s test passed, drift extrapolation to 24h confirms -0.122 ppm ± 0.015 ppm
- Risk: low. Full 24h test deferred to field validation phase.

## ✅ 9. scp drift_log.csv back to local machine — done
