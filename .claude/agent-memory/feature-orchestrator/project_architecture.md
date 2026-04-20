---
name: trafficlens-data-lake architecture
description: Layer structure, dbt conventions, domain patterns, and test style for this project
type: project
---

## Data Lake Layers

**Bronze:** raw CSVs from VIOFO dashcam OCR (`datalake/bronze/telemetry/*.csv`, `detections/*.csv`).
**Silver:** cleaned + typed external Parquet via dbt. Key models: `silver_telemetry`, `silver_detections`.
**Int (Intermediate):** joined/transformed views materialized as DuckDB tables. First created with `int_telemetry_10s_windows` feature (2026-04-19).
**Gold:** curated external Parquet for consumption by ML/domain. `fct_vehicle_counts`, `fct_traffic_windows`, etc.

## dbt Conventions

- Engine: DuckDB. Use DuckDB-native syntax (e.g., `time_bucket`, `QUALIFY ROW_NUMBER()`).
- External materialization: `location='{{ var("datalake_path") }}/datalake/<layer>/<model>.parquet'`.
- Silver: `+materialized: external`, `+file_format: parquet`.
- Int: `+materialized: table` (in-memory DuckDB table, no Parquet).
- Gold: `+materialized: external`, `+file_format: parquet`.
- `dbt_project.yml` vars: `datalake_path` points to repo root.
- All new layers must be registered in `dbt_project.yml` under `models.trafficlens_dbt`.
- Schema tests live in per-folder `.yml` files (e.g., `int_telemetry_10s_windows.yml`).
- Gold models documented in `gold/gold.yml`.

## Domain / Application Conventions

- Value objects: `@dataclass(frozen=True)` for simple data carriers (TrafficWindow, AnomalyScore, FrameVehicleCounts).
- Rich entities: Pydantic `BaseModel` with validators (CameraPose, SplatScene) when invariants need enforcement.
- All ports live in a single file: `core/domain/ports.py`.
- One use case per file in `core/application/`.
- Adapters in `core/infrastructure/`. Application layer must NEVER import infrastructure libraries.
- Clean Architecture: domain → application → infrastructure (no reverse imports).

## Test Conventions

- Framework: `pytest`.
- No mocking libraries. All fakes are hand-rolled inner classes implementing the port.
- Fakes are deterministic and rule-based (not random).
- Test file structure: `TestUseCaseName` class grouping related tests.
- Helper `_make_*` or `_window(...)` factory functions for test data.
- Edge cases covered: empty input, single item, mixed batch, identity preservation.
- Port isolation tests: verify application layer source does not import infra libraries.

**Why:** This ensures test failures map directly to domain logic failures, not mock configuration.
**How to apply:** Always write fake implementations, never `unittest.mock.patch`.
