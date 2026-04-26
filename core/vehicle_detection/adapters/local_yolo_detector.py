"""
Infrastructure Adapter: LocalYoloDetector

Uses local YOLOv8 to detect vehicles in dashcam frames.

Canonical location: core/vehicle_detection/adapters/local_yolo_detector.py
"""
from pathlib import Path

from core.vehicle_detection.domain.ports.i_vehicle_detection_ports import VehicleDetectorPort
from core.vehicle_detection.domain.model import FrameVehicleCounts

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


class LocalYoloDetector(VehicleDetectorPort):
    """Infrastructure Adapter: Uses local YOLOv8 to detect vehicles in frames."""

    def __init__(self, model_path: str = "yolov8n.pt"):
        if YOLO is None:
            raise ImportError("ultralytics package is required for LocalYoloDetector.")

        # Load the pre-trained YOLO model (downloads on first run if not present)
        self.model = YOLO(model_path)

    def detect(self, frame_path: str) -> FrameVehicleCounts:
        frame_filename = Path(frame_path).name

        # Run inference (stream=False by default for single images)
        results = self.model(frame_path, verbose=False)

        car_count = 0
        motorcycle_count = 0

        # COCO class IDs: 2 is car, 3 is motorcycle
        for r in results:
            if r.boxes is not None and r.boxes.cls is not None:
                classes = r.boxes.cls.cpu().numpy()
                car_count += int((classes == 2).sum())
                motorcycle_count += int((classes == 3).sum())

        return FrameVehicleCounts(
            frame_filename=frame_filename,
            car_count=car_count,
            motorcycle_count=motorcycle_count
        )
