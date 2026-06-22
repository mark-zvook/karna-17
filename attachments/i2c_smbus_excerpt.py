# Excerpt from src/battery_monitor/i2c.py + smbus.py
# Pattern for raw I2C access on bus 1 (reference only — RTC adapter does NOT use this)

import smbus2

class I2CBus:
    """Thin wrapper around smbus2 for consistent error handling."""

    def __init__(self, bus: int = 1):
        self._bus = smbus2.SMBus(bus)

    def read_word(self, address: int, register: int) -> int:
        return self._bus.read_word_data(address, register)

    def read_bytes(self, address: int, register: int, length: int) -> bytes:
        return bytes(self._bus.read_i2c_block_data(address, register, length))

    def write_byte(self, address: int, register: int, value: int) -> None:
        self._bus.write_byte_data(address, register, value)

    def close(self) -> None:
        self._bus.close()

# Usage example (INA219 @ 0x40):
# bus = I2CBus(bus=1)
# raw = bus.read_word(0x40, 0x01)  # shunt voltage register
# bus.close()
#
# NOTE: RTC adapter (src/sensors/rtc.py) does NOT use I2CBus.
# The kernel driver (rtc-rv3028) owns the chip; Python reads timedatectl/hwclock only.
