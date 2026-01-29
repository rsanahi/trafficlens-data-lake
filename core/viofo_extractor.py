import subprocess
import json
import sys
import os

import shutil

class ViofoMetadataExtractor:
    """
    Extracts GPS and sensor metadata from VIOFO dashcam MP4 files.
    Tries ExifTool first for embedded metadata.
    If full track is missing, suggests FFmpeg diagnosis.
    """

    def __init__(self, file_path, debug=False):
        self.file_path = file_path
        self.debug = debug
        self.has_ffmpeg = shutil.which('ffmpeg') is not None
        self.has_ffprobe = shutil.which('ffprobe') is not None

    def diagnose_streams(self):
        """
        Uses ffprobe to list streams and find potential data/subtitle tracks.
        """
        if not self.has_ffprobe:
            print("DEBUG: ffprobe not found, skipping stream diagnosis.")
            return

        print("DEBUG: Running ffprobe to inspect streams...")
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'stream=index,codec_type,codec_name,tags', 
            '-of', 'json', 
            self.file_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            for stream in info.get('streams', []):
                print(f"DEBUG: Stream {stream['index']}: {stream.get('codec_type')} ({stream.get('codec_name')})")
                if 'tags' in stream:
                    print(f"       Tags: {stream['tags']}")
                    
        except Exception as e:
            print(f"DEBUG: Error running ffprobe: {e}")

    def extract_metadata(self):
        """
        Runs exiftool to extract embedded GPS metadata.
        Yields: dict with timestamp, lat, lon, speed_kmh
        """
        # Run stream diagnosis first if in debug mode
        if self.debug:
            self.diagnose_streams()

        metadata = []
        
        # Command: exiftool -ee3 -n -j <file>
        # -ee3: Extract embedded data (most robust mode for video tracks)
        # -n:  Output numeric values (easier for parsing)
        # -j:  Output in JSON format
        cmd = ['exiftool', '-ee3', '-n', '-j', self.file_path]
        
        if self.debug:
            print(f"DEBUG: Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            if self.debug:
                print(f"DEBUG: ExifTool returned {len(data)} records.")
                # Print a sample of the structure to understand what we are getting
                if len(data) > 0:
                    print(f"DEBUG: Keys in first record: {list(data[0].keys())}")
                if len(data) > 1:
                     print(f"DEBUG: Keys in second record (potential sample): {list(data[1].keys())}")

            # ExifTool with -ee returns a list of dicts. 
            # Depending on the file structure, it might return:
            # 1. Many dicts, each with one GPS point (common in TS or some MP4)
            # 2. One or few dicts, containing LISTS of GPS points (e.g. GPSLatitude: [1.1, 1.2...])
            
            for i, entry in enumerate(data):
                # DEBUG: Trace entries that might have partial GPS data
                if self.debug:
                     has_lat = 'GPSLatitude' in entry
                     has_lon = 'GPSLongitude' in entry
                     if has_lat or has_lon:
                         print(f"DEBUG: Entry {i} has GPS data. Lat: {has_lat}, Lon: {has_lon}. Keys: {list(entry.keys())}")
                # Case 2: Arrays of data (common in some dashcams when -ee is used)
                if isinstance(entry.get('GPSLatitude'), list) and isinstance(entry.get('GPSLongitude'), list):
                    lats = entry['GPSLatitude']
                    lons = entry['GPSLongitude']
                    
                    # Timestamps might be a list or single start time. 
                    # If list, zip it. If not, we might lack per-sample time unless we calculate it.
                    # Usually Exiftool gives GPSDateTime as a list too if lats are a list.
                    times = entry.get('GPSDateTime', [])
                    if not isinstance(times, list):
                         # Fallback to SampleTime if available, or just repeat? 
                         # For now, handle if it IS a list
                         times = [times] * len(lats) 
                         
                    speeds = entry.get('GPSSpeed', [])
                    if not isinstance(speeds, list):
                        speeds = [0] * len(lats)

                    # Zip and append
                    # We use the length of lats as the source of truth
                    for i in range(len(lats)):
                        t = times[i] if i < len(times) else ""
                        s = speeds[i] if i < len(speeds) else 0
                        
                        metadata.append({
                            "timestamp": t,
                            "latitude": lats[i],
                            "longitude": lons[i],
                            "speed_kmh": s
                        })

                # Case 1: Single points per entry
                elif 'GPSLatitude' in entry and 'GPSLongitude' in entry:
                    # Normalize keys
                    record = {
                        "timestamp": entry.get('GPSDateTime', entry.get('DateTimeOriginal', '')),
                        "latitude": entry.get('GPSLatitude'),
                        "longitude": entry.get('GPSLongitude'),
                        "speed_kmh": entry.get('GPSSpeed', 0)
                    }
                    metadata.append(record)
                    
        except subprocess.CalledProcessError as e:
            print(f"Error running exiftool: {e.stderr}")
        except FileNotFoundError:
            print("Error: 'exiftool' not found. Please install it (brew install exiftool).")
        except json.JSONDecodeError:
            print("Error: Could not decode ExifTool output.")
            
        return metadata

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract VIOFO Dashcam Metadata using ExifTool")
    parser.add_argument("video_path", help="Path to the MP4 video file")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()

    video_path = args.video_path
    
    if not os.path.exists(video_path):
        print(f"Archivo no encontrado: {video_path}")
        sys.exit(1)

    print(f"Procesando {video_path}...")
    extractor = ViofoMetadataExtractor(video_path, debug=args.debug)
    data = extractor.extract_metadata()
    
    print(f"Se encontraron {len(data)} puntos de datos GPS.")
    if data:
        print("Ejemplo de primeros 3 registros:")
        for d in data[:3]:
            print(d)
