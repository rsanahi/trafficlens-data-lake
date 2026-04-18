"""
Application tests: ExtractTelemetryUseCase business rules.
Uses in-memory fakes — no real files, no OpenCV, no Tesseract.
"""
import pytest

from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata
from core.domain.ports import VideoReaderPort, TelemetryRepositoryPort
from core.application.extract_telemetry import ExtractTelemetryUseCase


# --- In-memory fakes (no infrastructure) ---

class FakeVideoReader(VideoReaderPort):
    def __init__(self, records: list):
        self._records = records

    def read_records(self, metadata: VideoMetadata) -> list[TelemetryRecord]:
        return self._records


class FakeTelemetryRepository(TelemetryRepositoryPort):
    def __init__(self, already_processed: bool = False):
        self._already_processed = already_processed
        self.saved_records: list | None = None
        self.saved_path: str | None = None

    def save(self, records: list[TelemetryRecord], path: str) -> None:
        self.saved_records = records
        self.saved_path = path

    def exists(self, path: str) -> bool:
        return self._already_processed


# --- Use Case tests ---

class TestExtractTelemetryUseCase:

    def _a_trip(self) -> list[TelemetryRecord]:
        return [
            TelemetryRecord(
                timestamp="2026-01-14T18:13:32",
                speed_kmh=45,
                latitude=9.2985,
                longitude=-75.3856,
                raw_text="045KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32",
            )
        ]

    def test_telemetry_is_persisted_after_successful_extraction(self):
        reader = FakeVideoReader(self._a_trip())
        repo = FakeTelemetryRepository(already_processed=False)

        ExtractTelemetryUseCase(reader=reader, repository=repo).execute(
            metadata=VideoMetadata(path="/videos/trip.mp4"),
            output_path="/out/trip.csv",
        )

        assert repo.saved_records is not None
        assert len(repo.saved_records) == 1
        assert repo.saved_path == "/out/trip.csv"

    def test_already_processed_video_is_not_extracted_again(self):
        reader = FakeVideoReader(self._a_trip())
        repo = FakeTelemetryRepository(already_processed=True)

        ExtractTelemetryUseCase(reader=reader, repository=repo).execute(
            metadata=VideoMetadata(path="/videos/trip.mp4"),
            output_path="/out/trip.csv",
        )

        assert repo.saved_records is None  # save() was never called

    def test_video_with_no_readable_frames_produces_no_output(self):
        reader = FakeVideoReader([])  # nothing extracted
        repo = FakeTelemetryRepository(already_processed=False)

        ExtractTelemetryUseCase(reader=reader, repository=repo).execute(
            metadata=VideoMetadata(path="/videos/empty.mp4"),
            output_path="/out/empty.csv",
        )

        assert repo.saved_records is None  # nothing to persist
