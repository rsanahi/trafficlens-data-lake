from abc import ABC, abstractmethod
from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata
from core.domain.vehicle_counts import FrameVehicleCounts


class VideoReaderPort(ABC):
    """Port: reads telemetry records from a video source."""

    @abstractmethod
    def read_records(self, metadata: VideoMetadata) -> list[TelemetryRecord]:
        ...


class TelemetryRepositoryPort(ABC):
    """Port: persists and checks telemetry records."""

    @abstractmethod
    def save(self, records: list[TelemetryRecord], path: str) -> None:
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        ...


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
