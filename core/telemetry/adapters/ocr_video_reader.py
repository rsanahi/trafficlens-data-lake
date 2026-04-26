"""
Infrastructure adapter: implements VideoReaderPort using OpenCV + Tesseract OCR.
This class contains ALL external dependencies (cv2, pytesseract).
The Domain layer never imports from here.

Canonical location: core/telemetry/adapters/ocr_video_reader.py
"""
from __future__ import annotations

import os
import re
from typing import Optional

import cv2
import pytesseract

from core.telemetry.domain.ports.i_telemetry_ports import VideoReaderPort
from core.telemetry.domain.model import TelemetryRecord, VideoMetadata


class OcrVideoReader(VideoReaderPort):
    """Reads telemetry from VIOFO dashcam videos via OpenCV + Tesseract OCR."""

    # Regex patterns for VIOFO caption format
    _DATE_YMD = re.compile(r'(\d{4})[-/:](\d{2})[-/:](\d{2})')
    _DATE_DMY = re.compile(r'(\d{2})[-/:](\d{2})[-/:](\d{4})')
    _TIME = re.compile(r'(\d{2}):(\d{2}):(\d{2})')
    _SPEED = re.compile(r'(\d{1,3})(?:\s*)km/h', re.IGNORECASE)
    _LAT = re.compile(r'([NS])[:\s]*(\d+\.\d+)')
    _LON = re.compile(r'([EW])[:\s]*(\d+\.\d+)')

    def __init__(self, save_frames: bool = False, frames_base_dir: Optional[str] = None) -> None:
        self._save_frames = save_frames
        self._frames_base_dir = frames_base_dir

    def read_records(self, metadata: VideoMetadata) -> list[TelemetryRecord]:
        if not os.path.exists(metadata.path):
            return []

        cap = cv2.VideoCapture(metadata.path)
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        print(f"Video Info: {duration:.1f}s duration, {fps:.1f} FPS, {total_frames} frames.")
        print(f"Sampling every {metadata.sample_interval} seconds...")

        frames_dir = self._resolve_frames_dir(metadata.path)
        if self._save_frames and frames_dir:
            os.makedirs(frames_dir, exist_ok=True)
            print(f"Saving frames to: {frames_dir}")

        results: list[TelemetryRecord] = []
        skip_frames = max(1, int(fps * metadata.sample_interval))
        frame_idx = 0
        processed_count = 0

        while True:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            frame_filename = self._save_frame(frame, frame_idx, frames_dir) if (
                self._save_frames and frames_dir
            ) else ""

            record = self._extract_record(frame, frame_filename)
            if record:
                results.append(record)

            frame_idx += skip_frames
            processed_count += 1
            if processed_count % 10 == 0:
                print(f"Processed {processed_count} samples...", end='\r')

        cap.release()
        print(f"\nDone. Extracted {len(results)} valid records.")
        return results

    # --- Private helpers ---

    def _resolve_frames_dir(self, video_path: str) -> Optional[str]:
        if not self._save_frames or not self._frames_base_dir:
            return None
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        return os.path.join(self._frames_base_dir, base_name)

    def _save_frame(self, frame, frame_idx: int, frames_dir: str) -> str:
        frame_name = f"frame_{frame_idx:06d}.jpg"
        frame_path = os.path.join(frames_dir, frame_name)
        cv2.imwrite(frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return frame_name

    def _extract_record(self, frame, frame_filename: str) -> Optional[TelemetryRecord]:
        h, w = frame.shape[:2]
        roi = frame[h - int(h * 0.08):h, 0:w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        text = pytesseract.image_to_string(thresh, config='--psm 6').strip()
        return self._parse_text(text, frame_filename)

    def _parse_text(self, text: str, frame_filename: str) -> Optional[TelemetryRecord]:
        timestamp = self._parse_timestamp(text)
        speed = self._parse_speed(text)
        lat = self._parse_latitude(text)
        lon = self._parse_longitude(text)

        if timestamp or lat is not None or lon is not None or speed > 0:
            return TelemetryRecord(
                timestamp=timestamp,
                speed_kmh=speed,
                latitude=lat,
                longitude=lon,
                raw_text=text,
                frame_filename=frame_filename or None,
            )
        return None

    def _parse_timestamp(self, text: str) -> Optional[str]:
        d = self._DATE_YMD.search(text)
        if d:
            year, month, day = d.group(1), d.group(2), d.group(3)
        else:
            d = self._DATE_DMY.search(text)
            if d:
                day, month, year = d.group(1), d.group(2), d.group(3)
            else:
                return None

        t = self._TIME.search(text)
        if not t:
            return None
        return f"{year}-{month}-{day}T{t.group(1)}:{t.group(2)}:{t.group(3)}"

    def _parse_speed(self, text: str) -> int:
        m = self._SPEED.search(text)
        return int(m.group(1)) if m else 0

    def _parse_latitude(self, text: str) -> Optional[float]:
        m = self._LAT.search(text)
        if not m:
            return None
        val = float(m.group(2))
        return -val if m.group(1) == 'S' else val

    def _parse_longitude(self, text: str) -> Optional[float]:
        m = self._LON.search(text)
        if not m:
            return None
        val = float(m.group(2))
        return -val if m.group(1) == 'W' else val
