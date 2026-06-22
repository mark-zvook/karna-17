# Excerpt from src/telemetry.py lines 20-110
# Context: log format with absolute timestamp, LOGS_FOLDER usage

import logging
import datetime

# Line 36 — log format (uses systemd clock → must be correct for post-mission correlation)
LOG_FORMAT = "[%(asctime)s.%(msecs)03d][%(levelname)s][F:%(frame_id)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# All per-frame logs carry frame_id for shot correlation
# extra={"frame_id": frame_id}  ← mandatory convention

# LOGS_FOLDER — same as sa_config.py:123, repeated here for context
LOGS_FOLDER = "telemetry/session_" + datetime.datetime.now().strftime("%d%m%Y-%H_%M")

class TelemetryLogger:
    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        self._log = logging.getLogger("telemetry")

    def log_frame(self, frame_id: int, capture_time: float, data: dict):
        # capture_time is time.time() at frame capture — needs correct system clock
        self._log.info(
            "frame data",
            extra={"frame_id": frame_id},
        )

    def log_shot(self, frame_id: int, shot_time: float):
        # shot_time absolute timestamp — correlated with video by post-mission (KARNA-19)
        self._log.info(
            "SHOT detected at %.3f", shot_time,
            extra={"frame_id": frame_id},
        )
