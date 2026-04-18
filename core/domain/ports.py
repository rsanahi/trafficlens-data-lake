from abc import ABC, abstractmethod
from core.domain.telemetry_record import TelemetryRecord
from core.domain.video_metadata import VideoMetadata
from core.domain.vehicle_counts import FrameVehicleCounts
from core.domain.spatial_reconstruction import CameraPose, SplatScene


class VideoReaderPort(ABC):
    """Port: reads telemetry records from a video source."""

    @abstractmethod
    def read_records(self, metadata: VideoMetadata) -> list[TelemetryRecord]:
        ...


class TelemetryRepositoryPort(ABC):
    """Port: persists and checks telemetry records."""

    @abstractmethod
    def save(self, records: list[TelemetryRecord], path: str) -> None:
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        ...


class VehicleDetectorPort(ABC):
    """Port: analyzes a frame image and detects the vehicles present."""

    @abstractmethod
    def detect(self, frame_path: str) -> FrameVehicleCounts:
        ...


class VehicleCountsRepositoryPort(ABC):
    """Port: persists the series of frame detection counts for a video."""

    @abstractmethod
    def save(self, video_id: str, counts: list[FrameVehicleCounts]) -> None:
        ...

    @abstractmethod
    def exists(self, video_id: str) -> bool:
        ...


class SfMMapperPort(ABC):
    """
    Port: takes a collection of frame image paths and produces
    a list of CameraPose objects (position + orientation per frame).

    Optionally accepts GPS telemetry records to enable metric-scale reconstruction:
    - Without GPS: arbitrary scale (suitable for visual-only use cases).
    - With GPS: metric scale in meters (required for synthetic scenario injection).

    Concrete adapters: ColmapSfMAdapter (local), AwsRekonstructionAdapter (cloud).
    The application layer must never import COLMAP or any SfM library directly.
    """

    @abstractmethod
    def map_poses(
        self,
        frame_paths: list[str],
        telemetry: list["TelemetryRecord"] | None = None,
    ) -> list[CameraPose]:
        """
        Run Structure-from-Motion on a set of frames.

        Args:
            frame_paths: absolute paths to the extracted Bronze Layer frame images.

        Returns:
            A list of CameraPose objects with normalized quaternions.
            The adapter is responsible for normalization before constructing CameraPose.
        """
        ...


class GaussianTrainerPort(ABC):
    """
    Port: takes a set of CameraPose objects and trains a 3D Gaussian Splatting model,
    returning a validated SplatScene entity.

    Concrete adapters: NerfstudioSplatfactoAdapter (local MPS), AwsSageMakerAdapter (cloud).
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
