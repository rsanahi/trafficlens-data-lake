"""
Application Layer — DetectTrafficAnomalies Use Case

Orchestrates the traffic anomaly detection pipeline:
    list[TrafficWindow]  →  AnomalyDetectorPort  →  list[AnomalyScore]

Clean Architecture constraints (non-negotiable):
- ZERO infrastructure imports. No scikit-learn, no numpy, no pandas.
- All ML behaviour is injected via AnomalyDetectorPort at construction time.
- Business rules (input validation, delegation) live here, not in adapters.
- The use case is stateless — it holds only the injected port reference.
"""
from core.domain.ports import AnomalyDetectorPort
from core.domain.traffic_window import TrafficWindow
from core.domain.anomaly_score import AnomalyScore


class DetectTrafficAnomalies:
    """
    Application Service: scores a batch of 10-second traffic windows for anomalies.

    Typical caller flow:
        1. Load TrafficWindow objects from the fct_traffic_windows Gold Layer Parquet.
        2. Instantiate this use case with an IsolationForestAdapter (or any other
           AnomalyDetectorPort implementation).
        3. Call detect(windows) — get back one AnomalyScore per window.

    The use case is deliberately thin: its only responsibility is to delegate to the
    port and return the result. No scoring logic lives here.
    """

    def __init__(self, detector: AnomalyDetectorPort) -> None:
        """
        Args:
            detector: any concrete implementation of AnomalyDetectorPort.
                      In production: IsolationForestAdapter.
                      In tests: InMemoryAnomalyDetector (deterministic fake).
        """
        self._detector = detector

    def detect(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        """
        Score a batch of TrafficWindow objects for anomalous traffic behaviour.

        Args:
            windows: list of pre-aggregated 10-second windows from the Gold Layer.
                     An empty list is valid — returns an empty list immediately.

        Returns:
            A list of AnomalyScore objects in the same order as the input windows.
            len(output) == len(input) is guaranteed by the AnomalyDetectorPort contract.
        """
        if not windows:
            return []

        return self._detector.detect_anomalies(windows)
