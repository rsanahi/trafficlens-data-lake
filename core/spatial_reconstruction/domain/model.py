"""
Spatial Reconstruction Domain — Core Entities & Value Objects.

Design constraints (non-negotiable):
- Pure Python types only (list[float], no numpy, no torch).
- CameraPose: raises ValueError if quaternion is not normalized (|q| = 1 ± 1e-4).
- SplatScene: raises SceneReliabilityError if reliability metrics are invalid.
- InferenceContract: raises ContractViolationError if a scene fails pre-injection checks.
- All entities are frozen (immutable Value Objects) or validated Entities.
"""
import math
from pydantic import BaseModel, field_validator, model_validator

from core.spatial_reconstruction.domain.exceptions.domain_exceptions import (
    SceneReliabilityError,
    ContractViolationError,
)

# ---------------------------------------------------------------------------
# CameraPose — Value Object
# ---------------------------------------------------------------------------

QUATERNION_TOLERANCE = 1e-4


class CameraPose(BaseModel):
    """
    Value Object: position and orientation of a single camera frame,
    as extracted by COLMAP (SfM).

    Ubiquitous Language:
    - frame_id: unique identifier linking back to a Bronze Layer frame asset.
    - translation: [tx, ty, tz] world-space position of the camera center.
    - quaternion: [qw, qx, qy, qz] unit quaternion representing camera rotation.

    Invariant: |quaternion| must equal 1.0 ± 1e-4. Any COLMAP adapter
    is responsible for normalizing its output before constructing this object.
    """
    model_config = {"frozen": True}

    frame_id: str
    translation: list[float]
    quaternion: list[float]

    @field_validator("translation")
    @classmethod
    def translation_must_have_3_components(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError(
                f"translation must have exactly 3 components [tx, ty, tz], got {len(v)}."
            )
        return v

    @field_validator("quaternion")
    @classmethod
    def quaternion_must_be_unit(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError(
                f"quaternion must have exactly 4 components [qw, qx, qy, qz], got {len(v)}."
            )
        norm = math.sqrt(sum(c ** 2 for c in v))
        if abs(norm - 1.0) > QUATERNION_TOLERANCE:
            raise ValueError(
                f"quaternion is not normalized: |q| = {norm:.6f} "
                f"(expected 1.0 ± {QUATERNION_TOLERANCE}). "
                "The COLMAP adapter must normalize the quaternion before constructing CameraPose."
            )
        return v


# ---------------------------------------------------------------------------
# SplatScene — Entity
# ---------------------------------------------------------------------------

MAX_REPROJECTION_ERROR = 2.0  # pixels — above this is a "floater cloud"


class SplatScene(BaseModel):
    """
    Entity: the result of a 3D Gaussian Splatting reconstruction pass.

    Carries reliability metrics validated at creation time. A scene must
    meet minimum thresholds to even exist in the domain — bad reconstructions
    are rejected at the boundary, not silently propagated downstream.

    Ubiquitous Language:
    - scene_id: unique identifier for the reconstructed scene.
    - camera_poses: all CameraPose objects used in the reconstruction.
    - num_gaussians: total number of 3D Gaussians produced.
    - average_reprojection_error: mean pixel error across registered cameras.
    - point_cloud_density: ratio of registered points vs estimated (0.0–1.0).
    """
    model_config = {"frozen": True}

    scene_id: str
    camera_poses: list[CameraPose]
    num_gaussians: int
    average_reprojection_error: float
    point_cloud_density: float

    @model_validator(mode="after")
    def validate_reliability(self) -> "SplatScene":
        if not self.camera_poses:
            raise SceneReliabilityError(
                "camera_poses cannot be empty. "
                "A SplatScene requires at least one registered CameraPose."
            )
        if self.num_gaussians <= 0:
            raise SceneReliabilityError(
                f"num_gaussians must be > 0, got {self.num_gaussians}. "
                "A reconstruction with zero Gaussians indicates a failed pipeline run."
            )
        if self.average_reprojection_error > MAX_REPROJECTION_ERROR:
            raise SceneReliabilityError(
                f"average_reprojection_error = {self.average_reprojection_error:.2f} px "
                f"exceeds the maximum allowed threshold of {MAX_REPROJECTION_ERROR} px. "
                "This scene likely contains floater clouds and cannot be used."
            )
        return self


# ---------------------------------------------------------------------------
# InferenceContract — Value Object
# ---------------------------------------------------------------------------

class InferenceContract(BaseModel):
    """
    Value Object: a set of minimum quality thresholds that a SplatScene must
    satisfy before being cleared for synthetic scenario injection or active learning.

    This is the final reliability gate before any data enters the retraining pipeline.

    Ubiquitous Language:
    - min_gaussians: minimum number of Gaussians required for a scene to represent
      sufficient geometric detail.
    - max_reprojection_error: maximum allowable reprojection error (pixels).
    - min_camera_poses: minimum number of registered camera views required.
    """
    model_config = {"frozen": True}

    min_gaussians: int
    max_reprojection_error: float
    min_camera_poses: int

    def validate(self, scene: SplatScene) -> None:
        """
        Validate a SplatScene against this contract.

        Raises ContractViolationError if ANY threshold is not met,
        preventing automatic synthetic injection on low-quality scenes.
        """
        if scene.num_gaussians < self.min_gaussians:
            raise ContractViolationError(
                f"num_gaussians = {scene.num_gaussians} is below the contract minimum "
                f"of {self.min_gaussians}. Scene '{scene.scene_id}' is not cleared for injection."
            )
        if scene.average_reprojection_error > self.max_reprojection_error:
            raise ContractViolationError(
                f"average_reprojection_error = {scene.average_reprojection_error:.2f} px "
                f"exceeds the contract maximum of {self.max_reprojection_error} px. "
                f"Scene '{scene.scene_id}' is not cleared for injection."
            )
        if len(scene.camera_poses) < self.min_camera_poses:
            raise ContractViolationError(
                f"camera_poses count = {len(scene.camera_poses)} is below the contract minimum "
                f"of {self.min_camera_poses}. "
                f"Scene '{scene.scene_id}' lacks sufficient camera coverage."
            )
