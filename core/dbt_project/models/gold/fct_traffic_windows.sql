{{ config(
    materialized='external',
    location='{{ var("datalake_path") }}/datalake/gold/fct_traffic_windows.parquet'
) }}

/*
    Gold Layer: Traffic Anomaly Feature Store
    -----------------------------------------
    Reads from the intermediate 10-second window model and surfaces clean,
    typed feature columns for downstream ML consumption.

    Consumer: DetectTrafficAnomalies use case → IsolationForestAdapter.
    Features consumed: avg_speed_kmh, avg_delta_speed, avg_total_vehicles.

    Materialized as external Parquet for zero-copy reads by the Python application layer.
*/

WITH windows AS (
    SELECT * FROM {{ ref('int_telemetry_10s_windows') }}
)

SELECT
    video_id,
    window_start,
    CAST(avg_speed_kmh AS DOUBLE)      AS avg_speed_kmh,
    CAST(avg_delta_speed AS DOUBLE)    AS avg_delta_speed,
    CAST(avg_total_vehicles AS DOUBLE) AS avg_total_vehicles,
    frame_count
FROM windows
ORDER BY video_id, window_start
