# TrafficLens Data Lake 🚦

Scalable Video Ingestion and Analytics Architecture for Dashcam Footage on AWS.

TrafficLens transforms raw dashcam video into actionable data (GPS tracks, speed, trips) using a Modern Data Stack approach (Python, dbt, DuckDB, Parquet, Streamlit).

## Data Lake Architecture

The project implements a Medallion Architecture (Bronze, Silver, Gold) to organize data refinement.

### 🥉 Bronze Layer (Raw Ingestion)
**Goal:** Capture extraction output "as-is" without data loss.
-   **Source**: Raw `.mp4` videos from VIOFO A229 Pro.
-   **Process**: OCR Extraction (`core/viofo_ocr.py`).
-   **Artifacts**:
    -   `datalake/bronze/telemetry/*.csv`: Raw text data (Time, Speed, GPS text) extracted frame-by-frame.
    -   `datalake/bronze/frames/{video_id}/*.jpg`: Extracted frames (images) sampled at 1 FPS.

### 🥈 Silver Layer (Refined/Cleaned)
**Goal:** Clean, standardize, and type-cast the data for query performance.
-   **Process**: dbt Transformation (`models/silver/stg_telemetry.sql`).
-   **Engine**: DuckDB.
-   **Artifacts**:
    -   `datalake/silver/telemetry.parquet`: 
        -   Timestamps parsed to actual `DATETIME` objects.
        -   Coordinates cast to `DOUBLE`.
        -   Nulls removed.
        -   Stored in columnar **Parquet** format for efficient analytical queries.

### 🥇 Gold Layer (Business Aggregates)
**Goal:** Business-ready tables and ML preparation.
-   **Process**: dbt Aggregation.
-   **Artifacts**:
    -   **`dim_trips.parquet`**: Trip Summary.
        -   *Columns*: `trip_id`, `start_time`, `duration`, `distance_km`, `avg_speed`.
        -   *Use Case*: "How long did I drive?"
    -   **`ml_training_catalog.parquet`**: ML Dataset Candidate List.
        -   *Columns*: `frame_filename`, `speed`, `gps`.
        -   *Filter*: `speed > 5 km/h` (Filters out idling/red lights).
        -   *Use Case*: Training Object Detection models on high-quality frames.

---

## 🚀 How to Run

### 1. Ingest Videos (Bronze -> Gold)
Process all videos in a folder automatically.
```bash
python core/batch_ingest.py /Volumes/External/dashcam/
```

### 2. Visualize (Frontend)
Explore your trips and data in the interactive dashboard.
```bash
streamlit run frontend/app.py
```

## Project Structure
-   `core/`: Python ETL scripts (`viofo_ocr.py`, `batch_ingest.py`).
-   `core/dbt_project/`: SQL transformations managing Silver/Gold layers.
-   `frontend/`: Streamlit dashboard application.
-   `datalake/`: Local storage simulating AWS S3 buckets.
