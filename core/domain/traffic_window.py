"""
Traffic Window — Value Object

Represents a single non-overlapping 10-second temporal window of dashcam telemetry,
pre-aggregated from the fct_traffic_windows Gold Layer.

This is the primary input to the anomaly detection pipeline.

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
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Upper bound on plausible dashcam-recorded road speed.
# Values above this threshold indicate sensor error or unit confusion (mph as kmh).
_MAX_SPEED_KMH: float = 300.0


@dataclass(frozen=True)
class TrafficWindow:
    """Value Object: a 10-second aggregated window of dashcam traffic telemetry."""

    video_id: str
    window_start: datetime
    avg_speed_kmh: float
    avg_delta_speed: float
    avg_total_vehicles: float
    frame_count: int

    def __post_init__(self) -> None:
        # --- video_id ---
        if not self.video_id or not self.video_id.strip():
            raise ValueError(
                "video_id must not be blank or whitespace-only; "
                f"got: {self.video_id!r}"
            )

        # --- window_start ---
        if self.window_start.tzinfo is None:
            raise ValueError(
                "window_start must be a timezone-aware datetime to avoid ambiguity "
                "in dashcam data recorded across timezones or DST boundaries; "
                f"got naive datetime: {self.window_start!r}"
            )

        # --- avg_speed_kmh ---
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

        # --- avg_delta_speed ---
        if self.avg_delta_speed < 0:
            raise ValueError(
                f"avg_delta_speed must be >= 0 (it is the mean *absolute* speed change "
                f"between consecutive frames and cannot be negative); "
                f"got: {self.avg_delta_speed}"
            )

        # --- avg_total_vehicles ---
        if self.avg_total_vehicles < 0:
            raise ValueError(
                f"avg_total_vehicles must be >= 0 (vehicle count cannot be negative); "
                f"got: {self.avg_total_vehicles}"
            )

        # --- frame_count ---
        if self.frame_count < 1:
            raise ValueError(
                f"frame_count must be >= 1 (a window with no frames carries no "
                f"telemetry and is meaningless); "
                f"got: {self.frame_count}"
            )
