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
- Order preserved: output[i].video_id == input[i].video_id and
  output[i].window_start == input[i].window_start for all i.
  Violations raise ValueError with "order" in the message.
"""
from abc import ABC, abstractmethod

from core.traffic_analysis.domain.model import TrafficWindow, AnomalyScore


class AnomalyDetectorPort(ABC):
    """
    Port: scores a batch of TrafficWindow value objects for anomalous behavior
    and returns a corresponding list of AnomalyScore value objects.

    Concrete adapters: IsolationForestAdapter (scikit-learn, local / Lambda-friendly).
    The application layer must never import scikit-learn or any ML library directly.

    Contract (enforced by this base class — not merely documented):
    - len(output) == len(input): one score per window, no drops, no duplicates.
    - Empty input must return an empty list without raising.
    - Each AnomalyScore must carry the contamination parameter used during scoring.
    - Order preserved: output[i] must correspond to input[i] by (video_id, window_start).
      Any adapter that returns scores in a different order than the input windows will
      cause detect_anomalies() to raise ValueError before the result is returned.

    Implementation note — Template Method pattern:
    Subclasses must implement `_detect_anomalies()`, NOT override `detect_anomalies()`.
    The public `detect_anomalies()` method is a concrete template that calls the
    subclass hook and then enforces all port contracts before returning. This ensures
    no adapter can silently violate a contract.
    """

    @abstractmethod
    def _detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        """
        Protected hook: subclasses implement their scoring logic here.

        Args:
            windows: non-empty list of TrafficWindow value objects. The base class
                     has already handled the empty-list case before calling this hook.

        Returns:
            A list of AnomalyScore objects. The base class will validate that the
            returned list satisfies all port contracts (cardinality, ordering).
        """
        ...

    def detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        """
        Score a batch of TrafficWindow objects for anomalous traffic behavior.

        This is a concrete template method. It delegates scoring to `_detect_anomalies`
        (implemented by each adapter subclass) and then enforces all port contracts on
        the result before returning.

        Args:
            windows: list of TrafficWindow value objects from the Gold Layer.
                     May be empty — an empty list returns immediately without calling
                     the subclass hook.

        Returns:
            A list of AnomalyScore objects in the same order as the input windows.
            Guaranteed: len(output) == len(input) and output[i] corresponds to input[i]
            by (video_id, window_start).

        Raises:
            ValueError: if the adapter's output violates any of the following contracts:
                - len(output) != len(input)
                - output[i].video_id != input[i].video_id for any i
                - output[i].window_start != input[i].window_start for any i
                All order-violation messages contain the word "order".
        """
        if not windows:
            return []

        scores = self._detect_anomalies(windows)

        # --- Contract: cardinality ---
        if len(scores) != len(windows):
            raise ValueError(
                f"AnomalyDetectorPort contract violated: "
                f"expected {len(windows)} scores (one per window), "
                f"got {len(scores)}. "
                f"Adapter must not drop or duplicate windows."
            )

        # --- Contract: order preservation ---
        for i, (window, score) in enumerate(zip(windows, scores)):
            if score.video_id != window.video_id:
                raise ValueError(
                    f"AnomalyDetectorPort order contract violated at position {i}: "
                    f"expected video_id={window.video_id!r}, "
                    f"got {score.video_id!r}. "
                    f"Adapter must return scores in the same order as the input windows."
                )
            if score.window_start != window.window_start:
                raise ValueError(
                    f"AnomalyDetectorPort order contract violated at position {i}: "
                    f"expected window_start={window.window_start!r}, "
                    f"got {score.window_start!r}. "
                    f"Adapter must return scores in the same order as the input windows."
                )

        return scores
