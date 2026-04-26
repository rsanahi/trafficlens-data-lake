"""
Telemetry Ingestion — Domain Ports

Bounded context: dashcam video reading and telemetry persistence.

These ports define the outbound interfaces that the Telemetry Ingestion bounded
context requires from the infrastructure layer. No infrastructure details leak
through these abstractions.

Ubiquitous Language:
- VideoMetadata:  descriptor of a dashcam video file and how to sample it.
- TelemetryRecord: a single timestamped telemetry sample extracted from a frame.
- VideoReaderPort: reads TelemetryRecords from a video source.
- TelemetryRepositoryPort: persists and checks existence of telemetry extractions.
"""
from abc import ABC, abstractmethod

from core.telemetry.domain.model import TelemetryRecord, VideoMetadata


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
