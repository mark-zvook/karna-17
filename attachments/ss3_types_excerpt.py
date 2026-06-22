# Excerpt from src/ss3_types.py — frozen dataclass convention
# Follow this style for RtcStatus

from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class FrameTrackState:
    frame_id: int
    capture_time: float          # time.time() — must be correct absolute time (KARNA-17)
    target_bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    is_locked: bool

@dataclass(frozen=True)
class ShotEvent:
    frame_id: int
    shot_time: float             # absolute timestamp — correlated in post-mission (KARNA-19)
    recoil_magnitude: float
