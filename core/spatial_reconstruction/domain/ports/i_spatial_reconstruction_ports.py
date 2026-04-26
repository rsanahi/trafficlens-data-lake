"""
Spatial Reconstruction — Domain Ports

Bounded context: Structure-from-Motion (SfM) and 3D Gaussian Splatting reconstruction
of dashcam scenes for synthetic scenario injection and active learning.

These ports define the outbound interfaces that the Spatial Reconstruction bounded
context requires from the infrastructure layer. The application layer depends only on
these abstractions — never on COLMAP, Nerfstudio, nerfstudio, or any 3D library.

Ubiquitous Language:
- CameraPose:          position and orientation of a single camera frame (from SfM).
- SplatScene:          result of a 3DGS reconstruction pass, with reliability metrics.
- SfMMapperPort:       runs Structure-from-Motion on a set of frames → [CameraPose].
- GaussianTrainerPort: trains a 3DGS model from registered poses → SplatScene.

Cross-context dependency (Conformist pattern):
  SfMMapperPort optionally accepts TelemetryRecord to enable metric-scale
  reconstruction via GPS priors. This is a deliberate cross-context data flow:
  the Telemetry Ingestion context produces the records; this context consumes them
  as optional input.

  Relationship type: Conformist.
    - Spatial Reconstruction conforms to the Telemetry Ingestion model (TelemetryRecord)
      without translation or anti-corruption layer.
    - This is acceptable because TelemetryRecord is a stable, pure Value Object with
      no lifecycle and no Telemetry-specific behavior that would contaminate this context.
    - If TelemetryRecord evolves (e.g., gains Telemetry-context invariants), introduce
      an anti-corruption layer (e.g., GpsPrior VO) to translate at the boundary.

  Dependency direction: one-way — Spatial reads Telemetry VOs; Telemetry NEVER imports
  Spatial concepts.
"""
from abc import ABC, abstractmethod

from core.spatial_reconstruction.domain.model import CameraPose, SplatScene
from core.telemetry.domain.model import TelemetryRecord


class SfMMapperPort(ABC):
    """
    Port: takes a collection of frame image paths and produces
    a list of CameraPose objects (position + orientation per frame).

    Optionally accepts GPS telemetry records to enable metric-scale reconstruction:
    - Without GPS: arbitrary scale (suitable for visual-only use cases).
    - With GPS: metric scale in meters (required for synthetic scenario injection).

    Concrete adapters live in core/spatial_reconstruction/adapters/ and must implement this port.
    The application layer must never import COLMAP or any SfM library directly.
    """

    @abstractmethod
    def map_poses(
        self,
        frame_paths: list[str],
        telemetry: list[TelemetryRecord] | None = None,
    ) -> list[CameraPose]:
        """
        Run Structure-from-Motion on a set of frames.

        Args:
            frame_paths: absolute paths to the extracted Bronze Layer frame images.
            telemetry:   optional GPS records aligned to frame_paths for metric scale.

        Returns:
            A list of CameraPose objects with normalized quaternions.
            The adapter is responsible for normalization before constructing CameraPose.
        """
        ...


class GaussianTrainerPort(ABC):
    """
    Port: takes a set of CameraPose objects and trains a 3D Gaussian Splatting model,
    returning a validated SplatScene entity.

    Concrete adapters live in core/spatial_reconstruction/adapters/ and must implement this port.
    The application layer must never import nerfstudio or any training library directly.
    """

    @abstractmethod
    def train(self, camera_poses: list[CameraPose], scene_id: str) -> SplatScene:
        """
        Train a 3DGS model from registered camera poses.

        Args:
            camera_poses: validated CameraPose objects from SfMMapperPort.
            scene_id: unique identifier for the resulting scene.

        Returns:
            A SplatScene entity containing reliability metrics.
            The adapter is responsible for satisfying SplatScene's internal constraints.
        """
        ...
