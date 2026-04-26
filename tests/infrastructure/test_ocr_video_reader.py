"""
Infrastructure tests: OcrVideoReader caption parsing business rules.
Tests run against the parsing logic only — no real video, no OpenCV I/O.
"""
import pytest
from core.telemetry.adapters.ocr_video_reader import OcrVideoReader


@pytest.fixture()
def reader():
    return OcrVideoReader()


class TestOcrVideoReaderParseText:

    def test_full_viofo_caption_is_parsed_into_telemetry_record(self, reader):
        text = "045KM/H N:9.2985 W:75.3856 VIOFO A229 28-01-2026 18:13:32"
        record = reader._parse_text(text, frame_filename="frame_000001.jpg")
        assert record is not None
        assert record.speed_kmh == 45
        assert record.latitude == pytest.approx(9.2985)
        assert record.longitude == pytest.approx(-75.3856)
        assert record.timestamp == "2026-01-28T18:13:32"

    def test_frame_with_no_telemetry_data_produces_no_record(self, reader):
        record = reader._parse_text("some random noise text", "")
        assert record is None

    def test_southern_hemisphere_latitude_is_stored_as_negative(self, reader):
        text = "000KM/H S:4.5000 W:75.0000 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.latitude == pytest.approx(-4.5)

    def test_eastern_hemisphere_longitude_is_stored_as_positive(self, reader):
        text = "000KM/H N:9.0000 E:75.0000 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.longitude == pytest.approx(75.0)

    def test_stationary_vehicle_at_zero_speed_is_recorded(self, reader):
        text = "000KM/H N:9.2985 W:75.3856 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.speed_kmh == 0

    def test_yyyy_mm_dd_date_format_is_accepted(self, reader):
        text = "010KM/H N:9.2985 W:75.3856 2026/01/14 18:13:32"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.timestamp == "2026-01-14T18:13:32"

    def test_extracted_frame_filename_is_linked_to_telemetry_record(self, reader):
        text = "010KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32"
        record = reader._parse_text(text, "frame_000042.jpg")
        assert record is not None
        assert record.frame_filename == "frame_000042.jpg"
