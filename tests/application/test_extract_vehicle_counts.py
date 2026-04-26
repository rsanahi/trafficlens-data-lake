import pytest
import os
from pathlib import Path
from core.vehicle_detection.domain.ports.i_vehicle_detection_ports import (
    VehicleDetectorPort,
    VehicleCountsRepositoryPort,
)
from core.vehicle_detection.domain.model import FrameVehicleCounts
from core.vehicle_detection.application.extract_vehicle_counts_use_case import ExtractVehicleCountsUseCase


class FakeVehicleDetector(VehicleDetectorPort):
    def __init__(self):
        self.invocations = []
        # Return a deterministic value for tests
        self.mock_response = FrameVehicleCounts(frame_filename="dummy.jpg", car_count=2, motorcycle_count=1)

    def detect(self, frame_path: str) -> FrameVehicleCounts:
        self.invocations.append(frame_path)
        # Update the filename to match the path passed for reality check
        filename = Path(frame_path).name
        return FrameVehicleCounts(frame_filename=filename, 
                                  car_count=self.mock_response.car_count, 
                                  motorcycle_count=self.mock_response.motorcycle_count)


class FakeVehicleCountsRepository(VehicleCountsRepositoryPort):
    def __init__(self):
        self.saved_data = {}

    def save(self, video_id: str, counts: list[FrameVehicleCounts]) -> None:
        self.saved_data[video_id] = counts

    def exists(self, video_id: str) -> bool:
        return video_id in self.saved_data


@pytest.fixture
def temp_frames_dir(tmp_path):
    """Fixture to create a temporary directory with fake frame images."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_0001.jpg").touch()
    (frames_dir / "frame_0002.jpg").touch()
    return str(frames_dir)


def test_extract_vehicle_counts_successfully_processes_and_saves_frames(temp_frames_dir):
    # Setup Fakes
    detector = FakeVehicleDetector()
    repository = FakeVehicleCountsRepository()
    use_case = ExtractVehicleCountsUseCase(detector, repository)

    video_id = "test_video_123"

    # Action
    use_case.execute(video_id=video_id, frames_dir=temp_frames_dir)

    # Asserts - Verification of Ubiquitous Behavior
    assert len(detector.invocations) == 2, "Detector should have been called for each frame"
    
    assert video_id in repository.saved_data, "Counts should be saved in the repository under the video_id"
    saved_counts = repository.saved_data[video_id]
    
    assert len(saved_counts) == 2, "There should be two FrameVehicleCounts saved"
    assert saved_counts[0].frame_filename == "frame_0001.jpg"
    assert saved_counts[0].car_count == 2
    assert saved_counts[0].motorcycle_count == 1
