"""
Telemetry Ingestion — Domain Model

Bounded context: dashcam video reading and telemetry persistence.

Aggregate Root / Value Objects:
- TelemetryRecord: a single timestamped telemetry sample extracted from a dashcam frame via OCR.
- VideoMetadata:   identifies a dashcam video and its sampling configuration.

DDD classification: both are Value Objects — defined entirely by their attribute values,
no lifecycle, no identity, never mutated after construction.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, field_validator


class TelemetryRecord(BaseModel, frozen=True):
    """
    Value Object: a single telemetry sample extracted from a dashcam frame via OCR.

    Ubiquitous Language:
    - timestamp:      ISO-8601 datetime string parsed from the VIOFO on-screen caption.
                      None if the OCR could not read a valid date/time from the frame.
    - speed_kmh:      vehicle speed in km/h as read from the dashcam display. 0 when absent.
    - latitude:       GPS latitude in decimal degrees. Negative = southern hemisphere.
                      None if GPS was unavailable or could not be parsed.
    - longitude:      GPS longitude in decimal degrees. Negative = western hemisphere.
                      None if GPS was unavailable or could not be parsed.
    - raw_text:       the raw OCR text extracted from the frame's telemetry bar.
                      Always present — used for debugging and re-parsing.
    - frame_filename: basename of the saved frame image (e.g. "frame_000120.jpg").
                      None if the frame was not saved to disk.

    Invariants:
    - speed_kmh must be >= 0 (physical speed is a non-negative magnitude).
    """

    model_config = {"frozen": True}

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


class VideoMetadata(BaseModel, frozen=True):
    """
    Value Object: identifies a dashcam video and its sampling configuration.

    Ubiquitous Language:
    - path:            filesystem path to the source dashcam video file.
                       Must be a non-blank string — a blank path has no identity
                       in the Telemetry Ingestion pipeline and cannot be read.
    - sample_interval: time between consecutive frame extractions, in seconds.
                       Controls the density of TelemetryRecord output.
                       Default: 1.0 second (one frame per second).

    Invariants:
    - path must not be blank or whitespace-only.
    - sample_interval must be strictly positive (zero or negative is physically meaningless).
    """

    path: str
    sample_interval: float = 1.0

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "path must not be blank or whitespace-only; "
                "a blank path cannot identify a dashcam video in the Telemetry Ingestion pipeline."
            )
        return v

    @field_validator("sample_interval")
    @classmethod
    def interval_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(
                f"sample_interval must be > 0 (physically meaningful sampling rate); "
                f"got: {v}"
            )
        return v
