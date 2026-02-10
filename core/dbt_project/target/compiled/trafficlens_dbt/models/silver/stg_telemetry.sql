

/*
    Silver Layer: Cleaned Telemetry
    - cast timestamps
    - remove null coordinates
    - add partitions (virtual)
*/

WITH source_data AS (
    SELECT * FROM read_csv_auto('/Users/anahiruiz/Documents/GitHub/trafficlens-data-lake/datalake/bronze/telemetry/*.csv')
),

cleaned AS (
    SELECT
        -- Parse Timestamp (handling possible formats if CSV varies, but we assume ISO from viofo_ocr.py)
        TRY_CAST(timestamp AS TIMESTAMP) as event_time,
        
        -- Geolocation
        CAST(latitude AS DOUBLE) as latitude,
        CAST(longitude AS DOUBLE) as longitude,
        
        -- Speed
        CAST(speed_kmh AS DOUBLE) as speed_kmh,
        
        -- Metadata
        raw_text,
        frame_filename
        
    FROM source_data
    WHERE latitude IS NOT NULL 
      AND longitude IS NOT NULL
)

SELECT * FROM cleaned