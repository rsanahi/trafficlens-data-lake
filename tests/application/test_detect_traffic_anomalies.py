"""
Use Case Tests — DetectTrafficAnomalies

The DetectTrafficAnomalies use case delegates all scoring to AnomalyDetectorPort.
These tests verify the use case's orchestration contract: input routing, output
cardinality, identity preservation, and infrastructure isolation.

Test double design:
    InMemoryAnomalyDetector is a *pure Fake* — it returns only the AnomalyScore
    objects pre-configured by the test. It contains zero business logic, zero
    threshold comparisons, and zero knowledge of what constitutes an anomaly.
    This keeps each test self-contained and immune to any future threshold drift
    in the real IsolationForestAdapter.

Use case flow under test:
    list[TrafficWindow] -> AnomalyDetectorPort -> list[AnomalyScore]

Scenarios covered:
- frenazo_brusco:        sudden braking event          → is_anomaly=True
- flujo_normal:          typical cruise traffic        → is_anomaly=False
- congestion_anomala:    unusual vehicle density spike → is_anomaly=True
- velocidad_cero_normal: stopped vehicle at red light  → is_anomaly=False
"""
import pytest
from datetime import datetime, timezone

from core.domain.traffic_window import TrafficWindow
from core.domain.anomaly_score import AnomalyScore
from core.domain.ports import AnomalyDetectorPort
from core.application.detect_traffic_anomalies import DetectTrafficAnomalies


# ---------------------------------------------------------------------------
# In-Memory Fake — pure stub, zero domain logic
# ---------------------------------------------------------------------------

class InMemoryAnomalyDetector(AnomalyDetectorPort):
    """
    Pure Fake implementation of AnomalyDetectorPort for use-case tests.

    The Fake is completely controlled by the test: callers supply a list of
    AnomalyScore objects at construction time (or via set_results) and the
    Fake returns them verbatim when detect_anomalies() is called.

    There are NO threshold comparisons, NO business rules, and NO knowledge
    of what constitutes an anomaly. Classification decisions belong to the
    domain and infrastructure layers — not to test doubles.

    Usage:
        detector = InMemoryAnomalyDetector(results=[score_a, score_b])
        use_case = DetectTrafficAnomalies(detector=detector)
        scores = use_case.detect([window_a, window_b])
    """

    # Exposed as a class constant so tests that assert on contamination values
    # have a single source of truth without hard-coding magic numbers.
    CONTAMINATION = 0.05

    def __init__(self, results: list[AnomalyScore] | None = None) -> None:
        self._results: list[AnomalyScore] = results if results is not None else []

    def set_results(self, results: list[AnomalyScore]) -> None:
        """Replace the pre-configured results. Useful for multi-step test setups."""
        self._results = results

    def detect_anomalies(self, windows: list[TrafficWindow]) -> list[AnomalyScore]:
        return list(self._results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)


def _window(
    video_id: str = "trip_001",
    offset_seconds: int = 0,
    avg_speed_kmh: float = 40.0,
    avg_delta_speed: float = 2.0,
    avg_total_vehicles: float = 5.0,
    frame_count: int = 10,
) -> TrafficWindow:
    """Build a TrafficWindow with sensible defaults."""
    return TrafficWindow(
        video_id=video_id,
        window_start=datetime(
            2024, 1, 15, 8, 0, offset_seconds, tzinfo=timezone.utc
        ),
        avg_speed_kmh=avg_speed_kmh,
        avg_delta_speed=avg_delta_speed,
        avg_total_vehicles=avg_total_vehicles,
        frame_count=frame_count,
    )


def _score(
    video_id: str = "trip_001",
    offset_seconds: int = 0,
    is_anomaly: bool = False,
    anomaly_score: float = 0.1,
    contamination: float = InMemoryAnomalyDetector.CONTAMINATION,
) -> AnomalyScore:
    """Build an AnomalyScore with sensible defaults."""
    return AnomalyScore(
        video_id=video_id,
        window_start=datetime(
            2024, 1, 15, 8, 0, offset_seconds, tzinfo=timezone.utc
        ),
        anomaly_score=anomaly_score,
        is_anomaly=is_anomaly,
        contamination=contamination,
    )


# ---------------------------------------------------------------------------
# DetectTrafficAnomalies Use Case Tests
# ---------------------------------------------------------------------------

