"""
Traffic Analysis — Domain Model

Bounded context: anomaly detection over aggregated dashcam telemetry windows.

Value Objects:
- TrafficWindow: a single non-overlapping 10-second temporal window of dashcam telemetry.
- AnomalyScore:  carries the result of running the AnomalyDetectorPort on a TrafficWindow.

DDD classification: both are Value Objects — frozen, defined entirely by their attribute values,
produced by the data layer / detector, never mutated downstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# TrafficWindow — Value Object
# ---------------------------------------------------------------------------

# Upper bound on plausible dashcam-recorded road speed.
_MAX_SPEED_KMH: float = 300.0


@dataclass(frozen=True)
class TrafficWindow:
    """
    Value Object: a 10-second aggregated window of dashcam traffic telemetry.

    Ubiquitous Language:
    - video_id:            identifier of the source dashcam video.
    - window_start:        floor timestamp of the 10-second bucket (from DuckDB time_bucket).
    - avg_speed_kmh:       mean speed across all frames in the window.
    - avg_delta_speed:     mean absolute speed change between consecutive frames — braking signal.
    - avg_total_vehicles:  mean vehicle count per frame — traffic density signal.
    - frame_count:         number of frames that contributed to this window.

    Invariants enforced at construction time:
    - video_id must not be blank or whitespace-only.
    - avg_speed_kmh must be in [0, 300] km/h (physical bounds for road vehicles).
    - avg_delta_speed must be >= 0 (it is an absolute speed variation, never negative).
    - avg_total_vehicles must be >= 0 (a count cannot be negative).
    - frame_count must be >= 1 (a window with no frames has no meaning).
    - window_start must be timezone-aware (naive datetimes are ambiguous across timezones).

    Immutability invariant: frozen=True — computed by dbt, never mutated in the domain.
    """

    video_id: str
    window_start: datetime
    avg_speed_kmh: float
    avg_delta_speed: float
    avg_total_vehicles: float
    frame_count: int

    def __post_init__(self) -> None:
        if not self.video_id or not self.video_id.strip():
            raise ValueError(
                "video_id must not be blank or whitespace-only; "
                f"got: {self.video_id!r}"
            )

        if self.window_start.tzinfo is None:
            raise ValueError(
                "window_start must be a timezone-aware datetime to avoid ambiguity "
                "in dashcam data recorded across timezones or DST boundaries; "
                f"got naive datetime: {self.window_start!r}"
            )

        if self.avg_speed_kmh < 0:
            raise ValueError(
                f"avg_speed_kmh must be >= 0 (physical speed cannot be negative); "
                f"got: {self.avg_speed_kmh}"
            )
        if self.avg_speed_kmh > _MAX_SPEED_KMH:
            raise ValueError(
                f"avg_speed_kmh must be <= {_MAX_SPEED_KMH} km/h (implausible for road "
                f"vehicles — possible unit confusion or sensor error); "
                f"got: {self.avg_speed_kmh}"
            )

        if self.avg_delta_speed < 0:
            raise ValueError(
                f"avg_delta_speed must be >= 0 (it is the mean *absolute* speed change "
                f"between consecutive frames and cannot be negative); "
                f"got: {self.avg_delta_speed}"
            )

        if self.avg_total_vehicles < 0:
            raise ValueError(
                f"avg_total_vehicles must be >= 0 (vehicle count cannot be negative); "
                f"got: {self.avg_total_vehicles}"
            )

        if self.frame_count < 1:
            raise ValueError(
                f"frame_count must be >= 1 (a window with no frames carries no "
                f"telemetry and is meaningless); "
                f"got: {self.frame_count}"
            )


# ---------------------------------------------------------------------------
# AnomalyScore — Value Object
# ---------------------------------------------------------------------------

# Domain threshold: scores below this value classify a window as anomalous.
ANOMALY_THRESHOLD: float = -0.1

# Upper bound on a valid contamination parameter (exclusive of 0, inclusive of 0.5).
_MAX_CONTAMINATION: float = 0.5


@dataclass(frozen=True)
class AnomalyScore:
    """
    Value Object: result of anomaly detection on a single TrafficWindow.

    `is_anomaly` is derived automatically from `anomaly_score` using ANOMALY_THRESHOLD.
    Callers must NOT supply `is_anomaly` — it is computed at construction time.

    Usage:
        score = AnomalyScore(
            video_id="trip_001",
            window_start=datetime(..., tzinfo=timezone.utc),
            anomaly_score=-0.35,
            contamination=0.05,
        )
        assert score.is_anomaly is True   # derived: -0.35 < -0.1
    """

    video_id: str
    window_start: datetime
    anomaly_score: float       # Raw IF score — negative = more anomalous
    contamination: float       # Contamination parameter used by the detector
    is_anomaly: bool = field(init=False)  # Derived — not supplied by caller

    def __post_init__(self) -> None:
        if not self.video_id or not self.video_id.strip():
            raise ValueError(
                "video_id must not be blank or whitespace-only; "
                f"got: {self.video_id!r}"
            )

        if self.window_start.tzinfo is None:
            raise ValueError(
                "window_start must be a timezone-aware datetime to avoid ambiguity "
                "in dashcam data recorded across timezones or DST boundaries; "
                f"got naive datetime: {self.window_start!r}"
            )

        if self.contamination <= 0 or self.contamination > _MAX_CONTAMINATION:
            raise ValueError(
                f"contamination must be in (0, {_MAX_CONTAMINATION}] "
                f"(valid range for IsolationForest); "
                f"got: {self.contamination}"
            )

        object.__setattr__(self, "is_anomaly", self.anomaly_score < ANOMALY_THRESHOLD)
