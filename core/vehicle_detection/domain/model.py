"""
Vehicle Detection — Domain Model

Bounded context: per-frame vehicle detection and count persistence.

Value Objects:
- FrameVehicleCounts: the number of vehicles detected in a single dashcam frame.

DDD classification: Value Object — defined entirely by its attribute values,
no lifecycle, no identity, never mutated after construction.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FrameVehicleCounts:
    """
    Value Object: per-frame vehicle detection counts from a single dashcam frame.

    Ubiquitous Language:
    - frame_filename:     filename of the source frame image (e.g. "frame_0001.jpg").
                          Used to trace each detection back to its source asset.
    - car_count:          number of cars detected in this frame (COCO class 2).
    - motorcycle_count:   number of motorcycles detected in this frame (COCO class 3).

    Invariants enforced at construction time:
    - frame_filename must not be blank or whitespace-only.
    - car_count must be >= 0 (a detection count cannot be negative).
    - motorcycle_count must be >= 0 (a detection count cannot be negative).

    Immutability invariant: frozen=True — produced by the detector, never mutated downstream.
    """

    frame_filename: str
    car_count: int
    motorcycle_count: int

    def __post_init__(self) -> None:
        # --- frame_filename ---
        if not self.frame_filename or not self.frame_filename.strip():
            raise ValueError(
                "frame_filename must not be blank or whitespace-only; "
                f"got: {self.frame_filename!r}"
            )

        # --- car_count ---
        if self.car_count < 0:
            raise ValueError(
                f"car_count must be >= 0 (a detection count cannot be negative); "
                f"got: {self.car_count}"
            )

        # --- motorcycle_count ---
        if self.motorcycle_count < 0:
            raise ValueError(
                f"motorcycle_count must be >= 0 (a detection count cannot be negative); "
                f"got: {self.motorcycle_count}"
            )
