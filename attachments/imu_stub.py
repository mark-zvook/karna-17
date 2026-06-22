# Stub: IMU / IMUService class skeleton (pattern for I2C-1 sensor)
# Full source: src/sensors/imu.py

import logging
from typing import Optional

log = logging.getLogger(__name__)

class IMUReading:
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    temperature: float

class IMU:
    """Low-level MPU-6500 access on I2C-1 @ 0x68."""
    def __init__(self, bus: int = 1, address: int = 0x68): ...
    def read(self) -> IMUReading: ...
    def calibrate(self) -> None: ...
    def close(self) -> None: ...

class IMUService:
    """Background thread that reads IMU and publishes to queue."""
    def __init__(self, imu: IMU, sample_rate_hz: int = 1000): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_latest(self) -> Optional[IMUReading]: ...
