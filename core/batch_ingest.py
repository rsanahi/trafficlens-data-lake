"""
Presentation Layer: thin CLI entry point for batch ingestion.
Wires infrastructure adapters into the use case and processes directories.
"""
from __future__ import annotations

import glob
import os
import subprocess

from core.application.extract_telemetry import ExtractTelemetryUseCase
from core.application.extract_vehicle_counts import ExtractVehicleCountsUseCase
from core.domain.video_metadata import VideoMetadata
from core.infrastructure.csv_telemetry_repository import CsvTelemetryRepository
from core.infrastructure.csv_detection_repository import CsvDetectionRepository
from core.infrastructure.ocr_video_reader import OcrVideoReader
from core.infrastructure.local_yolo_detector import LocalYoloDetector


def _discover_videos(input_dir: str) -> list[str]:
    patterns = [
        os.path.join(input_dir, "**", "*.mp4"),
        os.path.join(input_dir, "**", "*.MP4"),
    ]
    found = []
    for p in patterns:
        found.extend(glob.glob(p, recursive=True))
    return sorted(set(found))


def ingest_directory(input_dir: str, bronze_base: str, dry_run: bool = False) -> None:
    video_files = _discover_videos(input_dir)
    print(f"Found {len(video_files)} videos in {input_dir}")

    telemetry_repo = CsvTelemetryRepository()
    
    # Lazily instantiate YOLO so it doesn't load into RAM if we just run dbt or dry_run
    detector = None
    detection_repo = None
    counts_use_case = None

    for video_path in video_files:
        filename = os.path.basename(video_path)
        base_name = os.path.splitext(filename)[0]

        frames_dir = os.path.join(bronze_base, "frames")
        telemetry_path = os.path.join(bronze_base, "telemetry", f"{base_name}.csv")
        video_frames_dir = os.path.join(frames_dir, base_name)

        # 1. Telemetry Extraction
        if not telemetry_repo.exists(telemetry_path):
            print(f"Processing telemetry for {filename}...")
            if not dry_run:
                reader = OcrVideoReader(save_frames=True, frames_base_dir=frames_dir)
                use_case = ExtractTelemetryUseCase(reader=reader, repository=telemetry_repo)
                try:
                    use_case.execute(
                        metadata=VideoMetadata(path=video_path),
                        output_path=telemetry_path,
                    )
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    continue
        else:
            print(f"Skipping telemetry for {filename} — already processed.")
            
        # 2. Vehicle Counts (YOLO)
        if detection_repo is None and not dry_run:
            detector = LocalYoloDetector()
            detection_repo = CsvDetectionRepository(base_path=os.path.join(bronze_base, "detections"))
            counts_use_case = ExtractVehicleCountsUseCase(detector, detection_repo)
        
        if not dry_run and not detection_repo.exists(base_name):
            print(f"Counting vehicles for {filename} using YOLO...")
            try:
                counts_use_case.execute(video_id=base_name, frames_dir=video_frames_dir)
            except Exception as e:
                print(f"Error counting vehicles for {filename}: {e}")
        elif not dry_run:
             print(f"Skipping vehicle counts for {filename} — already processed.")


def _run_dbt(project_dir: str) -> None:
    print("\nRunning dbt transformations (Bronze → Silver → Gold)...")
    try:
        subprocess.run(["dbt", "run", "--profiles-dir", "."], cwd=project_dir, check=True)
        print("dbt run completed.")
    except subprocess.CalledProcessError as e:
        print(f"dbt run failed: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch ingest VIOFO videos to Data Lake")
    parser.add_argument("input_dir", help="Directory containing dashcam videos")
    parser.add_argument("--dry-run", action="store_true", help="List files without processing")
    args = parser.parse_args()

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    BRONZE_BASE = os.path.join(PROJECT_ROOT, "datalake", "bronze")
    DBT_DIR = os.path.join(SCRIPT_DIR, "dbt_project")

    ingest_directory(args.input_dir, BRONZE_BASE, args.dry_run)

    if not args.dry_run:
        _run_dbt(DBT_DIR)
