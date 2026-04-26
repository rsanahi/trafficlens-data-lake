"""
Infrastructure Layer — IsolationForestAdapter

Concrete implementation of AnomalyDetectorPort using scikit-learn's IsolationForest.

Canonical location: core/traffic_analysis/adapters/isolation_forest_adapter.py

This class must NEVER be imported by the application or domain layers.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from core.traffic_analysis.domain.ports.i_traffic_analysis_ports import AnomalyDetectorPort
from core.traffic_analysis.domain.model import TrafficWindow, AnomalyScore

# Default anomaly threshold: scores below this value are classified as anomalies.
ANOMALY_THRESHOLD = -0.1


class IsolationForestAdapter(AnomalyDetectorPort):
    """
    Adapts scikit-learn's IsolationForest to the AnomalyDetectorPort interface.

    The adapter fits and scores the model in a single detect_anomalies() call
    (transductive / batch mode). This is appropriate for:
    - Post-trip analysis of a full video's windows.
    - Daily batch jobs over a day's worth of dashcam footage.

    Args:
        contamination: expected proportion of anomalies in the dataset (0 < x < 0.5).
                       Default: 0.05 (5%). Stored on every AnomalyScore for traceability.
        random_state:  seed for reproducible results. Default: 42.
        threshold:     anomaly_score below this value is classified as is_anomaly=True.
                       Default: -0.1 (sklearn decision_function convention).
    """

    def __init__(
        self,
        contamination: float = 0.05,
        random_state: int = 42,
        threshold: float = ANOMALY_THRESHOLD,
    ) -> None:
        self._contamination = contamination
        self._random_state = random_state
        self._threshold = threshold

    def _detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        feature_matrix = np.array(
            [
                [w.avg_speed_kmh, w.avg_delta_speed, w.avg_total_vehicles]
                for w in windows
            ],
            dtype=np.float64,
        )

        model = IsolationForest(
            contamination=self._contamination,
            random_state=self._random_state,
        )
        model.fit(feature_matrix)

        raw_scores: np.ndarray = model.decision_function(feature_matrix)

        return [
            AnomalyScore(
                video_id=w.video_id,
                window_start=w.window_start,
                anomaly_score=float(score),
                contamination=self._contamination,
            )
            for w, score in zip(windows, raw_scores)
        ]
