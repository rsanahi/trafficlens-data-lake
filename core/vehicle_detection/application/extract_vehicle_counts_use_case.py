"""
Application Layer — ExtractVehicleCountsUseCase

Bounded context: Vehicle Detection.

Orchestrates the vehicle detection pipeline for a set of dashcam frames:
    frames_dir  →  FrameProviderPort (frame paths)
                →  VehicleDetectorPort (per frame)
                →  VehicleCountsRepositoryPort (persistence)

Clean Architecture constraints (non-negotiable):
- ZERO ML/CV infrastructure imports. No ultralytics, no torch, no OpenCV.
- All detection behaviour is injected via VehicleDetectorPort at construction time.
- All persistence behaviour is injected via VehicleCountsRepositoryPort.
- All frame resolution behaviour is injected via FrameProviderPort.
- The use case is stateless — it holds only the injected port references.

Backward compatibility:
- frame_provider is optional. When None, the use case falls back to its own
  _resolve_frame_paths() inline implementation (filesystem glob via pathlib).
  This preserves compatibility with the existing test contract while the
  LocalJpegFrameProvider infrastructure adapter is implemented.
- New code should always inject a FrameProviderPort explicitly.
"""
from __future__ import annotations

from pathlib import Path

from core.vehicle_detection.domain.ports.i_vehicle_detection_ports import (
    VehicleDetectorPort,
    VehicleCountsRepositoryPort,
    FrameProviderPort,
)
from core.vehicle_detection.domain.model import FrameVehicleCounts


class ExtractVehicleCountsUseCase:
    """
    Application Service: orchestrates vehicle detection across all frames of a video.

    Typical caller flow:
        1. Provide a directory containing Bronze Layer JPEG frames for a video.
        2. Instantiate this use case with a LocalYoloDetector (or any VehicleDetectorPort),
           a CsvDetectionRepository (or any VehicleCountsRepositoryPort), and optionally
           a LocalJpegFrameProvider (or any FrameProviderPort).
        3. Call execute(video_id, frames_dir) — detections are persisted per frame.
    """

    def __init__(
        self,
        detector: VehicleDetectorPort,
        repository: VehicleCountsRepositoryPort,
        frame_provider: FrameProviderPort | None = None,
    ) -> None:
        self._detector = detector
        self._repository = repository
        self._frame_provider = frame_provider

    def execute(self, video_id: str, frames_dir: str) -> None:
        """
        Detect vehicles in every JPEG frame found in frames_dir and persist the results.

        Args:
            video_id:   unique identifier for the source video. Used as the persistence key.
            frames_dir: path to a directory containing Bronze Layer JPEG frame images.
                        The directory must exist and be non-empty to produce output.

        Raises:
            FileNotFoundError: if frames_dir does not exist or is not a directory.
        """
        if self._frame_provider is not None:
            frame_paths = self._frame_provider.get_frame_paths(frames_dir)
        else:
            frame_paths = self._resolve_frame_paths(frames_dir)

        counts: list[FrameVehicleCounts] = []
        for frame_path in frame_paths:
            frame_counts = self._detector.detect(frame_path)
            counts.append(frame_counts)

        if counts:
            self._repository.save(video_id, counts)

    # ---------------------------------------------------------------------------
    # Private: inline fallback when no FrameProviderPort is injected
    # ---------------------------------------------------------------------------

    def _resolve_frame_paths(self, frames_dir: str) -> list[str]:
        """
        Return a sorted list of absolute JPEG paths from frames_dir.

        Uses stdlib `pathlib.Path` — not an infrastructure library. pathlib is a
        Python standard-library utility and does not couple this use case to any
        external framework, cloud SDK, or ML library.

        Raises:
            FileNotFoundError: if frames_dir does not exist or is not a directory.
        """
        frames_path = Path(frames_dir)
        if not frames_path.exists() or not frames_path.is_dir():
            raise FileNotFoundError(f"Frames directory not found: {frames_dir}")
        return sorted(str(p) for p in frames_path.glob("*.jpg"))