class TestDetectTrafficAnomalies:

    # --- Happy path: four canonical traffic scenarios ---

    def test_frenazo_brusco_is_detected_as_anomaly(self):
        """
        Scenario: frenazo_brusco
        A window with delta_speed=40.0 represents a sudden braking event.
        The Fake is pre-configured to return is_anomaly=True for this window.
        Expected: the use case passes through is_anomaly=True unchanged.
        """
        window = _window(
            video_id="trip_001",
            avg_speed_kmh=80.0,
            avg_delta_speed=40.0,
            avg_total_vehicles=5.0,
        )
        expected_score = _score(
            video_id="trip_001",
            is_anomaly=True,
            anomaly_score=-0.3,
        )
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert len(scores) == 1
        score = scores[0]
        assert score.video_id == "trip_001"
        assert score.is_anomaly is True
        assert score.anomaly_score < -0.1, (
            "A braking anomaly must produce a negative score below the -0.1 threshold"
        )

    def test_flujo_normal_is_not_detected_as_anomaly(self):
        """
        Scenario: flujo_normal
        A window with delta_speed=2.0 and 8 vehicles represents normal traffic flow.
        The Fake is pre-configured to return is_anomaly=False for this window.
        Expected: the use case passes through is_anomaly=False unchanged.
        """
        window = _window(
            video_id="trip_002",
            avg_speed_kmh=50.0,
            avg_delta_speed=2.0,
            avg_total_vehicles=8.0,
        )
        expected_score = _score(
            video_id="trip_002",
            is_anomaly=False,
            anomaly_score=0.1,
        )
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert len(scores) == 1
        score = scores[0]
        assert score.video_id == "trip_002"
        assert score.is_anomaly is False
        assert score.anomaly_score > -0.1, (
            "Normal flow must produce a score above the -0.1 anomaly threshold"
        )

    def test_congestion_anomala_is_detected_as_anomaly(self):
        """
        Scenario: congestion_anomala
        A window with 80 average vehicles represents an unusual density spike.
        The Fake is pre-configured to return is_anomaly=True for this window.
        Expected: the use case passes through is_anomaly=True unchanged.
        """
        window = _window(
            video_id="trip_003",
            avg_speed_kmh=15.0,
            avg_delta_speed=5.0,
            avg_total_vehicles=80.0,
        )
        expected_score = _score(
            video_id="trip_003",
            is_anomaly=True,
            anomaly_score=-0.3,
        )
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert len(scores) == 1
        score = scores[0]
        assert score.video_id == "trip_003"
        assert score.is_anomaly is True
        assert score.anomaly_score < -0.1

    def test_velocidad_cero_normal_is_not_detected_as_anomaly(self):
        """
        Scenario: velocidad_cero_normal
        A window with speed=0 and 0 vehicles represents a legitimate stopped vehicle
        (e.g., traffic light). The Fake is pre-configured to return is_anomaly=False.
        Expected: the use case passes through is_anomaly=False unchanged.
        """
        window = _window(
            video_id="trip_004",
            avg_speed_kmh=0.0,
            avg_delta_speed=0.0,
            avg_total_vehicles=0.0,
        )
        expected_score = _score(
            video_id="trip_004",
            is_anomaly=False,
            anomaly_score=0.1,
        )
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert len(scores) == 1
        score = scores[0]
        assert score.video_id == "trip_004"
        assert score.is_anomaly is False
        assert score.anomaly_score > -0.1

    # --- Output shape and cardinality ---

    def test_output_length_matches_input_length(self):
        """
        The use case must return exactly one AnomalyScore per TrafficWindow supplied.
        No windows must be dropped or duplicated.
        """
        windows = [
            _window(video_id="trip_001", offset_seconds=i * 10)
            for i in range(5)
        ]
        scores_preset = [
            _score(video_id="trip_001", offset_seconds=i * 10)
            for i in range(5)
        ]
        detector = InMemoryAnomalyDetector(results=scores_preset)
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect(windows)

        assert len(scores) == 5, (
            "One AnomalyScore must be emitted per TrafficWindow — no drops, no duplicates"
        )

    def test_output_preserves_video_id_and_window_start(self):
        """
        Each AnomalyScore must carry the same video_id and window_start as its
        corresponding TrafficWindow. Identity must not be lost during scoring.
        """
        windows = [
            _window(video_id="trip_A", offset_seconds=0),
            _window(video_id="trip_B", offset_seconds=10),
        ]
        scores_preset = [
            _score(video_id="trip_A", offset_seconds=0),
            _score(video_id="trip_B", offset_seconds=10),
        ]
        detector = InMemoryAnomalyDetector(results=scores_preset)
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect(windows)

        assert scores[0].video_id == "trip_A"
        assert scores[1].video_id == "trip_B"
        assert scores[0].window_start == windows[0].window_start
        assert scores[1].window_start == windows[1].window_start

    # --- Edge cases ---

    def test_empty_window_list_returns_empty_scores(self):
        """
        Calling the use case with an empty list must return an empty list — not
        raise an exception. Batch jobs may produce empty windows legitimately.
        """
        detector = InMemoryAnomalyDetector(results=[])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([])

        assert scores == []

    def test_single_window_returns_single_score(self):
        """Minimum viable batch: one window must produce exactly one score."""
        window = _window()
        expected_score = _score()
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert len(scores) == 1
        assert isinstance(scores[0], AnomalyScore)

    def test_mixed_batch_produces_correct_anomaly_flags(self):
        """
        A batch containing both normal and anomalous windows must produce the
        correct is_anomaly flag for each, in input order.
        The Fake is pre-configured with the expected classification for each window.
        """
        windows = [
            _window(video_id="trip_mix", offset_seconds=0,  avg_delta_speed=2.0,  avg_total_vehicles=8.0),
            _window(video_id="trip_mix", offset_seconds=10, avg_delta_speed=40.0, avg_total_vehicles=5.0),
            _window(video_id="trip_mix", offset_seconds=20, avg_delta_speed=5.0,  avg_total_vehicles=80.0),
            _window(video_id="trip_mix", offset_seconds=30, avg_delta_speed=0.0,  avg_total_vehicles=0.0),
        ]
        scores_preset = [
            _score(video_id="trip_mix", offset_seconds=0,  is_anomaly=False, anomaly_score=0.1),
            _score(video_id="trip_mix", offset_seconds=10, is_anomaly=True,  anomaly_score=-0.3),
            _score(video_id="trip_mix", offset_seconds=20, is_anomaly=True,  anomaly_score=-0.3),
            _score(video_id="trip_mix", offset_seconds=30, is_anomaly=False, anomaly_score=0.1),
        ]
        detector = InMemoryAnomalyDetector(results=scores_preset)
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect(windows)

        assert scores[0].is_anomaly is False, "Normal flow must not be flagged"
        assert scores[1].is_anomaly is True,  "Braking event must be flagged"
        assert scores[2].is_anomaly is True,  "Density spike must be flagged"
        assert scores[3].is_anomaly is False, "Stopped vehicle must not be flagged"

    def test_anomaly_score_carries_contamination_parameter(self):
        """
        Each AnomalyScore must carry the contamination parameter that was used
        by the detector. This enables experiment traceability.
        """
        window = _window()
        expected_score = _score(contamination=InMemoryAnomalyDetector.CONTAMINATION)
        detector = InMemoryAnomalyDetector(results=[expected_score])
        use_case = DetectTrafficAnomalies(detector=detector)

        scores = use_case.detect([window])

        assert scores[0].contamination == InMemoryAnomalyDetector.CONTAMINATION

    # --- Port isolation ---

    def test_use_case_does_not_import_sklearn(self):
        """
        The DetectTrafficAnomalies use case must not import scikit-learn.
        The application layer is infrastructure-agnostic.
        """
        import ast
        from pathlib import Path

        source_path = (
            Path(__file__).resolve().parents[2]
            / "core" / "application" / "detect_traffic_anomalies.py"
        )
        tree = ast.parse(source_path.read_text())

        sklearn_imports = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and any(
                (alias.name or "").startswith("sklearn")
                for alias in getattr(node, "names", [])
            )
            or isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("sklearn")
        ]

        assert not sklearn_imports, (
            "The application layer must never import scikit-learn directly. "
            "IsolationForest belongs in the infrastructure layer only."
        )


