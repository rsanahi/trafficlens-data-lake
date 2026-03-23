"""
Infrastructure tests: OcrVideoReader._parse_text behaviour.
These tests punch into the parsing logic without real video/OpenCV/Tesseract calls.
"""
import pytest
from core.domain.telemetry_record import TelemetryRecord
from core.infrastructure.ocr_video_reader import OcrVideoReader


@pytest.fixture()
def reader():
    return OcrVideoReader()


class TestOcrVideoReaderParseText:

    def test_parses_full_viofo_caption(self, reader):
        text = "045KM/H N:9.2985 W:75.3856 VIOFO A229 28-01-2026 18:13:32"
        record = reader._parse_text(text, frame_filename="frame_000001.jpg")
        assert record is not None
        assert record.speed_kmh == 45
        assert record.latitude == pytest.approx(9.2985)
        assert record.longitude == pytest.approx(-75.3856)
        assert record.timestamp == "2026-01-28T18:13:32"

    def test_returns_none_when_no_useful_data(self, reader):
        record = reader._parse_text("some random noise text", "")
        assert record is None

    def test_southern_hemisphere_latitude_is_negative(self, reader):
        text = "000KM/H S:4.5000 W:75.0000 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.latitude == pytest.approx(-4.5)

    def test_eastern_hemisphere_longitude_is_positive(self, reader):
        text = "000KM/H N:9.0000 E:75.0000 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.longitude == pytest.approx(75.0)

    def test_zero_speed_is_accepted(self, reader):
        text = "000KM/H N:9.2985 W:75.3856 01-01-2026 10:00:00"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.speed_kmh == 0

    def test_date_ymd_format_is_parsed(self, reader):
        text = "010KM/H N:9.2985 W:75.3856 2026/01/14 18:13:32"
        record = reader._parse_text(text, "")
        assert record is not None
        assert record.timestamp == "2026-01-14T18:13:32"

    def test_frame_filename_is_stored(self, reader):
        text = "010KM/H N:9.2985 W:75.3856 14-01-2026 18:13:32"
        record = reader._parse_text(text, "frame_000042.jpg")
        assert record is not None
        assert record.frame_filename == "frame_000042.jpg"
