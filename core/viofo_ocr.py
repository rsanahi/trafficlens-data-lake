import cv2
import pytesseract
import re
import os
import sys
from datetime import datetime, timedelta

class ViofoOCRExtractor:
    """
    Extracts metadata (Time, Speed, GPS) from VIOFO dashcam videos 
    by reading the burned-in caption text using OCR.
    """

    def __init__(self, video_path, sample_interval=1.0, debug=False, save_frames=False, frames_dir=None):
        """
        Args:
            video_path: Path to the video file.
            sample_interval: Process one frame every X seconds (default 1.0).
            debug: Create debug images of cropped areas.
            save_frames: Whether to save the full frame as an image (Bronze Layer).
            frames_dir: Directory to save frames to.
        """
        self.video_path = video_path
        self.sample_interval = sample_interval
        self.debug = debug
        self.save_frames = save_frames
        self.frames_dir = frames_dir
        
        # Regex for VIOFO caption formats
        # Observed: "012KM/H N:9.2985 W:75.3856 VIOFO A229 Pro HDR 28-01-2026 07:07:07"
        
        # Date: Handle YYYY/MM/DD and DD-MM-YYYY
        self.date_pattern_ymd = re.compile(r'(\d{4})[-/:](\d{2})[-/:](\d{2})')
        self.date_pattern_dmy = re.compile(r'(\d{2})[-/:](\d{2})[-/:](\d{4})')
        
        self.time_pattern = re.compile(r'(\d{2}):(\d{2}):(\d{2})')
        
        # Speed: "123KM/H" or "123 KM/H". Common OCR error O/0 handled by parsing logic best effort.
        self.speed_pattern = re.compile(r'(\d{1,3})(?:\s*)km/h', re.IGNORECASE)
        
        # Coordinates: N:9.2985 or N 9.2985
        self.lat_pattern = re.compile(r'([NS])[:\s]*(\d+\.\d+)')
        self.lon_pattern = re.compile(r'([EW])[:\s]*(\d+\.\d+)')

    def process_video(self):
        if not os.path.exists(self.video_path):
            print(f"Error: File not found {self.video_path}")
            return []

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print("Error: Could not open video.")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        print(f"Video Info: {duration:.1f}s duration, {fps:.1f} FPS, {total_frames} frames.")
        print(f"Sampling every {self.sample_interval} seconds...")

        results = []
        skip_frames = int(fps * self.sample_interval)
        if skip_frames < 1: skip_frames = 1

        frame_idx = 0
        processed_count = 0
        
        # Prepare frame output directory if needed
        if self.save_frames and self.frames_dir:
             if not os.path.exists(self.frames_dir):
                 os.makedirs(self.frames_dir)
             print(f"Saving frames to: {self.frames_dir}")
        
        while True:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            
            # Save frame if requested (Bronze Layer Artifact)
            frame_filename = ""
            if self.save_frames and self.frames_dir:
                # Use frame index as temporary name, we can rename to timestamp later if extraction succeeds
                # Or just use frame index which is unique
                frame_name = f"frame_{frame_idx:06d}.jpg"
                frame_path = os.path.join(self.frames_dir, frame_name)
                # Quality 80 to save space
                cv2.imwrite(frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                frame_filename = frame_name

            # Crop the bottom 8% of the image (tightened based on user feedback)
            h, w = frame.shape[:2]
            crop_h = int(h * 0.08) # Bottom 8%
            roi = frame[h - crop_h : h, 0 : w]
            
            # Preprocess for OCR
            # 1. Grayscale
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # 2. Thresholding (white text on dark background)
            # Binary inverse might work better if it's white text on black.
            # But standard thresholding often works for white text.
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

            if self.debug and processed_count == 0:
                # Ensure directory exists
                debug_dir = "data-samples"
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)
                    
                cv2.imwrite(f"{debug_dir}/debug_crop_raw.jpg", roi)
                cv2.imwrite(f"{debug_dir}/debug_crop_thresh.jpg", thresh)
                print(f"DEBUG: Saved crop images to {debug_dir}/ for inspection.")

            # Run OCR
            # --psm 7: Treat the image as a single text line (good for captions)
            # --psm 6: Assume a single uniform block of text
            text = pytesseract.image_to_string(thresh, config='--psm 6').strip()
            
            if self.debug:
               print(f"Frame {frame_idx}: OCR Raw -> '{text}'")

            data = self._parse_text(text)
            if data:
                if self.save_frames:
                    data['frame_filename'] = frame_filename
                    
                results.append(data)
                if self.debug: 
                    print(f"  -> Parsed: {data}")

            frame_idx += skip_frames
            processed_count += 1
            if processed_count % 10 == 0:
                print(f"Processed {processed_count} samples...", end='\r')

        cap.release()
        print(f"\nDone. Extracted {len(results)} valid records.")
        return results

    def _parse_text(self, text):
        """Attempts to extract structured data from the OCR line."""
        # Normalize simple OCR errors: 'O' -> '0' specifically for numbers if needed, 
        # but regex usually ignores 'O' and finds the digits.
        
        # 1. Extract Date/Time
        # Try YYYY-MM-DD
        d_match = self.date_pattern_ymd.search(text)
        year, month, day = None, None, None
        
        if d_match:
            year, month, day = d_match.group(1), d_match.group(2), d_match.group(3)
        else:
            # Try DD-MM-YYYY
            d_match = self.date_pattern_dmy.search(text)
            if d_match:
                day, month, year = d_match.group(1), d_match.group(2), d_match.group(3)

        t_match = self.time_pattern.search(text)
        
        timestamp = None
        if year and month and day and t_match:
            try:
                dt_str = f"{year}-{month}-{day}T{t_match.group(1)}:{t_match.group(2)}:{t_match.group(3)}"
                timestamp = dt_str
            except:
                pass
        
        # 2. Extract Speed
        speed = 0
        s_match = self.speed_pattern.search(text)
        if s_match:
            try:
                speed = int(s_match.group(1))
            except:
                pass

        # 3. Extract Coordinates
        # Looking for pairs like N 12.345... E 123.456...
        lat_match = self.lat_pattern.search(text)
        lon_match = self.lon_pattern.search(text)
        
        lat = None
        lon = None
        
        if lat_match:
            val = float(lat_match.group(2))
            if lat_match.group(1) == 'S': val = -val
            lat = val
            
        if lon_match:
            val = float(lon_match.group(2))
            if lon_match.group(1) == 'W': val = -val
            lon = val

        # Only return if we have at least partial useful info
        if timestamp or (lat is not None and lon is not None) or speed > 0:
            return {
                "timestamp": timestamp,
                "speed_kmh": speed,
                "latitude": lat,
                "longitude": lon,
                "raw_text": text
            }
        return None

    def save_to_file(self, data, output_path, output_format='csv'):
        """
        Saves the extracted data to a file (CSV or JSON).
        Designed to be replaced or extended with S3 upload logic later.
        """
        if not data:
            print("No data to save.")
            return

        print(f"Saving {len(data)} records to {output_path}...")
        
        try:
            if output_format.lower() == 'json':
                import json
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            else:
                import csv
                keys = data[0].keys()
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(data)
            print(f"Successfully saved to {output_path}")
        except Exception as e:
            print(f"Error saving file: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VIOFO OCR Metadata Extractor")
    parser.add_argument("video_path", help="Path to video file")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    parser.add_argument("--debug", action="store_true", help="Save debug images/logs")
    parser.add_argument("--output", help="Output file path (default: video_name.csv)")
    parser.add_argument("--format", choices=['csv', 'json'], default='csv', help="Output format")
    parser.add_argument("--save-frames", action="store_true", help="Extract and save frames (Bronze Layer)")
    
    args = parser.parse_args()
    
    # Logic for Bronze Layer structure if saving frames
    frames_out_dir = None
    if args.save_frames:
         base_name = os.path.splitext(os.path.basename(args.video_path))[0]
         # datalake/bronze/frames/{video_name}/
         frames_out_dir = os.path.join("datalake", "bronze", "frames", base_name)
    
    extractor = ViofoOCRExtractor(
        args.video_path, 
        sample_interval=args.interval, 
        debug=args.debug,
        save_frames=args.save_frames,
        frames_dir=frames_out_dir
    )
    data = extractor.process_video()
    
    if data:
        # Determine output path if not provided
        if not args.output:
            base_name = os.path.splitext(os.path.basename(args.video_path))[0]
            extension = args.format
            # Default to Bronze Telemetry folder if keeping with Data Lake structure
            # datalake/bronze/telemetry/{video_name}.csv
            output_dir = os.path.join("datalake", "bronze", "telemetry")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            args.output = os.path.join(output_dir, f"{base_name}.{extension}")
            
        extractor.save_to_file(data, args.output, args.format)
    else:
        print("No data extracted.")
