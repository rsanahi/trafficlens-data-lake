{{ config(
    materialized='table'
) }}

/*
    Intermediate Layer: Telemetry 10-Second Windows
    -----------------------------------------------
    Joins silver_telemetry with silver_detections on frame_id.
    Computes per-frame delta_speed using LAG over the video's chronological order.
    Aggregates into non-overlapping 10-second time buckets per video.

    Output grain: one row per (video_id, window_start) — a 10-second window.

    Downstream consumer: fct_traffic_windows (Gold Layer) → IsolationForestAdapter.
*/

WITH base AS (
    SELECT
        t.video_id,
        t.event_time,
        t.frame_id,
        t.speed_kmh,
        COALESCE(d.car_count, 0)          AS car_count,
        COALESCE(d.motorcycle_count, 0)   AS motorcycle_count,
        (COALESCE(d.car_count, 0) + COALESCE(d.motorcycle_count, 0)) AS total_vehicles
    FROM {{ ref('silver_telemetry') }} t
    INNER JOIN {{ ref('silver_detections') }} d
        ON t.frame_id = d.frame_id
),

with_delta AS (
    SELECT
        video_id,
        event_time,
        frame_id,
        speed_kmh,
        total_vehicles,
        -- delta_speed: absolute change in speed from the previous frame within the same video
        ABS(
            speed_kmh - LAG(speed_kmh) OVER (
                PARTITION BY video_id
                ORDER BY event_time
            )
        ) AS delta_speed
    FROM base
),

windowed AS (
    SELECT
        video_id,
        -- DuckDB time_bucket: floor every event_time to the nearest 10-second boundary
        time_bucket(INTERVAL '10 seconds', event_time) AS window_start,
        AVG(speed_kmh)      AS avg_speed_kmh,
        AVG(delta_speed)    AS avg_delta_speed,
        AVG(total_vehicles) AS avg_total_vehicles,
        COUNT(*)            AS frame_count
    FROM with_delta
    -- Exclude the first frame per video where delta_speed is NULL (no previous frame)
    WHERE delta_speed IS NOT NULL
    GROUP BY video_id, time_bucket(INTERVAL '10 seconds', event_time)
)

SELECT
    video_id,
    window_start,
    avg_speed_kmh,
    avg_delta_speed,
    avg_total_vehicles,
    frame_count
FROM windowed
ORDER BY video_id, window_start
