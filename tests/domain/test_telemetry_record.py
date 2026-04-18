"""
Domain tests: TelemetryRecord and VideoMetadata business rules.
Names reflect the domain language, not the implementation.
"""
import pytest
from pydantic import ValidationError

from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata


class TestTelemetryRecord:

    def test_record_captures_all_telemetry_fields(self):
        record = TelemetryRecord(
            timestamp="2026-01-14T18:13:32",
            speed_kmh=45,
            latitude=9.2985,
            longitude=-75.3856,
            raw_text="045KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32",
        )
        assert record.speed_kmh == 45
        assert record.latitude == pytest.approx(9.2985)

    def test_record_without_gps_has_zero_speed_and_no_position(self):
        record = TelemetryRecord(raw_text="unreadable ocr text")
        assert record.speed_kmh == 0
        assert record.timestamp is None
        assert record.latitude is None
        assert record.frame_filename is None

    def test_speed_below_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryRecord(raw_text="text", speed_kmh=-1)

    def test_southern_hemisphere_position_stores_negative_latitude(self):
        record = TelemetryRecord(raw_text="text", latitude=-4.5)
        assert record.latitude == pytest.approx(-4.5)

    def test_western_hemisphere_position_stores_negative_longitude(self):
        record = TelemetryRecord(raw_text="text", longitude=-75.3)
        assert record.longitude == pytest.approx(-75.3)


class TestVideoMetadata:

    def test_video_at_given_path_is_valid(self):
        meta = VideoMetadata(path="/videos/trip.mp4", sample_interval=1.0)
        assert meta.path == "/videos/trip.mp4"

    def test_default_sampling_rate_is_one_second(self):
        meta = VideoMetadata(path="/videos/trip.mp4")
        assert meta.sample_interval == 1.0

    def test_zero_sampling_interval_is_rejected(self):
        with pytest.raises(ValidationError):
            VideoMetadata(path="/videos/trip.mp4", sample_interval=0)

    def test_negative_sampling_interval_is_rejected(self):
        with pytest.raises(ValidationError):
            VideoMetadata(path="/videos/trip.mp4", sample_interval=-1.0)

    def test_video_metadata_is_immutable_after_creation(self):
        meta = VideoMetadata(path="/videos/trip.mp4")
        with pytest.raises((ValidationError, TypeError)):
            meta.path = "/other/path"
