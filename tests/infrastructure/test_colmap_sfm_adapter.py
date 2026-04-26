"""
RED Phase — GPS Alignment Tests for ColmapSfMAdapter

Tests for the two purely unit-testable GPS responsibilities:
  1. _lat_lon_to_local_xyz(): GPS degrees → metric ENU coordinates (pure math)
  2. _align_telemetry_to_frames(): matches TelemetryRecord to frame filename
  3. _inject_gps_priors_to_db(): writes prior_tx/ty/tz into COLMAP's SQLite (in-memory DB)

No COLMAP binary required for any of these tests.
"""
import math
import sqlite3
import pytest

from core.telemetry.domain.model import TelemetryRecord
from core.spatial_reconstruction.adapters.colmap_sfm_adapter import ColmapSfMAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_telemetry(lat: float, lon: float, filename: str) -> TelemetryRecord:
    return TelemetryRecord(
        raw_text="",
        latitude=lat,
        longitude=lon,
        frame_filename=filename,
    )


def _make_colmap_db_in_memory() -> sqlite3.Connection:
    """Create a minimal in-memory COLMAP database (images table only)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE images (
            image_id   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            camera_id  INTEGER NOT NULL DEFAULT 1,
            prior_qw   REAL,
            prior_qx   REAL,
            prior_qy   REAL,
            prior_qz   REAL,
            prior_tx   REAL,
            prior_ty   REAL,
            prior_tz   REAL
        )
    """)
    # Simulate images registered by COLMAP feature extractor
    conn.executemany(
        "INSERT INTO images (name, prior_tx, prior_ty, prior_tz) VALUES (?, NULL, NULL, NULL)",
        [("frame_0001.jpg",), ("frame_0002.jpg",), ("frame_0003.jpg",)],
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 1. GPS → Local XYZ Conversion Tests (pure math, no COLMAP)
# ---------------------------------------------------------------------------

class TestLatLonToLocalXyz:
    """
    Validates the ENU (East-North-Up) conversion from GPS degrees to metric coordinates.
    Reference: WGS84 Earth radius = 6,378,137.0 m.
    """

    def test_reference_point_maps_to_origin(self):
        """The reference point (origin) must convert to (0, 0, 0)."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        x, y, z = adapter._lat_lon_to_local_xyz(
            lat=19.4326,
            lon=-99.1332,
            lat0=19.4326,
            lon0=-99.1332,
        )
        assert x == pytest.approx(0.0, abs=1e-6)
        assert y == pytest.approx(0.0, abs=1e-6)
        assert z == pytest.approx(0.0, abs=1e-6)

    def test_moving_north_increases_y(self):
        """Moving north (increasing latitude) increases the Y (North) coordinate."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        _, y, _ = adapter._lat_lon_to_local_xyz(
            lat=19.4336,    # 0.001° north of reference
            lon=-99.1332,
            lat0=19.4326,
            lon0=-99.1332,
        )
        assert y > 0.0, "Moving north should increase Y"

    def test_moving_east_increases_x(self):
        """Moving east (increasing longitude) increases the X (East) coordinate."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        x, _, _ = adapter._lat_lon_to_local_xyz(
            lat=19.4326,
            lon=-99.1322,   # 0.001° east of reference
            lat0=19.4326,
            lon0=-99.1332,
        )
        assert x > 0.0, "Moving east should increase X"

    def test_100m_displacement_north_is_approximately_correct(self):
        """
        1 degree of latitude ≈ 111,320 meters.
        0.001° north ≈ 111.32 meters. Tolerance: ±1 m.
        """
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        _, y, _ = adapter._lat_lon_to_local_xyz(
            lat=19.4326 + (100 / 111_320),  # exactly 100 meters north
            lon=-99.1332,
            lat0=19.4326,
            lon0=-99.1332,
        )
        assert y == pytest.approx(100.0, abs=1.0)

    def test_west_displacement_gives_negative_x(self):
        """Moving west (decreasing longitude) must yield negative X."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        x, _, _ = adapter._lat_lon_to_local_xyz(
            lat=19.4326,
            lon=-99.1342,   # west of reference
            lat0=19.4326,
            lon0=-99.1332,
        )
        assert x < 0.0

    def test_z_is_always_zero_for_flat_terrain(self):
        """Dashcam drives on flat roads — Z (Up) must always be 0.0."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        _, _, z = adapter._lat_lon_to_local_xyz(
            lat=19.4330, lon=-99.1322,
            lat0=19.4326, lon0=-99.1332,
        )
        assert z == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 2. Frame-Telemetry Alignment Tests
# ---------------------------------------------------------------------------

class TestAlignTelemetryToFrames:
    """
    The adapter must correctly match frame filenames to TelemetryRecord objects.
    Mismatches (frames without GPS) must be handled gracefully.
    """

    def test_matches_frame_to_correct_telemetry(self):
        """Each frame path must be matched to its TelemetryRecord by filename."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        frame_paths = ["/data/frame_0001.jpg", "/data/frame_0002.jpg"]
        telemetry = [
            _make_telemetry(19.4326, -99.1332, "frame_0001.jpg"),
            _make_telemetry(19.4330, -99.1320, "frame_0002.jpg"),
        ]
        mapping = adapter._align_telemetry_to_frames(frame_paths, telemetry)

        assert "/data/frame_0001.jpg" in mapping
        assert mapping["/data/frame_0001.jpg"].latitude == pytest.approx(19.4326)

    def test_frames_without_matching_telemetry_are_excluded(self):
        """Frames that have no GPS entry must NOT appear in the mapping (no silent None injection)."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        frame_paths = ["/data/frame_0001.jpg", "/data/orphan_frame.jpg"]
        telemetry = [_make_telemetry(19.4326, -99.1332, "frame_0001.jpg")]

        mapping = adapter._align_telemetry_to_frames(frame_paths, telemetry)

        assert "/data/orphan_frame.jpg" not in mapping
        assert len(mapping) == 1

    def test_telemetry_with_none_gps_is_excluded(self):
        """TelemetryRecord with latitude=None or longitude=None must be excluded."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        frame_paths = ["/data/frame_nogps.jpg"]
        telemetry = [TelemetryRecord(raw_text="", frame_filename="frame_nogps.jpg")]

        mapping = adapter._align_telemetry_to_frames(frame_paths, telemetry)

        assert len(mapping) == 0


