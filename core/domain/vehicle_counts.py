from dataclasses import dataclass

@dataclass(frozen=True)
class FrameVehicleCounts:
    """Value object representing the number of detected vehicles in a specific frame."""
    frame_filename: str
    car_count: int
    motorcycle_count: int
