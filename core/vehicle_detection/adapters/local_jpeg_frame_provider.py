"""
Infrastructure Layer — LocalJpegFrameProvider

Concrete adapter implementing FrameProviderPort using pathlib filesystem scanning.

Canonical location: core/vehicle_detection/adapters/local_jpeg_frame_provider.py

Responsibilities:
  - Scanning a local directory for .jpg files.
  - Returning their absolute paths in deterministic sorted order.
  - Raising FileNotFoundError for missing or invalid directories.
"""
from pathlib import Path

from core.vehicle_detection.domain.ports.i_vehicle_detection_ports import FrameProviderPort


class LocalJpegFrameProvider(FrameProviderPort):
    """
    Scans a local filesystem directory and returns sorted .jpg frame paths.

    This adapter resolves the infrastructure seam that previously lived inside
    ExtractVehicleCountsUseCase._resolve_frame_paths(). By extracting it here,
    the use case becomes fully infrastructure-agnostic: frame discovery can be
    replaced with an S3 listing, a database query, or any other source without
    changing the application layer.
    """

    def get_frame_paths(self, frames_dir: str) -> list[str]:
        """
        Return a sorted list of absolute .jpg frame paths from frames_dir.

        Args:
            frames_dir: path to a Bronze Layer directory containing .jpg frames.

        Returns:
            Sorted list of absolute paths to all JPEG frames in the directory.
            Returns an empty list if the directory contains no .jpg files.

        Raises:
            FileNotFoundError: if frames_dir does not exist or is not a directory.
        """
        frames_path = Path(frames_dir)
        if not frames_path.exists() or not frames_path.is_dir():
            raise FileNotFoundError(f"Frames directory not found: {frames_dir}")
        return sorted(str(p) for p in frames_path.glob("*.jpg"))
