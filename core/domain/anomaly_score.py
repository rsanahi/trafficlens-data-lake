"""
Anomaly Score — Value Object

Carries the result of running the AnomalyDetectorPort on a single TrafficWindow.

Ubiquitous Language:
- video_id:       mirrors the source TrafficWindow.video_id for traceability.
- window_start:   mirrors the source TrafficWindow.window_start for traceability.
- anomaly_score:  raw Isolation Forest score. Negative values indicate anomalies.
                  Range is roughly (-1, 0) for anomalies and (0, 1) for normal.
- is_anomaly:     boolean classification derived by applying threshold (score < -0.1).
- contamination:  the contamination parameter used when training the detector.
                  Stored here to make experiments reproducible and traceable.

Invariant: frozen (immutable) — produced by the detector, never modified downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AnomalyScore:
    """Value Object: result of anomaly detection on a single TrafficWindow."""

    video_id: str
    window_start: datetime
    anomaly_score: float       # Raw IF score — negative = more anomalous
    is_anomaly: bool           # True if anomaly_score < -0.1 (default threshold)
    contamination: float       # Contamination parameter used by the detector
