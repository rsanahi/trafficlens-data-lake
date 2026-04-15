"""
RED Phase — ColmapSfMAdapter Tests

Strategy: COLMAP runs as a subprocess — we DON'T test the subprocess call itself.
Instead we test the two critical responsibilities the adapter owns:
  1. Quaternion normalization: adapter must produce |q|=1 before constructing CameraPose.
  2. images.txt parsing: adapter must correctly read COLMAP's sparse reconstruction output.
  3. Error handling: adapter must raise descriptive errors if COLMAP fails or produces no poses.

Tests are split into unit (pure functions) and integration (requires COLMAP binary, skipped by default).
"""
import math
import pytest

from core.infrastructure.colmap_sfm_adapter import ColmapSfMAdapter, ColmapReconstructionError


# ---------------------------------------------------------------------------
# Quaternion Normalization Tests (unit — pure math, no COLMAP needed)
# ---------------------------------------------------------------------------

class TestQuaternionNormalization:
    """
    The adapter must normalize COLMAP's raw floats before constructing CameraPose.
    These are pure unit tests over a helper function — no subprocess, no files.
    """

    def test_already_unit_quaternion_is_unchanged(self):
        """A perfect unit quaternion must pass through normalization without change."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        q = [1.0, 0.0, 0.0, 0.0]
        result = adapter._normalize_quaternion(q)
        norm = math.sqrt(sum(c ** 2 for c in result))
        assert abs(norm - 1.0) < 1e-6

    def test_non_unit_quaternion_is_normalized_to_unit(self):
        """A raw COLMAP float with |q| != 1 must be normalized to unit length."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        q = [2.0, 0.0, 0.0, 0.0]  # |q| = 2.0
        result = adapter._normalize_quaternion(q)
        norm = math.sqrt(sum(c ** 2 for c in result))
        assert abs(norm - 1.0) < 1e-6
        assert result[0] == pytest.approx(1.0)

    def test_arbitrary_quaternion_is_normalized(self):
        """Verify normalization works for a general non-trivial rotation quaternion."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        # Unnormalized rotation, typical of COLMAP float precision issues
        q = [0.695, 0.718, -0.011, 0.025]
        result = adapter._normalize_quaternion(q)
        norm = math.sqrt(sum(c ** 2 for c in result))
        assert abs(norm - 1.0) < 1e-6

    def test_zero_quaternion_raises_value_error(self):
        """A zero quaternion cannot be normalized — must fail before reaching CameraPose."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        with pytest.raises(ValueError, match="zero quaternion"):
            adapter._normalize_quaternion([0.0, 0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# images.txt Parser Tests (unit — pure string parsing, no COLMAP needed)
# ---------------------------------------------------------------------------

SAMPLE_IMAGES_TXT = """\
# Image list with two lines of data per image:
#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
#   POINTS2D[] as (X, Y, POINT3D_ID)
1 0.695104 0.718385 -0.010566 0.024957 1.396693 -0.251668 0.814782 1 frame_0001.jpg
427.0 312.0 -1
2 0.999900 0.010000 0.005000 0.008000 2.500000 0.000000 -1.200000 1 frame_0002.jpg
110.0 200.0 4
"""

EMPTY_IMAGES_TXT = """\
# Image list with two lines of data per image:
#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
"""


class TestImagesParser:
    """
    Tests for the COLMAP images.txt format parser.
    Verifies that frame_id, translation, and quaternion are extracted correctly.
    """

    def test_parses_correct_number_of_poses(self):
        """Parser must produce one CameraPose per registered image."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(SAMPLE_IMAGES_TXT)
        assert len(poses) == 2

    def test_parses_frame_id_from_image_name(self):
        """frame_id must be the image filename (stem), not the full path."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(SAMPLE_IMAGES_TXT)
        assert poses[0].frame_id == "frame_0001"
        assert poses[1].frame_id == "frame_0002"

    def test_parses_translation_vector_correctly(self):
        """Translation [TX, TY, TZ] from images.txt must map to CameraPose.translation."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(SAMPLE_IMAGES_TXT)
        assert poses[0].translation == pytest.approx([1.396693, -0.251668, 0.814782])

    def test_quaternion_is_normalized_after_parsing(self):
        """Parsed quaternions must be normalized to unit length before CameraPose construction."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(SAMPLE_IMAGES_TXT)
        for pose in poses:
            norm = math.sqrt(sum(c ** 2 for c in pose.quaternion))
            assert abs(norm - 1.0) < 1e-4, f"Quaternion is not unit: {pose.quaternion}"

    def test_comments_are_ignored(self):
        """Lines starting with '#' must be skipped — they are COLMAP metadata."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(SAMPLE_IMAGES_TXT)
        # Only real image lines, not comment lines
        assert all(hasattr(p, "frame_id") for p in poses)

    def test_empty_images_txt_returns_empty_list(self):
        """If COLMAP registered zero images, the parser returns an empty list (caller handles error)."""
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/fake")
        poses = adapter._parse_images_txt(EMPTY_IMAGES_TXT)
        assert poses == []


# ---------------------------------------------------------------------------
# ColmapReconstructionError Tests (unit — no subprocess)
# ---------------------------------------------------------------------------

class TestColmapAdapterErrorHandling:
    """
    Verifies adapter error behavior without actually running COLMAP.
    """

    def test_map_poses_raises_if_no_frames_provided(self):
        """
        The adapter must not call COLMAP on an empty frame list.
        (Redundant with use case check but protects against direct adapter misuse.)
        """
        adapter = ColmapSfMAdapter(workspace_dir="/tmp/colmap_test_ws")
        with pytest.raises(ValueError, match="frame_paths"):
            adapter.map_poses([])

    def test_colmap_reconstruction_error_is_descriptive(self):
        """ColmapReconstructionError must carry a meaningful message for debugging."""
        err = ColmapReconstructionError("COLMAP failed with exit code 1: feature extractor OOM")
        assert "exit code 1" in str(err)


# ---------------------------------------------------------------------------
# Integration Tests (require COLMAP binary — skipped in CI by default)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestColmapAdapterIntegration:
    """
    These tests require `colmap` to be installed and available in PATH.
    Run with: pytest -m integration
    """

    def test_map_poses_returns_camera_poses_for_real_frames(self, tmp_path):
        """
        End-to-end: given real frame images, adapter runs COLMAP and returns CameraPose objects.
        Requires: colmap binary + at least 3 overlapping JPEG frames.
        """
        pytest.skip("Requires COLMAP binary and real dashcam frames — run manually.")
