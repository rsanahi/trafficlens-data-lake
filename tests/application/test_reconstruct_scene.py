"""
RED Phase — ReconstructSceneUseCase Tests

The Application Layer orchestrates the 3DGS pipeline using only ports (no infrastructure imports).
All dependencies are injected via fakes (in-memory stubs) — zero mocking frameworks needed.

Use Case flow:
    frame_paths -> SfMMapperPort -> [CameraPose] -> GaussianTrainerPort -> SplatScene
                                                                              |
                                                                       InferenceContract.validate()
                                                                              |
                                                                        SplatScene (cleared)
"""
import pytest

from core.spatial_reconstruction.domain.model import (
    CameraPose,
    SplatScene,
    InferenceContract,
)
from core.spatial_reconstruction.domain.exceptions.domain_exceptions import (
    SceneReliabilityError,
    ContractViolationError,
)
from core.spatial_reconstruction.domain.ports.i_spatial_reconstruction_ports import (
    SfMMapperPort,
    GaussianTrainerPort,
)
from core.spatial_reconstruction.application.reconstruct_scene_use_case import ReconstructSceneUseCase


# ---------------------------------------------------------------------------
# In-Memory Fakes (no mocks, no patches — pure DDD)
# ---------------------------------------------------------------------------

def _make_pose(i: int) -> CameraPose:
    return CameraPose(
        frame_id=f"trip_001_frame_{i:04d}",
        translation=[float(i), 0.0, 0.0],
        quaternion=[1.0, 0.0, 0.0, 0.0],
    )


class FakeSfMMapper(SfMMapperPort):
    """Returns a fixed number of CameraPoses, independent of actual file content."""

    def __init__(self, num_poses: int = 15):
        self.num_poses = num_poses
        self.called_with_paths: list[str] = []
        self.called_with_telemetry: list["TelemetryRecord"] | None = None

    def map_poses(
        self,
        frame_paths: list[str],
        telemetry: list["TelemetryRecord"] | None = None,
    ) -> list[CameraPose]:
        self.called_with_paths = frame_paths
        self.called_with_telemetry = telemetry
        return [_make_pose(i) for i in range(self.num_poses)]


class FakeGaussianTrainer(GaussianTrainerPort):
    """Returns a synthetic SplatScene with configurable reliability metrics."""

    def __init__(
        self,
        num_gaussians: int = 200_000,
        reprojection_error: float = 0.5,
    ):
        self.num_gaussians = num_gaussians
        self.reprojection_error = reprojection_error
        self.called_with_scene_id: str | None = None

    def train(self, camera_poses: list[CameraPose], scene_id: str) -> SplatScene:
        self.called_with_scene_id = scene_id
        return SplatScene(
            scene_id=scene_id,
            camera_poses=camera_poses,
            num_gaussians=self.num_gaussians,
            average_reprojection_error=self.reprojection_error,
            point_cloud_density=0.85,
        )


class FakeFailingGaussianTrainer(GaussianTrainerPort):
    """Simulates a training run that produces a degenerate scene (floater cloud)."""

    def train(self, camera_poses: list[CameraPose], scene_id: str) -> SplatScene:
        raise SceneReliabilityError(
            "Training diverged: num_gaussians = 0. Reconstruction failed."
        )


# ---------------------------------------------------------------------------
# ReconstructSceneUseCase Tests
# ---------------------------------------------------------------------------

