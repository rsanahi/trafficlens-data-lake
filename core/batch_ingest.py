import os
import glob
import argparse
import subprocess
from viofo_ocr import ViofoOCRExtractor

def process_directory(input_dir, bronze_base, dry_run=False):
    # Find all MP4 files
    video_files = glob.glob(os.path.join(input_dir, "**", "*.mp4"), recursive=True)
    video_files += glob.glob(os.path.join(input_dir, "**", "*.MP4"), recursive=True)
    video_files = sorted(list(set(video_files))) # dedupe and sort
    
    print(f"Found {len(video_files)} videos in {input_dir}")
    
    for video_path in video_files:
        filename = os.path.basename(video_path)
        base_name = os.path.splitext(filename)[0]
        
        # Define output paths
        frames_dir = os.path.join(bronze_base, "frames", base_name)
        telemetry_dir = os.path.join(bronze_base, "telemetry")
        telemetry_file = os.path.join(telemetry_dir, f"{base_name}.csv")
        
        # Check if already processed (simple check: if CSV exists)
        if os.path.exists(telemetry_file):
            print(f"Skipping {filename}, already processed: {telemetry_file}")
            continue
            
        print(f"Processing {filename}...")
        if dry_run:
            continue
            
        # Ensure dirs exist
        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(telemetry_dir, exist_ok=True)
        
        try:
            # Initialize Extractor
            extractor = ViofoOCRExtractor(
                video_path=video_path,
                sample_interval=1.0, # 1 sec interval
                debug=False,
                save_frames=True,
                frames_dir=frames_dir
            )
            
            # Extract
            data = extractor.process_video()
            
            # Save CSV
            if data:
                extractor.save_to_file(data, telemetry_file, 'csv')
                print(f"Completed {filename}")
            else:
                print(f"No data extracted for {filename}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

def run_dbt(project_dir):
    print("\nRunning dbt transformations (Bronze -> Silver -> Gold)...")
    try:
        subprocess.run(["dbt", "run", "--profiles-dir", "."], cwd=project_dir, check=True)
        print("dbt run completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"dbt run failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch ingest VIOFO videos to Data Lake")
    parser.add_argument("input_dir", help="Directory containing dashcam videos")
    parser.add_argument("--dry-run", action="store_true", help="List files without processing")
    
    args = parser.parse_args()
    
    # Hardcoded project paths relative to this script
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    BRONZE_BASE = os.path.join(PROJECT_ROOT, "datalake", "bronze")
    DBT_DIR = os.path.join(SCRIPT_DIR, "dbt_project")
    
    process_directory(args.input_dir, BRONZE_BASE, args.dry_run)
    
    if not args.dry_run:
        run_dbt(DBT_DIR)
