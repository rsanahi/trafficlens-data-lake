---
name: TrafficLens Project Overview
description: Estado actual del pipeline de datos: entidades modeladas, capas dbt, fuentes de datos
type: project
---

Proyecto TrafficLens — data lake de análisis de tráfico a partir de dashcam.

**Hardware fuente**: VIOFO A229 Pro (video .mp4 con telemetría overlay: GPS, velocidad, timestamp)

**Pipeline de ingesta (Python)**:
- OcrVideoReader (OpenCV + Tesseract) -> extrae telemetría frame a frame -> Bronze CSV
- FpsFrameExtractor -> extrae frames JPG a 1 FPS -> Bronze images
- LocalYoloDetector (YOLOv8) -> detecciones de vehículos por frame -> Bronze CSV
- Puerto limpio para swappear a AWS Rekognition / SageMaker sin cambiar dominio

**Capas dbt (DuckDB, materialización external Parquet)**:
- Bronze: CSVs raw de telemetría y detecciones + JPGs de frames
- Silver: silver_telemetry (casted, deduped, particionado por fecha), silver_detections
- Gold actual: fct_vehicle_counts (join telemetría + detecciones, car_count, motorcycle_count, total_vehicles, lat/lon, speed), fct_trips (dim de viajes: start/end, duración, avg/max speed, distancia estimada, total_points), fct_ml_training_catalog (frames candidatas para entrenamiento, filtro speed > 5 km/h)

**Dominio modelado**:
- TelemetryRecord: timestamp, speed_kmh, latitude, longitude, raw_text, frame_filename
- FrameVehicleCounts: frame_filename, car_count, motorcycle_count
- Spatial reconstruction domain: CameraPose, SplatScene (COLMAP/3D Gaussian Splatting)

**Frontend**: Streamlit + PyDeck (mapa interactivo)
**Infra**: AWS CDK en /infra/

**Convenciones actuales**:
- Nomenclatura: silver_{entidad}, fct_{proceso}, dim_{entidad}
- Particionado silver: partition_date
- Stack: dbt-duckdb local, diseñado para migrar a Athena/Glue
- Branch activo: video-data-frame

**Why**: Portfolio piece para demostrar DS + DE skills combinadas.
