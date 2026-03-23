from abc import ABC, abstractmethod
from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata


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
