from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, field_validator


class TelemetryRecord(BaseModel):
    """Domain Entity: a single telemetry sample extracted from a dashcam frame."""

    timestamp: Optional[str] = None
    speed_kmh: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw_text: str
    frame_filename: Optional[str] = None

    @field_validator("speed_kmh")
    @classmethod
    def speed_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("speed_kmh must be >= 0")
        return v
