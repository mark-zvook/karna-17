# Excerpt from src/sa_config.py lines 120-180
# Context: LOGS_FOLDER collision + I2C constants pattern

# --- CRITICAL: session name collision source (line 123) ---
import datetime
LOGS_FOLDER = "telemetry/session_" + datetime.datetime.now().strftime("%d%m%Y-%H_%M")
# ^^^ At invalid/missing time, two sessions launched <1 min apart get IDENTICAL names → overwrite.

# --- I2C constants pattern to follow for RTC ---
# Battery monitor (INA219 @ 0x40)
BATTERY_I2C_BUS      = 1
BATTERY_I2C_ADDRESS  = 0x40
BATTERY_VOLTAGE_WARN = 3.5   # V
BATTERY_VOLTAGE_CRIT = 3.2   # V

# IMU (MPU-6500 @ 0x68)
IMU_I2C_BUS          = 1
IMU_I2C_ADDRESS      = 0x68
IMU_SAMPLE_RATE_HZ   = 1000

# --- TODO: add RTC block here (KARNA-17) ---
# real-time clock (RV-3028-C7 over I2C-1)
RTC_I2C_BUS          = 1
RTC_I2C_ADDRESS      = 0x52          # RV-3028; PCF85063A = 0x51; DS3231 = 0x68 (COLLISION!)
RTC_MIN_VALID_EPOCH  = 1767225600    # 2026-01-01 00:00:00 UTC — update per firmware release
RTC_DRIFT_WARN_S     = 5.0           # |system - rtc| warning threshold (UI)
