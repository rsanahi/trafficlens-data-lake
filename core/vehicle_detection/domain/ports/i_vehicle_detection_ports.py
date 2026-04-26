"""
Vehicle Detection — Domain Ports

Bounded context: per-frame vehicle detection and count persistence.

These ports define the outbound interfaces that the Vehicle Detection bounded
context requires from the infrastructure layer. The application layer depends
only on these abstractions — never on YOLO, ultralytics, or any CV library.

Ubiquitous Language:
- FrameVehicleCounts:         the result of detecting vehicles in a single dashcam frame.
- VehicleDetectorPort:        analyzes a frame image and returns per-class vehicle counts.
- VehicleCountsRepositoryPort: persists detection counts per video for dbt ingestion.
- FrameProviderPort:          resolves the ordered list of frame paths for a given video.
                               Abstracts filesystem directory scanning from the use case.
"""
from abc import ABC, abstractmethod

from core.vehicle_detection.domain.model import FrameVehicleCounts


class VehicleDetectorPort(ABC):
    """Port: analyzes a frame image and detects the vehicles present."""

    @abstractmethod
    def detect(self, frame_path: str) -> FrameVehicleCounts:
        ...


class VehicleCountsRepositoryPort(ABC):
    """Port: persists the series of frame detection counts for a video."""

    @abstractmethod
    def save(self, video_id: str, counts: list[FrameVehicleCounts]) -> None:
        ...

    @abstractmethod
    def exists(self, video_id: str) -> bool:
        ...


class FrameProviderPort(ABC):
    """
    Port: resolves the sorted list of frame image paths for a given video.

    Abstracts the filesystem concern (directory scanning, glob patterns) from
    the ExtractVehicleCountsUseCase. Without this port, the use case contains
    a direct Path/glob call — a leak of infrastructure knowledge into the
    application layer.

    Ubiquitous Language:
    - frames_dir: the Bronze Layer directory containing extracted JPEG frames.
    - Returns:    a sorted list of absolute paths to all JPEG frames in the directory.

    Invariants:
    - Must raise FileNotFoundError if frames_dir does not exist or is not a directory.
    - Must return paths in deterministic, sorted order (alphabetical by filename).
    - An empty directory returns an empty list — not an error.

    Concrete adapters: LocalJpegFrameProvider (filesystem glob).
    """

    @abstractmethod
    def get_frame_paths(self, frames_dir: str) -> list[str]:
        """
        Return a sorted list of absolute JPEG frame paths from frames_dir.

        Args:
            frames_dir: path to a Bronze Layer directory containing .jpg frames.

        Returns:
            Sorted list of absolute paths to all JPEG frames.

        Raises:
            FileNotFoundError: if frames_dir does not exist or is not a directory.
        """
        ...
