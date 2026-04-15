"""
RED Phase — Spatial Reconstruction Domain Tests

Design decisions (non-negotiable):
- CameraPose: raises ValueError if quaternion is not normalized (|q| = 1 ± 1e-4).
- All numeric types are pure Python list[float] — no numpy, no torch in Domain.
- SplatScene: raises ValueError if reliability metrics are below contract thresholds.
- InferenceContract: validates SplatScene before allowing synthetic injection.
"""
import math
import pytest

from core.domain.spatial_reconstruction import (
    CameraPose,
    SplatScene,
    InferenceContract,
    SceneReliabilityError,
    ContractViolationError,
)


# ---------------------------------------------------------------------------
# CameraPose Tests
# ---------------------------------------------------------------------------

class TestCameraPose:
    """Value Object: position + orientation of a single COLMAP camera."""

    def test_valid_unit_quaternion_is_accepted(self):
        """A normalized quaternion (|q| = 1.0) must be accepted without error."""
        pose = CameraPose(
            frame_id="trip_001_frame_0042",
            translation=[1.0, 2.0, 3.0],
            quaternion=[1.0, 0.0, 0.0, 0.0],  # identity rotation
        )
        assert pose.frame_id == "trip_001_frame_0042"

    def test_nearly_unit_quaternion_within_tolerance_is_accepted(self):
        """Quaternions with |q| = 1 ± 1e-4 must be accepted (COLMAP float precision)."""
        # |q| ≈ 1.00003 — within tolerance
        pose = CameraPose(
            frame_id="trip_001_frame_0100",
            translation=[0.0, 0.0, 0.0],
            quaternion=[0.70711, 0.70711, 0.00005, 0.0],
        )
        assert pose is not None

    def test_unnormalized_quaternion_raises_value_error(self):
        """A non-unit quaternion from a buggy COLMAP export must be rejected at the Domain boundary."""
        with pytest.raises(ValueError, match="quaternion"):
            CameraPose(
                frame_id="trip_001_frame_0200",
                translation=[0.0, 0.0, 0.0],
                quaternion=[2.0, 0.0, 0.0, 0.0],  # |q| = 2.0 — invalid
            )

    def test_zero_quaternion_raises_value_error(self):
        """A zero quaternion is completely invalid."""
        with pytest.raises(ValueError, match="quaternion"):
            CameraPose(
                frame_id="trip_001_frame_0300",
                translation=[0.0, 0.0, 0.0],
                quaternion=[0.0, 0.0, 0.0, 0.0],
            )

    def test_translation_must_have_3_components(self):
        """Translation vector must be exactly [tx, ty, tz]."""
        with pytest.raises(ValueError, match="translation"):
            CameraPose(
                frame_id="trip_001_frame_0400",
                translation=[1.0, 2.0],  # only 2 components
                quaternion=[1.0, 0.0, 0.0, 0.0],
            )

    def test_quaternion_must_have_4_components(self):
        """Quaternion must be exactly [qw, qx, qy, qz]."""
        with pytest.raises(ValueError, match="quaternion"):
            CameraPose(
                frame_id="trip_001_frame_0500",
                translation=[1.0, 2.0, 3.0],
                quaternion=[1.0, 0.0, 0.0],  # 3 components — invalid
            )

    def test_camera_pose_is_immutable(self):
        """CameraPose is a Value Object — it must be frozen/immutable."""
        pose = CameraPose(
            frame_id="trip_001_frame_0042",
            translation=[1.0, 2.0, 3.0],
            quaternion=[1.0, 0.0, 0.0, 0.0],
        )
        with pytest.raises(Exception):  # Pydantic frozen raises ValidationError or TypeError
            pose.frame_id = "hacked"


# ---------------------------------------------------------------------------
# SplatScene Tests
# ---------------------------------------------------------------------------

