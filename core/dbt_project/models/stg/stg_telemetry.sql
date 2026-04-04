{{ config(
    materialized='external',
    location='/Users/anahiruiz/Documents/GitHub/trafficlens-data-lake/datalake/staging/telemetry',
    options={'partition_by': 'partition_date', 'overwrite_or_ignore': 'true'}
) }}

/*
    Silver Layer: Cleaned Telemetry
    - cast timestamps
    - remove null coordinates
    - add partitions (virtual)
*/

WITH source_data AS (
    SELECT * FROM {{ source('trafficlens_bronze', 'telemetry') }}
),

cleaned AS (
    SELECT
        -- Parse Timestamp (handling possible formats if CSV varies, but we assume ISO from viofo_ocr.py)
        TRY_CAST(timestamp AS TIMESTAMP) as event_time,
        
        -- Partitioning Key
        CAST(TRY_CAST(timestamp AS TIMESTAMP) AS DATE) as partition_date,
        
        -- Geolocation
        CAST(latitude AS DOUBLE) as latitude,
        CAST(longitude AS DOUBLE) as longitude,
        
        -- Speed
        CAST(speed_kmh AS DOUBLE) as speed_kmh,
        
        -- Metadata
        raw_text,
        frame_filename,
        
        -- Derived columns
        -- Extract just the filename from the full path to avoid mismatches
        scan.filename as source_file,
        
        -- Extract video_id (basename without extension)
        regexp_extract(scan.filename, '([^/]+)\.csv$', 1) as video_id,
        
        -- Globally unique frame identifier
        regexp_extract(scan.filename, '([^/]+)\.csv$', 1) || '_' || frame_filename as frame_id
        
    FROM source_data as scan
    WHERE latitude IS NOT NULL 
      AND longitude IS NOT NULL
)

SELECT * FROM cleaned