class TestReconstructSceneUseCase:

    def _default_contract(self) -> InferenceContract:
        return InferenceContract(
            min_gaussians=100_000,
            max_reprojection_error=1.5,
            min_camera_poses=10,
        )

    def test_successful_reconstruction_returns_cleared_splat_scene(self):
        """
        Happy path: SfM produces good poses, trainer returns a high-quality scene,
        contract is satisfied — use case returns the validated SplatScene.
        """
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(num_poses=15),
            gaussian_trainer=FakeGaussianTrainer(num_gaussians=200_000, reprojection_error=0.5),
            inference_contract=self._default_contract(),
        )

        scene = use_case.execute(
            frame_paths=["frame_0.jpg", "frame_1.jpg"],
            scene_id="scene_trip_001",
        )

        assert scene.scene_id == "scene_trip_001"
        assert scene.num_gaussians == 200_000
        assert len(scene.camera_poses) == 15

    def test_sfm_mapper_receives_frame_paths_and_telemetry(self):
        """The use case must forward frame_paths and telemetry to the SfM mapper unchanged."""
        mapper = FakeSfMMapper(num_poses=12)
        use_case = ReconstructSceneUseCase(
            sfm_mapper=mapper,
            gaussian_trainer=FakeGaussianTrainer(),
            inference_contract=self._default_contract(),
        )
        frame_paths = ["a.jpg", "b.jpg"]
        
        # Test 1: Without telemetry
        use_case.execute(frame_paths=frame_paths, scene_id="scene_002")
        assert mapper.called_with_paths == frame_paths
        assert mapper.called_with_telemetry is None
        
        # Test 2: With telemetry
        from core.telemetry.domain.model import TelemetryRecord
        fake_telemetry = [TelemetryRecord(raw_text="fake", latitude=0.0, longitude=0.0)]
        use_case.execute(frame_paths=frame_paths, scene_id="scene_003", telemetry=fake_telemetry)
        assert mapper.called_with_telemetry == fake_telemetry

    def test_gaussian_trainer_receives_correct_scene_id(self):
        """The trainer must receive the scene_id the caller specified."""
        trainer = FakeGaussianTrainer()
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(),
            gaussian_trainer=trainer,
            inference_contract=self._default_contract(),
        )
        use_case.execute(frame_paths=["x.jpg"], scene_id="scene_custom_id")

        assert trainer.called_with_scene_id == "scene_custom_id"

    def test_empty_frame_paths_raises_value_error(self):
        """
        The use case must reject empty frame lists before calling any port.
        Calling SfM on zero frames is meaningless — fail fast at the boundary.
        """
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(),
            gaussian_trainer=FakeGaussianTrainer(),
            inference_contract=self._default_contract(),
        )
        with pytest.raises(ValueError, match="frame_paths"):
            use_case.execute(frame_paths=[], scene_id="scene_empty")

    def test_failed_training_propagates_scene_reliability_error(self):
        """
        If the Gaussian trainer raises SceneReliabilityError (e.g., floater cloud),
        the use case must propagate it — do NOT silently swallow domain errors.
        """
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(),
            gaussian_trainer=FakeFailingGaussianTrainer(),
            inference_contract=self._default_contract(),
        )
        with pytest.raises(SceneReliabilityError):
            use_case.execute(frame_paths=["x.jpg"], scene_id="scene_bad")

    def test_contract_violation_propagates_as_contract_violation_error(self):
        """
        A scene that passes SplatScene's own constraints but fails the InferenceContract
        (e.g., too few gaussians for retraining) must raise ContractViolationError.
        The use case must NOT clear scenes that violate the contract.
        """
        strict_contract = InferenceContract(
            min_gaussians=500_000,   # very high threshold
            max_reprojection_error=1.5,
            min_camera_poses=10,
        )
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(num_poses=15),
            gaussian_trainer=FakeGaussianTrainer(num_gaussians=200_000),  # below contract
            inference_contract=strict_contract,
        )
        with pytest.raises(ContractViolationError):
            use_case.execute(frame_paths=["x.jpg"], scene_id="scene_sparse")

    def test_scene_id_cannot_be_empty_string(self):
        """A blank scene_id would produce unidentifiable reconstructions in the Data Lake."""
        use_case = ReconstructSceneUseCase(
            sfm_mapper=FakeSfMMapper(),
            gaussian_trainer=FakeGaussianTrainer(),
            inference_contract=self._default_contract(),
        )
        with pytest.raises(ValueError, match="scene_id"):
            use_case.execute(frame_paths=["x.jpg"], scene_id="")