class TestSplatScene:
    """Entity: result of 3DGS reconstruction, carries reliability metrics."""

    def _valid_poses(self) -> list[CameraPose]:
        return [
            CameraPose(
                frame_id=f"trip_001_frame_{i:04d}",
                translation=[float(i), 0.0, 0.0],
                quaternion=[1.0, 0.0, 0.0, 0.0],
            )
            for i in range(10)
        ]

    def test_valid_scene_is_accepted(self):
        """A well-reconstructed scene with sufficient points must be created without errors."""
        scene = SplatScene(
            scene_id="scene_trip_001",
            camera_poses=self._valid_poses(),
            num_gaussians=150_000,
            average_reprojection_error=0.8,
            point_cloud_density=0.75,
        )
        assert scene.scene_id == "scene_trip_001"
        assert scene.num_gaussians == 150_000

    def test_scene_with_zero_gaussians_raises_reliability_error(self):
        """A reconstruction with 0 gaussians is a failed scene — must be rejected."""
        with pytest.raises(SceneReliabilityError, match="num_gaussians"):
            SplatScene(
                scene_id="scene_bad",
                camera_poses=self._valid_poses(),
                num_gaussians=0,
                average_reprojection_error=0.8,
                point_cloud_density=0.75,
            )

    def test_scene_with_no_camera_poses_raises_reliability_error(self):
        """A scene with no registered camera poses is meaningless."""
        with pytest.raises(SceneReliabilityError, match="camera_poses"):
            SplatScene(
                scene_id="scene_empty_poses",
                camera_poses=[],
                num_gaussians=10_000,
                average_reprojection_error=0.8,
                point_cloud_density=0.75,
            )

    def test_scene_with_high_reprojection_error_raises_reliability_error(self):
        """A scene where reprojection error > 2.0 pixels indicates a floater cloud — rejected."""
        with pytest.raises(SceneReliabilityError, match="reprojection_error"):
            SplatScene(
                scene_id="scene_poor_quality",
                camera_poses=self._valid_poses(),
                num_gaussians=50_000,
                average_reprojection_error=5.2,  # terrible reconstruction
                point_cloud_density=0.75,
            )


# ---------------------------------------------------------------------------
# InferenceContract Tests
# ---------------------------------------------------------------------------

class TestInferenceContract:
    """Value Object: rules a SplatScene must satisfy before synthetic injection."""

    def _good_scene(self) -> SplatScene:
        poses = [
            CameraPose(
                frame_id=f"trip_001_frame_{i:04d}",
                translation=[float(i), 0.0, 0.0],
                quaternion=[1.0, 0.0, 0.0, 0.0],
            )
            for i in range(15)
        ]
        return SplatScene(
            scene_id="scene_good",
            camera_poses=poses,
            num_gaussians=200_000,
            average_reprojection_error=0.6,
            point_cloud_density=0.85,
        )

    def test_contract_passes_for_high_quality_scene(self):
        """A scene meeting all contract thresholds must pass validation."""
        contract = InferenceContract(
            min_gaussians=100_000,
            max_reprojection_error=1.5,
            min_camera_poses=10,
        )
        # Must not raise
        contract.validate(self._good_scene())

    def test_contract_rejects_scene_with_insufficient_gaussians(self):
        """Contract must reject scenes that don't meet the min gaussian count."""
        # Build a scene that passes SplatScene's own thresholds but not the contract's
        poses = [
            CameraPose(
                frame_id=f"trip_001_frame_{i:04d}",
                translation=[float(i), 0.0, 0.0],
                quaternion=[1.0, 0.0, 0.0, 0.0],
            )
            for i in range(15)
        ]
        sparse_scene = SplatScene(
            scene_id="scene_sparse",
            camera_poses=poses,
            num_gaussians=5_000,  # passes SplatScene min (>0) but below contract threshold
            average_reprojection_error=0.8,
            point_cloud_density=0.6,
        )
        contract = InferenceContract(
            min_gaussians=100_000,
            max_reprojection_error=1.5,
            min_camera_poses=10,
        )
        with pytest.raises(ContractViolationError, match="num_gaussians"):
            contract.validate(sparse_scene)

    def test_contract_rejects_scene_with_too_few_poses(self):
        """Contract must reject scenes below the minimum required camera poses."""
        few_poses = [
            CameraPose(
                frame_id=f"trip_001_frame_{i:04d}",
                translation=[float(i), 0.0, 0.0],
                quaternion=[1.0, 0.0, 0.0, 0.0],
            )
            for i in range(3)  # only 3 poses
        ]
        scene = SplatScene(
            scene_id="scene_few_poses",
            camera_poses=few_poses,
            num_gaussians=200_000,
            average_reprojection_error=0.5,
            point_cloud_density=0.9,
        )
        contract = InferenceContract(
            min_gaussians=100_000,
            max_reprojection_error=1.5,
            min_camera_poses=10,
        )
        with pytest.raises(ContractViolationError, match="camera_poses"):
            contract.validate(scene)
