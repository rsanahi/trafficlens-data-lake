"""
Traffic Analysis — Domain Ports

Bounded context: anomaly detection over aggregated dashcam telemetry windows.

These ports define the outbound interfaces that the Traffic Analysis bounded
context requires from the infrastructure layer. The application layer depends
only on these abstractions — never on scikit-learn, numpy, or any ML library.

Ubiquitous Language:
- TrafficWindow:       pre-aggregated 10-second telemetry window from fct_traffic_windows.
- AnomalyScore:        anomaly detection result for a single TrafficWindow.
- AnomalyDetectorPort: scores a batch of TrafficWindows → list[AnomalyScore].

Contract:
- len(output) == len(input): one score per window, no drops, no duplicates.
- Empty input must return an empty list without raising.
- Each AnomalyScore must carry the contamination parameter used during scoring.
"""
from abc import ABC, abstractmethod

from core.traffic_analysis.domain.model import TrafficWindow, AnomalyScore


class AnomalyDetectorPort(ABC):
    """
    Port: scores a batch of TrafficWindow value objects for anomalous behavior
    and returns a corresponding list of AnomalyScore value objects.

    Concrete adapters: IsolationForestAdapter (scikit-learn, local / Lambda-friendly).
    The application layer must never import scikit-learn or any ML library directly.

    Contract:
    - len(output) == len(input): one score per window, no drops, no duplicates.
    - Empty input must return an empty list without raising.
    - Each AnomalyScore must carry the contamination parameter used during scoring.
    """

    @abstractmethod
    def detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        """
        Score a batch of TrafficWindow objects for anomalous traffic behavior.

        Args:
            windows: list of TrafficWindow value objects from the Gold Layer.
                     May be empty — adapters must handle this gracefully.

        Returns:
            A list of AnomalyScore objects in the same order as the input windows.
        """
        ...
