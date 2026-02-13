
{{ config(
    materialized='external',
    location='/Users/anahiruiz/Documents/GitHub/trafficlens-data-lake/datalake/gold/ml_training_catalog.parquet'
) }}

/*
    Gold Layer: ML Training Catalog
    - Filters frames suitable for Object Detection training.
    - Rule: Speed > 5 km/h (to avoid standing still / repetitive frames).
    - Rule: Must have valid frame filename.
*/

WITH silver_telemetry AS (
    SELECT * FROM {{ ref('stg_telemetry') }}
),

candidates AS (
    SELECT
        event_time,
        frame_filename,
        latitude,
        longitude,
        speed_kmh,
        source_file
        
    FROM silver_telemetry
    WHERE 
        frame_filename IS NOT NULL 
        AND frame_filename != ''
        AND speed_kmh > 5.0  -- Filter for movement
)

SELECT * FROM candidates
ORDER BY event_time
