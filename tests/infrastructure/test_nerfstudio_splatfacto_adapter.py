"""
RED Phase — NerfstudioSplatfactoAdapter Tests

Strategy: Nerfstudio runs as a subprocess — we DON'T test the subprocess call itself.
Instead we test the adapter's critical owned responsibilities:
  1. PLY header parsing: count Gaussians from Nerfstudio's output .ply file.
  2. PSNR parsing: extract training quality metric from ns-train stdout.
  3. Bounding box computation: derived from CameraPose translation vectors.
  4. PSNR → reprojection proxy: converts Nerfstudio metric to domain metric.
  5. SplatScene construction: adapter must produce a valid domain entity.
  6. Error handling: adapter raises meaningfully when training fails.
"""
import math
import pytest

from core.spatial_reconstruction.domain.model import CameraPose
from core.spatial_reconstruction.adapters.nerfstudio_splatfacto_adapter import (
    NerfstudioSplatfactoAdapter,
    NerfstudioTrainingError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_pose(i: int, tx: float = 0.0) -> CameraPose:
    return CameraPose(
        frame_id=f"trip_001_frame_{i:04d}",
        translation=[tx, float(i * 0.1), 0.0],
        quaternion=[1.0, 0.0, 0.0, 0.0],
    )


# ---------------------------------------------------------------------------
# PLY Header Parser Tests (unit — pure string parsing)
# ---------------------------------------------------------------------------

PLY_HEADER_VALID = b"""\
ply
format binary_little_endian 1.0
element vertex 185432
property float x
property float y
property float z
end_header
"""

PLY_HEADER_ZERO = b"""\
ply
format binary_little_endian 1.0
element vertex 0
property float x
end_header
"""

PLY_HEADER_NO_VERTEX = b"""\
ply
format binary_little_endian 1.0
element face 1000
property list uchar int vertex_indices
end_header
"""


class TestPlyHeaderParser:
    def test_counts_gaussians_from_valid_ply_header(self):
        """Parser must extract the vertex count (= Gaussian count) from PLY header."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        count = adapter._count_gaussians_from_ply_header(PLY_HEADER_VALID)
        assert count == 185_432

    def test_ply_with_zero_vertices_returns_zero(self):
        """A PLY with 0 vertices indicates a convergence failure — must return 0."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        count = adapter._count_gaussians_from_ply_header(PLY_HEADER_ZERO)
        assert count == 0

    def test_ply_without_vertex_element_returns_zero(self):
        """A PLY with no 'element vertex' line must safely return 0."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        count = adapter._count_gaussians_from_ply_header(PLY_HEADER_NO_VERTEX)
        assert count == 0


# ---------------------------------------------------------------------------
# PSNR Parser Tests (unit — pure string parsing)
# ---------------------------------------------------------------------------

STDOUT_WITH_PSNR = """\
[step 29900] Train PSNR: 26.4312
[step 29950] Eval PSNR: 27.1823
[step 30000] Eval PSNR: 27.5601
Training complete.
"""

STDOUT_NO_PSNR = """\
Loading dataset...
Building model...
Training diverged.
"""

STDOUT_PARTIAL_PSNR = """\
[step 10000] Train PSNR: 18.2
[step 20000] Train PSNR: 22.8
"""


class TestPsnrParser:
    def test_extracts_final_eval_psnr_from_stdout(self):
        """Parser must return the LAST Eval PSNR reported (final checkpoint quality)."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        psnr = adapter._parse_final_psnr(STDOUT_WITH_PSNR)
        assert psnr == pytest.approx(27.5601)

    def test_falls_back_to_train_psnr_when_eval_absent(self):
        """If no Eval PSNR exists, fall back to the last Train PSNR."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        psnr = adapter._parse_final_psnr(STDOUT_PARTIAL_PSNR)
        assert psnr == pytest.approx(22.8)

    def test_returns_none_when_no_psnr_found(self):
        """If stdout contains no PSNR entries, the parser must return None gracefully."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        psnr = adapter._parse_final_psnr(STDOUT_NO_PSNR)
        assert psnr is None


# ---------------------------------------------------------------------------
# PSNR → Reprojection Proxy Tests (unit — pure math)
# ---------------------------------------------------------------------------

class TestPsnrToReprojectionProxy:
    """
    3DGS doesn't produce a traditional reprojection error.
    We use PSNR as a proxy: higher PSNR = better reconstruction = lower proxy error.
    Mapping: PSNR 30 dB → ~0.5 px proxy | PSNR 20 dB → ~1.5 px proxy
    """

    def test_high_psnr_yields_low_reprojection_proxy(self):
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        proxy = adapter._psnr_to_reprojection_proxy(psnr=30.0)
        assert proxy <= 1.0, f"High PSNR (30dB) should give proxy <= 1.0 px, got {proxy}"

    def test_low_psnr_yields_high_reprojection_proxy(self):
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        proxy = adapter._psnr_to_reprojection_proxy(psnr=15.0)
        assert proxy > 1.5, f"Low PSNR (15dB) should give proxy > 1.5 px, got {proxy}"

    def test_none_psnr_yields_worst_case_proxy(self):
        """If PSNR couldn't be parsed, assume worst-case quality to prevent bad scenes slipping through."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        proxy = adapter._psnr_to_reprojection_proxy(psnr=None)
        assert proxy >= 2.0, "Unknown PSNR should map to a worst-case proxy >= 2.0 px"


# ---------------------------------------------------------------------------
# Bounding Box Tests (unit — pure math from poses)
# ---------------------------------------------------------------------------

class TestBoundingBoxComputation:
    def test_bounding_box_spans_full_extent_of_poses(self):
        """Bounding box must enclose ALL camera translations."""
        poses = [
            CameraPose(frame_id="f1", translation=[-1.0, 0.0, 0.0], quaternion=[1.0, 0.0, 0.0, 0.0]),
            CameraPose(frame_id="f2", translation=[5.0, 3.0, -2.0], quaternion=[1.0, 0.0, 0.0, 0.0]),
            CameraPose(frame_id="f3", translation=[2.0, -1.0, 4.0], quaternion=[1.0, 0.0, 0.0, 0.0]),
        ]
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        bbox = adapter._compute_bounding_box(poses)

        # bbox = {"min": [x,y,z], "max": [x,y,z]}
        assert bbox["min"][0] == pytest.approx(-1.0)
        assert bbox["max"][0] == pytest.approx(5.0)
        assert bbox["min"][1] == pytest.approx(-1.0)
        assert bbox["max"][1] == pytest.approx(3.0)

    def test_single_pose_bounding_box_is_a_point(self):
        """A single camera pose produces a degenerate bounding box (min == max)."""
        poses = [
            CameraPose(frame_id="f1", translation=[1.0, 2.0, 3.0], quaternion=[1.0, 0.0, 0.0, 0.0]),
        ]
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        bbox = adapter._compute_bounding_box(poses)
        assert bbox["min"] == pytest.approx([1.0, 2.0, 3.0])
        assert bbox["max"] == pytest.approx([1.0, 2.0, 3.0])


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

class TestNerfstudioAdapterErrors:
    def test_nerfstudio_training_error_is_descriptive(self):
        err = NerfstudioTrainingError("ns-train failed with exit code 1: OOM on MPS device")
        assert "exit code 1" in str(err)

    def test_train_raises_value_error_on_empty_poses(self):
        """The adapter must reject empty pose lists before launching ns-train."""
        adapter = NerfstudioSplatfactoAdapter(output_dir="/tmp/fake")
        with pytest.raises(ValueError, match="camera_poses"):
            adapter.train(camera_poses=[], scene_id="scene_empty")


# ---------------------------------------------------------------------------
# Integration Tests (require Nerfstudio + GPU/MPS — skipped in CI)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestNerfstudioAdapterIntegration:
    def test_full_training_produces_splat_scene(self, tmp_path):
        pytest.skip("Requires Nerfstudio installed, COLMAP workspace, and MPS device.")
