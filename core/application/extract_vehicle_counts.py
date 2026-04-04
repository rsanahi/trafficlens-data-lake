import os
from pathlib import Path
from core.domain.ports import VehicleDetectorPort, VehicleCountsRepositoryPort

class ExtractVehicleCountsUseCase:
    """Application Service: Orchestrates the detection of vehicles across frame images."""

    def __init__(self, detector: VehicleDetectorPort, repository: VehicleCountsRepositoryPort):
        self.detector = detector
        self.repository = repository

    def execute(self, video_id: str, frames_dir: str) -> None:
        """Executes the pipeline to count and save detections."""
        counts = []
        frames_path = Path(frames_dir)
        
        if not frames_path.exists() or not frames_path.is_dir():
            raise FileNotFoundError(f"Frames directory not found: {frames_dir}")
            
        for frame_file in sorted(frames_path.glob("*.jpg")):
            frame_counts = self.detector.detect(str(frame_file))
            counts.append(frame_counts)
            
        if counts:
            self.repository.save(video_id, counts)
