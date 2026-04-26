"""
Application Layer — ExtractTelemetryUseCase

Bounded context: Telemetry Ingestion.

Orchestrates video reading and telemetry persistence.
This use case is a pure orchestrator — it delegates entirely to its ports
and contains no domain logic.

Clean Architecture constraints:
- ZERO infrastructure imports. No OpenCV, no Tesseract, no CSV libraries.
- All behaviour is injected via ports at construction time.
"""
from core.telemetry.domain.model import VideoMetadata
from core.telemetry.domain.ports.i_telemetry_ports import VideoReaderPort, TelemetryRepositoryPort


class ExtractTelemetryUseCase:
    """
    Application Use Case: orchestrates video reading and telemetry persistence.

    Bounded context: Telemetry Ingestion.

    This use case is a pure orchestrator — it delegates entirely to its ports
    and contains no domain logic. It never inspects or constructs TelemetryRecord
    objects directly; that responsibility belongs to VideoReaderPort implementations.

    Clean Architecture constraints:
    - ZERO infrastructure imports. No OpenCV, no Tesseract, no CSV libraries.
    - All behaviour is injected via ports at construction time.
    """

    def __init__(
        self,
        reader: VideoReaderPort,
        repository: TelemetryRepositoryPort,
    ) -> None:
        self._reader = reader
        self._repository = repository

    def execute(self, metadata: VideoMetadata, output_path: str) -> None:
        if self._repository.exists(output_path):
            return

        records = self._reader.read_records(metadata)

        if not records:
            return

        self._repository.save(records, output_path)
