"""
Application Layer — ReconstructSceneUseCase

Orchestrates the full 3D Gaussian Splatting reconstruction pipeline:
    frame_paths  →  SfMMapperPort  →  [CameraPose]
                →  GaussianTrainerPort  →  SplatScene
                →  InferenceContract.validate()
                →  SplatScene (cleared for synthetic injection)

Clean Architecture constraints:
- ZERO infrastructure imports (no COLMAP, no nerfstudio, no torch).
- All dependencies injected via ports at construction time.
- Business rules (validation order, error propagation) live here, not in adapters.
"""
from core.domain.spatial_reconstruction import InferenceContract, SplatScene
from core.domain.ports import SfMMapperPort, GaussianTrainerPort
from core.domain.telemetry_record import TelemetryRecord


class ReconstructSceneUseCase:
    """
    Orchestrates the pipeline from raw frames to a contract-cleared SplatScene.

    Optionally accepts GPS telemetry to enable metric-scale reconstruction.
    When telemetry is provided, the SfMMapperPort injects GPS priors into COLMAP,
    aligning the scene to real-world metric coordinates (meters). This is required
    for accurate synthetic scenario injection (correct object scale).

    Two reliability gates (non-optional):
    1. SplatScene's internal invariants (SceneReliabilityError on bad reconstructions).
    2. InferenceContract.validate() — prevents low-quality scenes from entering
       synthetic injection or active learning pipelines (ContractViolationError).
    """

    def __init__(
        self,
        sfm_mapper: SfMMapperPort,
        gaussian_trainer: GaussianTrainerPort,
        inference_contract: InferenceContract,
    ) -> None:
        self._sfm_mapper = sfm_mapper
        self._gaussian_trainer = gaussian_trainer
        self._inference_contract = inference_contract

    def execute(
        self,
        frame_paths: list[str],
        scene_id: str,
        telemetry: list[TelemetryRecord] | None = None,
    ) -> SplatScene:
        """
        Run the full reconstruction pipeline and return a validated SplatScene.

        Args:
            frame_paths: absolute paths to Bronze Layer frame images (.jpg).
                         Must be non-empty — SfM on zero frames is undefined.
            scene_id:    unique identifier for the resulting scene in the Data Lake.
                         Must be non-empty to ensure traceability.
            telemetry:   optional GPS telemetry aligned to frame_paths.
                         When provided, enables metric-scale reconstruction.
                         When None, reconstruction uses arbitrary (visual-only) scale.

        Returns:
            A SplatScene entity that has passed all reliability and contract gates.
            If telemetry is provided, the scene is georeferenced at metric scale.

        Raises:
            ValueError: if frame_paths is empty or scene_id is blank.
            SceneReliabilityError: if the reconstruction produces a degenerate scene.
            ContractViolationError: if the scene fails the InferenceContract thresholds.
        """
        # --- Input validation: fail fast before calling any port ---
        if not frame_paths:
            raise ValueError(
                "frame_paths cannot be empty. "
                "Provide at least one Bronze Layer frame path to run SfM."
            )
        if not scene_id or not scene_id.strip():
            raise ValueError(
                "scene_id cannot be empty. "
                "A blank scene_id would produce unidentifiable reconstructions in the Data Lake."
            )

        # Gate 1: SfM with optional GPS alignment → [CameraPose]
        camera_poses = self._sfm_mapper.map_poses(frame_paths, telemetry)

        # Gate 2: 3DGS Training → SplatScene (SceneReliabilityError propagates)
        scene = self._gaussian_trainer.train(camera_poses, scene_id)

        # Gate 3: InferenceContract → final reliability gate before injection
        self._inference_contract.validate(scene)

        return scene
