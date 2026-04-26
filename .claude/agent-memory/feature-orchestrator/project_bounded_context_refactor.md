---
name: Bounded Context Refactor — 2026-04-19
description: Domain review and refactor of all bounded contexts: canonical per-subdomain structure, shim cleanup complete (2026-04-19), cross-context patterns, known pre-existing test failures
type: project
---

## Refactor delivered: 2026-04-19

Branch: refactor/domain-definitions-organization

## Phase 1: Per-Context Port Decomposition (earlier in the day)

`core/domain/ports.py` was decomposed into four per-context port files:
- `core/domain/telemetry_ports.py`
- `core/domain/vehicle_detection_ports.py`
- `core/domain/spatial_reconstruction_ports.py`
- `core/domain/traffic_analysis_ports.py`

`core/domain/ports.py` became a backward-compatible re-export shim.

## Phase 2: Canonical Per-Subdomain Structure Migration (later in the day)

All flat domain/application/infrastructure files migrated to canonical per-subdomain structure.

### Canonical Structure

```
core/
├── telemetry/
│   ├── domain/
│   │   ├── model.py                  ← TelemetryRecord, VideoMetadata
│   │   └── ports/
│   │       └── i_telemetry_ports.py  ← VideoReaderPort, TelemetryRepositoryPort
│   ├── application/
│   │   ├── extract_telemetry_use_case.py
│   │   └── dtos/__init__.py
│   └── adapters/
│       ├── ocr_video_reader.py
│       └── csv_telemetry_repository.py
├── vehicle_detection/
│   ├── domain/
│   │   ├── model.py                            ← FrameVehicleCounts
│   │   └── ports/
│   │       └── i_vehicle_detection_ports.py    ← VehicleDetectorPort, VehicleCountsRepositoryPort, FrameProviderPort
│   ├── application/
│   │   ├── extract_vehicle_counts_use_case.py
│   │   └── dtos/__init__.py
│   └── adapters/
│       ├── csv_detection_repository.py
│       ├── local_yolo_detector.py
│       └── local_jpeg_frame_provider.py
├── spatial_reconstruction/
│   ├── domain/
│   │   ├── model.py                                  ← CameraPose, SplatScene, InferenceContract
│   │   ├── exceptions/
│   │   │   └── domain_exceptions.py                  ← SceneReliabilityError, ContractViolationError
│   │   └── ports/
│   │       └── i_spatial_reconstruction_ports.py     ← SfMMapperPort, GaussianTrainerPort
│   ├── application/
│   │   ├── reconstruct_scene_use_case.py
│   │   └── dtos/__init__.py
│   └── adapters/
│       ├── colmap_sfm_adapter.py
│       └── nerfstudio_splatfacto_adapter.py
└── traffic_analysis/
    ├── domain/
    │   ├── model.py                              ← TrafficWindow, AnomalyScore, ANOMALY_THRESHOLD
    │   └── ports/
    │       └── i_traffic_analysis_ports.py       ← AnomalyDetectorPort
    ├── application/
    │   ├── detect_traffic_anomalies_use_case.py
    │   └── dtos/__init__.py
    └── adapters/
        └── isolation_forest_adapter.py
```

### Shim Strategy

ALL old flat paths converted to backward-compatible re-export shims:

**core/domain/ shims** (preserve test imports):
- `telemetry_record.py` → re-exports from `core.telemetry.domain.model`
- `video_metadata.py` → re-exports from `core.telemetry.domain.model`
- `vehicle_counts.py` → re-exports from `core.vehicle_detection.domain.model`
- `traffic_window.py` → re-exports from `core.traffic_analysis.domain.model`
- `anomaly_score.py` → re-exports from `core.traffic_analysis.domain.model`
- `spatial_reconstruction.py` → re-exports from `core.spatial_reconstruction.domain.model` + exceptions
- `telemetry_ports.py` → re-exports from `core.telemetry.domain.ports.i_telemetry_ports`
- `vehicle_detection_ports.py` → re-exports from `core.vehicle_detection.domain.ports.i_vehicle_detection_ports`
- `spatial_reconstruction_ports.py` → re-exports from `core.spatial_reconstruction.domain.ports.i_spatial_reconstruction_ports`
- `traffic_analysis_ports.py` → re-exports from `core.traffic_analysis.domain.ports.i_traffic_analysis_ports`
- `ports.py` → re-exports from all canonical port modules directly

