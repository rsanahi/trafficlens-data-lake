
{{ config(
    materialized='external',
    location='/Users/anahiruiz/Documents/GitHub/trafficlens-data-lake/datalake/curated/dim_trips.parquet'
) }}

/*
    Gold Layer: Trip Dimension
    - Aggregates telemetry by source video file.
    - Metrics: Start/End Time, Duration, Avg Speed, Distance (proxy).
*/

WITH silver_telemetry AS (
    SELECT * FROM {{ ref('stg_telemetry') }}
),

trip_stats AS (
    SELECT
        -- Using the source filename as the Trip ID for now
        source_file as trip_id,
        
        MIN(event_time) as start_time,
        MAX(event_time) as end_time,
        
        -- Duration in seconds
        date_diff('second', MIN(event_time), MAX(event_time)) as duration_seconds,
        
        -- Speed stats
        AVG(speed_kmh) as avg_speed_kmh,
        MAX(speed_kmh) as max_speed_kmh,
        
        -- Simple distance approximation: Avg Speed (km/h) * Duration (h)
        (AVG(speed_kmh) * (date_diff('second', MIN(event_time), MAX(event_time)) / 3600.0)) as estimated_distance_km,
        
        COUNT(*) as total_points
        
    FROM silver_telemetry
    GROUP BY source_file
)

SELECT * FROM trip_stats