# ---------------------------------------------------------------------------
# TrafficWindow Invariant Tests
#
# Rule: invariants are proven through the use case, not by constructing domain
# objects in isolation. Each test builds an invalid TrafficWindow as part of
# the arrange phase, then calls use_case.detect() and expects ValueError.
# ---------------------------------------------------------------------------

class TestTrafficWindowInvariants:
    """
    Verify that TrafficWindow's domain invariants are enforced at construction
    time and that the violation surfaces as a ValueError when the use case
    attempts to consume an invalid window.

    One test per invariant. Each test follows the same pattern:
        1. Attempt to build a TrafficWindow that violates exactly one invariant.
        2. Wrap the construction + detect call in pytest.raises(ValueError).
        3. Assert nothing further — the raised exception IS the contract.
    """

    def _make_use_case(self) -> DetectTrafficAnomalies:
        """Return a use case wired with an empty-result fake detector."""
        return DetectTrafficAnomalies(detector=InMemoryAnomalyDetector(results=[]))

    # --- video_id ---

    def test_blank_video_id_raises_value_error(self):
        """
        Invariant: video_id must not be blank or whitespace-only.
        A window with video_id="" is meaningless — it cannot be traced to a source.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="video_id"):
            invalid_window = TrafficWindow(
                video_id="   ",
                window_start=BASE_TIME,
                avg_speed_kmh=40.0,
                avg_delta_speed=2.0,
                avg_total_vehicles=5.0,
                frame_count=10,
            )
            use_case.detect([invalid_window])

    # --- avg_speed_kmh ---

    def test_negative_avg_speed_raises_value_error(self):
        """
        Invariant: avg_speed_kmh >= 0.
        Physical speed is a magnitude — a negative value signals a data pipeline error.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="avg_speed_kmh"):
            invalid_window = TrafficWindow(
                video_id="trip_001",
                window_start=BASE_TIME,
                avg_speed_kmh=-1.0,
                avg_delta_speed=2.0,
                avg_total_vehicles=5.0,
                frame_count=10,
            )
            use_case.detect([invalid_window])

    # --- avg_delta_speed ---

    def test_negative_avg_delta_speed_raises_value_error(self):
        """
        Invariant: avg_delta_speed >= 0.
        avg_delta_speed is the mean *absolute* speed change — it is physically
        impossible for this to be negative.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="avg_delta_speed"):
            invalid_window = TrafficWindow(
                video_id="trip_001",
                window_start=BASE_TIME,
                avg_speed_kmh=40.0,
                avg_delta_speed=-0.1,
                avg_total_vehicles=5.0,
                frame_count=10,
            )
            use_case.detect([invalid_window])

    # --- avg_total_vehicles ---

    def test_negative_avg_total_vehicles_raises_value_error(self):
        """
        Invariant: avg_total_vehicles >= 0.
        A vehicle count cannot be negative — it signals a corrupted aggregation.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="avg_total_vehicles"):
            invalid_window = TrafficWindow(
                video_id="trip_001",
                window_start=BASE_TIME,
                avg_speed_kmh=40.0,
                avg_delta_speed=2.0,
                avg_total_vehicles=-1.0,
                frame_count=10,
            )
            use_case.detect([invalid_window])

    # --- frame_count ---

    def test_zero_frame_count_raises_value_error(self):
        """
        Invariant: frame_count >= 1.
        A window with no frames carries no telemetry and has no meaning in the domain.
        frame_count=0 indicates a broken aggregation in the dbt Gold Layer.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="frame_count"):
            invalid_window = TrafficWindow(
                video_id="trip_001",
                window_start=BASE_TIME,
                avg_speed_kmh=40.0,
                avg_delta_speed=2.0,
                avg_total_vehicles=5.0,
                frame_count=0,
            )
            use_case.detect([invalid_window])

    # --- window_start timezone-awareness ---

    def test_naive_window_start_raises_value_error(self):
        """
        Invariant: window_start must be timezone-aware.
        Naive datetimes are ambiguous when dashcam footage spans timezones or DST
        boundaries. The Gold Layer must always provide UTC-stamped windows.
        """
        use_case = self._make_use_case()

        with pytest.raises(ValueError, match="window_start"):
            invalid_window = TrafficWindow(
                video_id="trip_001",
                window_start=datetime(2024, 1, 15, 8, 0, 0),  # no tzinfo → naive
                avg_speed_kmh=40.0,
                avg_delta_speed=2.0,
                avg_total_vehicles=5.0,
                frame_count=10,
            )
            use_case.detect([invalid_window])