# ---------------------------------------------------------------------------
# 3. SQLite GPS Injection Tests (in-memory COLMAP DB)
# ---------------------------------------------------------------------------

class TestInjectGpsPriorsToDb:
    """
    Validates that the adapter correctly writes ENU coordinates into COLMAP's
    images table as prior_tx / prior_ty / prior_tz using plain sqlite3.
    No COLMAP binary installed required.
    """

    def test_prior_coordinates_are_written_to_db(self):
        """After injection, images must have non-NULL prior_tx/ty/tz."""
        conn = _make_colmap_db_in_memory()
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")

        gps_map = {
            "frame_0001.jpg": (10.5, 20.3, 0.0),
            "frame_0002.jpg": (11.0, 21.0, 0.0),
        }
        adapter._inject_gps_priors_to_db(conn, gps_map)

        row = conn.execute(
            "SELECT prior_tx, prior_ty, prior_tz FROM images WHERE name = 'frame_0001.jpg'"
        ).fetchone()
        assert row[0] == pytest.approx(10.5)
        assert row[1] == pytest.approx(20.3)
        assert row[2] == pytest.approx(0.0)

    def test_images_not_in_gps_map_remain_null(self):
        """Images with no GPS data must retain NULL priors — COLMAP will handle them normally."""
        conn = _make_colmap_db_in_memory()
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")

        gps_map = {"frame_0001.jpg": (5.0, 10.0, 0.0)}  # frame_0003 intentionally absent
        adapter._inject_gps_priors_to_db(conn, gps_map)

        row = conn.execute(
            "SELECT prior_tx FROM images WHERE name = 'frame_0003.jpg'"
        ).fetchone()
        assert row[0] is None

    def test_all_provided_frames_are_injected(self):
        """Every entry in the GPS map must result in a DB update."""
        conn = _make_colmap_db_in_memory()
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")

        gps_map = {
            "frame_0001.jpg": (1.0, 2.0, 0.0),
            "frame_0002.jpg": (3.0, 4.0, 0.0),
            "frame_0003.jpg": (5.0, 6.0, 0.0),
        }
        adapter._inject_gps_priors_to_db(conn, gps_map)

        count = conn.execute(
            "SELECT COUNT(*) FROM images WHERE prior_tx IS NOT NULL"
        ).fetchone()[0]
        assert count == 3