**core/application/ shims** (preserve test imports):
- `extract_telemetry.py` → `core.telemetry.application.extract_telemetry_use_case`
- `extract_vehicle_counts.py` → `core.vehicle_detection.application.extract_vehicle_counts_use_case`
- `reconstruct_scene.py` → `core.spatial_reconstruction.application.reconstruct_scene_use_case`
- `detect_traffic_anomalies.py` → `core.traffic_analysis.application.detect_traffic_anomalies_use_case`

**core/infrastructure/ shims** (preserve batch_ingest.py + run_roi.py imports):
- All 7 infrastructure files replaced with re-export shims to canonical adapter paths

**Shim cleanup completed: 2026-04-19**

All callers (including test files) migrated to canonical paths. Shim files in
`core/domain/`, `core/application/`, and `core/infrastructure/` replaced with
hard `raise ImportError(...)` tombstones pointing to canonical locations.
The flat package directories and their `__init__.py` files remain on disk but
contain no live code — they will produce an immediate, descriptive ImportError
if accidentally imported.

**How to apply:** All imports must use canonical per-subdomain paths. The flat
package paths are dead. Any new file must never import from `core.domain`,
`core.application`, or `core.infrastructure`.

## Bounded Context Map

Four bounded contexts, all isolated except one documented cross-context dependency:

1. **Telemetry Ingestion** (core subdomain)
   - Canonical ports: `core/telemetry/domain/ports/i_telemetry_ports.py`
   - Value Objects: TelemetryRecord, VideoMetadata (in model.py)
   - Use Case: ExtractTelemetryUseCase (method: `execute`)

2. **Vehicle Detection** (supporting subdomain)
   - Canonical ports: `core/vehicle_detection/domain/ports/i_vehicle_detection_ports.py`
   - Value Objects: FrameVehicleCounts (in model.py)
   - Use Case: ExtractVehicleCountsUseCase (method: `execute`)
   - Known seam: `_resolve_frame_paths()` uses stdlib `pathlib` as fallback — NOT an infra leak.

3. **Spatial Reconstruction** (supporting subdomain)
   - Canonical ports: `core/spatial_reconstruction/domain/ports/i_spatial_reconstruction_ports.py`
   - Entities/VOs: CameraPose, SplatScene, InferenceContract (in model.py)
   - Domain Exceptions: `core/spatial_reconstruction/domain/exceptions/domain_exceptions.py`
   - Use Case: ReconstructSceneUseCase (method: `execute`)
   - Cross-context: Conformist pattern — SfMMapperPort imports TelemetryRecord from Telemetry context

4. **Traffic Analysis** (supporting subdomain)
   - Canonical ports: `core/traffic_analysis/domain/ports/i_traffic_analysis_ports.py`
   - Value Objects: TrafficWindow, AnomalyScore (in model.py)
   - Use Case: DetectTrafficAnomalies (method: `detect`)

## Cross-Context Pattern: Conformist

Spatial Reconstruction consumes TelemetryRecord as-is (Conformist pattern).
- `i_spatial_reconstruction_ports.py` directly imports from `core.telemetry.domain.model`
- `reconstruct_scene_use_case.py` directly imports from `core.telemetry.domain.model`
- If TelemetryRecord evolves to carry Telemetry-context invariants, introduce an anti-corruption layer (e.g., `GpsPrior` VO) at the Spatial Reconstruction boundary.

## Known Pre-Existing Test Failures (DO NOT FIX — tests/ is frozen)

In `tests/application/test_detect_traffic_anomalies.py`:
- `test_velocidad_cero_normal_is_not_detected_as_anomaly` (line 235): calls `_score(is_anomaly=False, ...)` — TypeError because `_score()` has no `is_anomaly` parameter.
- `test_mixed_batch_produces_correct_anomaly_flags` (lines 335-338): same issue, 4 calls with `is_anomaly=...`.

These 2 tests fail with `TypeError: _score() got an unexpected keyword argument 'is_anomaly'`. The remaining 14 tests pass. Pre-existing bug in the test helper.

## Domain Exception Design Decision

`SceneReliabilityError` and `ContractViolationError` inherit `ValueError` intentionally:
- Tests use `pytest.raises(ValueError, match="...")` — must remain ValueError subclasses.
- Do NOT change the inheritance to break the ValueError catch chain.
- Canonical location: `core/spatial_reconstruction/domain/exceptions/domain_exceptions.py`
- Shim re-exports them from `core/domain/spatial_reconstruction.py` for backward compatibility.
