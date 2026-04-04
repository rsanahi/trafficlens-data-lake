import os
import csv
import random
from pathlib import Path

def generate_mock_detections():
    frames_dir = Path("datalake/bronze/frames")
    detections_dir = Path("datalake/bronze/detections")
    
    if not frames_dir.exists():
        print(f"Frames directory {frames_dir} does not exist.")
        return
        
    detections_dir.mkdir(parents=True, exist_ok=True)
    
    generated_count = 0
    
    for video_dir in frames_dir.iterdir():
        if video_dir.is_dir():
            video_name = video_dir.name
            output_csv_path = detections_dir / f"{video_name}.csv"
            
            with open(output_csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["frame_filename", "car_count", "motorcycle_count"])
                
                for frame_file in video_dir.glob("*.jpg"):
                    # Simulate some ML model outputs
                    # Most frames have cars, some have motorcycles
                    car_count = random.choices([0, 1, 2, 3, 4, 5], weights=[10, 30, 30, 15, 10, 5])[0]
                    motorcycle_count = random.choices([0, 1, 2], weights=[70, 20, 10])[0]
                    
                    writer.writerow([frame_file.name, car_count, motorcycle_count])
            
            print(f"Generated mock detections for {video_name}")
            generated_count += 1
            
    print(f"Total mock detection sets generated: {generated_count}")

if __name__ == "__main__":
    generate_mock_detections()
