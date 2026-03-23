"""
🔴 RED: Tests for ExtractTelemetryUseCase.
Uses in-memory fakes — no real files, no OpenCV, no Tesseract.
"""
import pytest
from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata
from core.domain.ports import VideoReaderPort, TelemetryRepositoryPort
from core.application.extract_telemetry import ExtractTelemetryUseCase


# --- In-Memory Fakes (no infrastructure) ---

class FakeVideoReader(VideoReaderPort):
    def __init__(self, records: list):
        self._records = records

    def read_records(self, metadata: VideoMetadata) -> list[TelemetryRecord]:
        return self._records


class FakeTelemetryRepository(TelemetryRepositoryPort):
    def __init__(self, already_exists=False):
        self._exists = already_exists
        self.saved_records = None
        self.saved_path = None

    def save(self, records: list[TelemetryRecord], path: str) -> None:
        self.saved_records = records
        self.saved_path = path

    def exists(self, path: str) -> bool:
        return self._exists


# --- Tests ---

class TestExtractTelemetryUseCase:

    def _sample_records(self):
        return [
            TelemetryRecord(
                timestamp="2026-01-14T18:13:32",
                speed_kmh=45,
                latitude=9.2985,
                longitude=-75.3856,
                raw_text="045KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32",
            )
        ]

    def test_use_case_saves_extracted_records(self):
        reader = FakeVideoReader(self._sample_records())
        repo = FakeTelemetryRepository(already_exists=False)
        metadata = VideoMetadata(path="/videos/trip.mp4")

        use_case = ExtractTelemetryUseCase(reader=reader, repository=repo)
        use_case.execute(metadata=metadata, output_path="/out/trip.csv")

        assert repo.saved_records is not None
        assert len(repo.saved_records) == 1
        assert repo.saved_path == "/out/trip.csv"

    def test_use_case_skips_if_already_processed(self):
        reader = FakeVideoReader(self._sample_records())
        repo = FakeTelemetryRepository(already_exists=True)
        metadata = VideoMetadata(path="/videos/trip.mp4")

        use_case = ExtractTelemetryUseCase(reader=reader, repository=repo)
        use_case.execute(metadata=metadata, output_path="/out/trip.csv")

        assert repo.saved_records is None  # save was never called

    def test_use_case_does_not_save_empty_results(self):
        reader = FakeVideoReader([])  # No records extracted
        repo = FakeTelemetryRepository(already_exists=False)
        metadata = VideoMetadata(path="/videos/trip.mp4")

        use_case = ExtractTelemetryUseCase(reader=reader, repository=repo)
        use_case.execute(metadata=metadata, output_path="/out/trip.csv")

        assert repo.saved_records is None  # nothing to save
