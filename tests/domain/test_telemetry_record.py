"""
🔴 RED: Tests for domain entities and use case.
These tests MUST fail until production code is implemented.
"""
import pytest
from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata


class TestTelemetryRecord:

    def test_valid_record_with_all_fields(self):
        record = TelemetryRecord(
            timestamp="2026-01-14T18:13:32",
            speed_kmh=45,
            latitude=9.2985,
            longitude=-75.3856,
            raw_text="045KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32",
        )
        assert record.speed_kmh == 45
        assert record.latitude == pytest.approx(9.2985)

    def test_defaults_are_applied(self):
        record = TelemetryRecord(raw_text="some ocr text")
        assert record.speed_kmh == 0
        assert record.timestamp is None
        assert record.latitude is None
        assert record.frame_filename is None

    def test_negative_speed_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TelemetryRecord(raw_text="text", speed_kmh=-1)

    def test_southern_latitude_is_negative(self):
        record = TelemetryRecord(raw_text="text", latitude=-4.5)
        assert record.latitude == pytest.approx(-4.5)

    def test_western_longitude_is_negative(self):
        record = TelemetryRecord(raw_text="text", longitude=-75.3)
        assert record.longitude == pytest.approx(-75.3)


class TestVideoMetadata:

    def test_valid_metadata(self):
        meta = VideoMetadata(path="/videos/trip.mp4", sample_interval=1.0)
        assert meta.path == "/videos/trip.mp4"

    def test_defaults_sample_interval(self):
        meta = VideoMetadata(path="/videos/trip.mp4")
        assert meta.sample_interval == 1.0

    def test_zero_interval_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VideoMetadata(path="/videos/trip.mp4", sample_interval=0)

    def test_negative_interval_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VideoMetadata(path="/videos/trip.mp4", sample_interval=-1.0)

    def test_is_immutable(self):
        from pydantic import ValidationError
        meta = VideoMetadata(path="/videos/trip.mp4")
        with pytest.raises((ValidationError, TypeError)):
            meta.path = "/other/path"
