{{ config(
    materialized='incremental',
    location='{{ var("datalake_path") }}/datalake/silver/detections.parquet',
    unique_key='frame_id'
) }}

/*
    Staging Layer: Object Detections
    - cast columns to integer
    - extract source file properly
*/

WITH source_data AS (
    SELECT * FROM {{ source('trafficlens_bronze', 'detections') }}
),

cleaned AS (
    SELECT
        frame_filename,
        CAST(car_count AS INTEGER) as car_count,
        CAST(motorcycle_count AS INTEGER) as motorcycle_count,
        scan.filename as source_file,
        regexp_extract(scan.filename, '([^/]+)\.csv$', 1) as video_id,
        regexp_extract(scan.filename, '([^/]+)\.csv$', 1) || '_' || frame_filename as frame_id
    FROM source_data as scan
    WHERE frame_filename IS NOT NULL
)

SELECT * FROM cleaned
