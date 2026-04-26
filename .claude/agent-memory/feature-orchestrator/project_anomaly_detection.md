---
name: Traffic Anomaly Detection — Isolation Forest feature
description: Full delivery context for the anomaly detection feature (2026-04-19): dbt models, domain objects, test patterns, architectural decisions
type: project
---

## Feature delivered: 2026-04-19

Isolation Forest anomaly detection on 10-second dashcam telemetry windows.

## dbt Data Contracts

**int_telemetry_10s_windows** (core/dbt_project/models/int/)
- Grain: (video_id, window_start) — one row per 10-second bucket per video.
- JOIN: silver_telemetry INNER JOIN silver_detections ON frame_id.
- delta_speed: ABS(speed_kmh - LAG(speed_kmh) OVER (PARTITION BY video_id ORDER BY event_time)).
- First frame per video excluded (delta_speed IS NULL filter).
- Aggregation: time_bucket(INTERVAL '10 seconds', event_time).
- Output cols: video_id, window_start, avg_speed_kmh DOUBLE, avg_delta_speed DOUBLE, avg_total_vehicles DOUBLE, frame_count INT.

**fct_traffic_windows** (core/dbt_project/models/gold/)
- Reads from int_telemetry_10s_windows.
- External Parquet: datalake/gold/fct_traffic_windows.parquet.
- Explicit CAST(... AS DOUBLE) for type safety.

## Domain Objects

- TrafficWindow: @dataclass(frozen=True) in core/domain/traffic_window.py.
- AnomalyScore: @dataclass(frozen=True) in core/domain/anomaly_score.py. Carries contamination for traceability.
- AnomalyDetectorPort: appended to core/domain/ports.py (single ports file pattern).

## Application Layer

- DetectTrafficAnomalies: core/application/detect_traffic_anomalies.py.
- Thin orchestrator — delegates entirely to AnomalyDetectorPort.
- Public method: `detect(windows)` — named after the domain intent, not technical convention. Replaces `execute()` (renamed 2026-04-19 for ubiquitous language alignment).
- Empty list short-circuit: returns [] before calling port.
- Zero infrastructure imports enforced by test.

## Infrastructure Layer

- IsolationForestAdapter: core/infrastructure/isolation_forest_adapter.py.
- Transductive batch mode: fits AND scores on the same windows in one call.
- Features: [avg_speed_kmh, avg_delta_speed, avg_total_vehicles].
- contamination=0.05, random_state=42, threshold=-0.1.
- Lambda-friendly: no GPU, no persistent model state by default.

## Test Fake: InMemoryAnomalyDetector (pure Fake — revised 2026-04-19)

Pure Fake in tests/application/test_detect_traffic_anomalies.py:
- Constructor accepts `results: list[AnomalyScore] | None`. Also exposes `set_results()`.
- Returns pre-configured AnomalyScore objects verbatim — zero threshold logic, zero business rules.
- Each test constructs its own InMemoryAnomalyDetector with explicit results; no shared fixture for scenario tests.
- CONTAMINATION = 0.05 retained as a class constant for traceability assertions.
- _score() helper mirrors _window() helper to build AnomalyScore with matching (video_id, offset_seconds).
- Exactly 10 tests covering: 4 scenarios, cardinality, identity, empty batch, single window, mixed batch, contamination traceability, sklearn isolation.

**Why:** The original rule-based fake was a Domain Service disguised as a test double. Any threshold drift in the real adapter would silently break tests. A pure Fake eliminates that coupling — the test declares what the detector *will return*, not how it decides.

**Pattern:** For any AnomalyDetectorPort fake: construct with `results=`, never evaluate domain signals inside the fake.

## TrafficWindow Invariant Hardening (2026-04-19)

All 6 invariants were already implemented in `TrafficWindow.__post_init__` (core/domain/traffic_window.py). The gap was the absence of tests.

**Invariants enforced:**
1. video_id not blank/whitespace → ValueError("video_id...")
2. avg_speed_kmh >= 0 → ValueError("avg_speed_kmh...")
3. avg_delta_speed >= 0 → ValueError("avg_delta_speed...")
4. avg_total_vehicles >= 0 → ValueError("avg_total_vehicles...")
5. frame_count >= 1 → ValueError("frame_count...")
6. window_start timezone-aware → ValueError("window_start...")

**Testing rule:** Invariants are tested ONLY through DetectTrafficAnomalies.detect(), never by instantiating TrafficWindow directly in a standalone assertion. Violation is expected at construction time inside pytest.raises(ValueError).

**New test class:** TestTrafficWindowInvariants in tests/application/test_detect_traffic_anomalies.py — 6 tests, one per invariant, each using InMemoryAnomalyDetector with results=[].

**Error message contract:** Each ValueError message contains the field name as a substring. Tests assert with `match="field_name"` to confirm the right invariant was triggered.

**Existing fixtures:** _window() helper and all TestDetectTrafficAnomalies fixtures already used tzinfo=timezone.utc — no fixture updates needed.
