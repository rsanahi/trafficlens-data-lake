"""
Infrastructure Layer — IsolationForestAdapter

Concrete implementation of AnomalyDetectorPort using scikit-learn's IsolationForest.

Design decisions:
- Fits the model on the entire batch passed to detect_anomalies(). This is a
  transductive (batch) approach: the model is trained and scored on the same
  windows. Suitable for offline anomaly detection over a full trip or day's data.
- Feature matrix: [avg_speed_kmh, avg_delta_speed, avg_total_vehicles] — three
  signals derived from the fct_traffic_windows Gold Layer.
- Threshold: anomaly_score < -0.1 → is_anomaly=True. This mirrors scikit-learn's
  decision_function convention where negative scores are anomalies.
- contamination=0.05: assumes roughly 5% of windows in a normal trip are anomalous.
  This parameter is stored on every AnomalyScore for experiment traceability.

Lambda-friendliness:
- scikit-learn + numpy are the only external dependencies.
- The fitted model is ephemeral (not persisted). For persistent models, serialize
  with joblib or pickle — both remain well within the 512MB Lambda limit for
  typical traffic datasets.

This class must NEVER be imported by the application or domain layers.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from core.domain.ports import AnomalyDetectorPort
from core.domain.traffic_window import TrafficWindow
from core.domain.anomaly_score import AnomalyScore

# Default anomaly threshold: scores below this value are classified as anomalies.
# Consistent with IsolationForest's decision_function convention.
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

    def detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        """
        Fit an IsolationForest on the batch, score each window, and return AnomalyScore
        objects in the same order as the input.

        Args:
            windows: list of TrafficWindow value objects from the Gold Layer.
                     An empty list returns an empty list without error.

        Returns:
            A list of AnomalyScore objects, one per input window, in input order.
        """
        if not windows:
            return []

        # Build feature matrix: shape (n_windows, 3)
        feature_matrix = np.array(
            [
                [w.avg_speed_kmh, w.avg_delta_speed, w.avg_total_vehicles]
                for w in windows
            ],
            dtype=np.float64,
        )

        # Fit and score in one pass (transductive batch)
        model = IsolationForest(
            contamination=self._contamination,
            random_state=self._random_state,
        )
        model.fit(feature_matrix)

        # decision_function returns anomaly scores:
        # negative values → anomalous, positive values → normal
        raw_scores: np.ndarray = model.decision_function(feature_matrix)

        return [
            AnomalyScore(
                video_id=w.video_id,
                window_start=w.window_start,
                anomaly_score=float(score),
                is_anomaly=float(score) < self._threshold,
                contamination=self._contamination,
            )
            for w, score in zip(windows, raw_scores)
        ]
