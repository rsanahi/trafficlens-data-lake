{{ config(
    materialized='external',
    location='{{ var("datalake_path") }}/datalake/silver/reconstruction_attempts',
    options={'overwrite_or_ignore': 'true'}
) }}

SELECT
    scene_id,
    TRY_CAST(attempt_ts AS TIMESTAMP)   AS attempt_ts,
    status,
    NULLIF(failure_reason, '')           AS failure_reason,
    num_frames_input,
    num_frames_registered,
    ROUND(CAST(reprojection_error_px AS DOUBLE), 4)   AS reprojection_error_px,
    matcher_type,
    ROUND(CAST(mean_inter_frame_dist_m AS DOUBLE), 3) AS mean_inter_frame_dist_m,
    ROUND(CAST(max_inter_frame_dist_m  AS DOUBLE), 3) AS max_inter_frame_dist_m,
    preflight_warnings,
    CASE
        WHEN num_frames_input > 0
        THEN ROUND(100.0 * num_frames_registered / num_frames_input, 1)
        ELSE 0.0
    END AS registration_rate_pct

FROM {{ source('trafficlens_bronze', 'reconstruction_attempts') }}
