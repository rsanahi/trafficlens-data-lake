from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata
from core.domain.ports import VideoReaderPort, TelemetryRepositoryPort


class ExtractTelemetryUseCase:
    """
    Application Use Case: orchestrates video reading and telemetry persistence.
    Has no direct dependency on infrastructure implementations.
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
