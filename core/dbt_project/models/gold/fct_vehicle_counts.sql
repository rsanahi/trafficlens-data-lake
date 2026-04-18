{{ config(
    materialized='external',
    location='{{ var("datalake_path") }}/datalake/gold/fct_vehicle_counts.parquet'
) }}

/*
    Curated Layer / Mart: Fact table for Vehicle Counts
    - Joins unique telemetry frames with the object detections.
    - Provides total vehicle metrics alongside geographical point logic.
*/

WITH telemetry_base AS (
    -- We want only one telemetry point per frame, because OCR provides detections per frame
    SELECT * FROM {{ ref('silver_telemetry') }}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY frame_id ORDER BY event_time) = 1
),

detections AS (
    SELECT * FROM {{ ref('silver_detections') }}
),

joined_counts AS (
    SELECT
        t.event_time,
        t.frame_id,
        t.video_id,
        t.latitude,
        t.longitude,
        t.speed_kmh,
        t.source_file,
        COALESCE(d.car_count, 0) as car_count,
        COALESCE(d.motorcycle_count, 0) as motorcycle_count,
        (COALESCE(d.car_count, 0) + COALESCE(d.motorcycle_count, 0)) as total_vehicles
    FROM telemetry_base t
    INNER JOIN detections d ON t.frame_id = d.frame_id
)

SELECT * FROM joined_counts
ORDER BY event_time
