import csv
from pathlib import Path
from typing import List
from core.domain.ports import VehicleCountsRepositoryPort
from core.domain.vehicle_counts import FrameVehicleCounts

class CsvDetectionRepository(VehicleCountsRepositoryPort):
    """Infrastructure Adapter: Persists frame counts into Bronze CSV files."""

    def __init__(self, base_path: str = "datalake/bronze/detections"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, video_id: str, counts: List[FrameVehicleCounts]) -> None:
        """Saves a list of FrameVehicleCounts object to a CSV for dbt."""
        output_csv = self.base_path / f"{video_id}.csv"
        
        with open(output_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["frame_filename", "car_count", "motorcycle_count"])
            for c in counts:
                writer.writerow([c.frame_filename, c.car_count, c.motorcycle_count])

    def exists(self, video_id: str) -> bool:
        """Verifies if detection data exists for the given video."""
        output_csv = self.base_path / f"{video_id}.csv"
        return output_csv.exists()
