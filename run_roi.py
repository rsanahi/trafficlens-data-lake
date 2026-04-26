"""
CLI Entrypoint for ROI-based 3D Reconstruction

Filters dashcam frames using a specific GPS Polygon, builds the TelemetryRecords,
and orchestrates the Metric-Scale 3D Gaussian Splatting pipeline.
"""
import math
import json
import argparse
import duckdb
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from core.telemetry.domain.model import TelemetryRecord
from core.spatial_reconstruction.domain.model import InferenceContract
from core.spatial_reconstruction.adapters.colmap_sfm_adapter import ColmapSfMAdapter
from core.spatial_reconstruction.adapters.nerfstudio_splatfacto_adapter import NerfstudioSplatfactoAdapter
from core.spatial_reconstruction.application.reconstruct_scene_use_case import ReconstructSceneUseCase

# Tus coordenadas de la región de interés (ROI)
ROI_POLYGON = [
    (9.298476757089974, -75.38603887991098),
    (9.298016592807429, -75.3857661754253),
    (9.298715975828147, -75.38568705745722),
    (9.298171088464356, -75.38537731902905),
]

_EARTH_RADIUS_M = 6_378_137.0


def is_point_in_polygon(lat: float, lon: float, poly: list[tuple[float, float]]) -> bool:
    """Ray-casting algorithm para saber si un GPS (lat,lon) está dentro del cuadrante."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if min(p1y, p2y) < lon <= max(p1y, p2y):
            if lat <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (lon - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or lat <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def load_telemetry_for_roi(parquet_path: str, frames_dir: str) -> tuple[list[str], list[TelemetryRecord]]:
    """
    Lee tu base de datos y extrae solo las imágenes y telemetría que cayeron en el ROI.
    NOTA: Ajusta el nombre de las columnas en la consulta SQL según tu Parquet!
    """
    print(f"[*] Analizando base de datos topográfica: {parquet_path}")
    conn = duckdb.connect(database=':memory:')

    query = f"SELECT frame_filename, latitude, longitude, speed_kmh FROM read_parquet('{parquet_path}')"
    try:
        rows = conn.execute(query).fetchall()
    except Exception as e:
        raise RuntimeError(f"Error leyendo el Parquet. ¿Son correctos los nombres de las columnas? Detalle: {e}")

    filtered_frames = []
    filtered_telemetry = []
    frames_path = Path(frames_dir)

    for row in rows:
        filename, lat, lon, speed = row
        if lat is None or lon is None:
            continue

        velocidad = float(speed) if speed is not None else 0.0

        if velocidad >= 5.0 and is_point_in_polygon(lat, lon, ROI_POLYGON):
            matches = list(frames_path.rglob(filename))
            if not matches:
                print(f"[!] Archivo omitido (no encontrado on disk): {filename}")
                continue

            filtered_frames.append(str(matches[0].resolve()))
            filtered_telemetry.append(TelemetryRecord(
                raw_text="roi_filtered",
                speed_kmh=int(speed) if speed else 0,
                latitude=float(lat),
                longitude=float(lon),
                frame_filename=filename,
            ))

    return filtered_frames, filtered_telemetry


# ---------------------------------------------------------------------------
# Preflight Check
# ---------------------------------------------------------------------------

def check_preflight(telemetry: list[TelemetryRecord]) -> dict:
    """
    Valida la calidad de los frames ANTES de lanzar COLMAP.
    Calcula distancia GPS entre frames consecutivos como proxy de visual overlap.

    Umbrales:
      - mean_dist > 5m: overlap probablemente insuficiente (advertencia)
      - max_dist > 15m: brecha severa entre frames (error — abortamos)
      - Ideal para dashcam: 0.2m – 3m entre frames consecutivos
    """
    warnings: list[str] = []
    errors: list[str] = []

    sorted_telem = sorted(
        [r for r in telemetry if r.latitude and r.longitude and r.frame_filename],
        key=lambda r: r.frame_filename,
    )

    if len(sorted_telem) < 2:
        return {"mean_dist_m": 0.0, "max_dist_m": 0.0, "warnings": warnings, "errors": errors}

    distances = []
    for i in range(1, len(sorted_telem)):
        prev, curr = sorted_telem[i - 1], sorted_telem[i]
        dlat = math.radians(curr.latitude - prev.latitude)
        dlon = math.radians(curr.longitude - prev.longitude)
        lat0 = math.radians(prev.latitude)
        dx = dlon * math.cos(lat0) * _EARTH_RADIUS_M
        dy = dlat * _EARTH_RADIUS_M
        distances.append(math.sqrt(dx ** 2 + dy ** 2))

    mean_dist = sum(distances) / len(distances)
    max_dist = max(distances)

    if mean_dist > 5.0:
        warnings.append(
            f"Distancia media entre frames: {mean_dist:.2f}m — overlap visual puede ser insuficiente "
            f"(recomendado <3m). Considera aumentar la densidad de frames."
        )
    if max_dist > 15.0:
        errors.append(
            f"Brecha máxima entre frames consecutivos: {max_dist:.2f}m — "
            f"triangulación muy probable que falle. Revisa gaps en el video."
        )

    return {
        "mean_dist_m": round(mean_dist, 3),
        "max_dist_m": round(max_dist, 3),
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Bronze Layer Logging
# ---------------------------------------------------------------------------

def log_reconstruction_attempt(
    scene_id: str,
    attempt_ts: str,
    status: str,
    failure_reason: str | None,
    num_frames_input: int,
    num_frames_registered: int,
    reprojection_error_px: float,
    preflight_stats: dict,
) -> None:
    """Persiste metadatos del intento de reconstrucción en Bronze Layer (Parquet)."""
    output_dir = Path("datalake/bronze/reconstruction_attempts")
    output_dir.mkdir(parents=True, exist_ok=True)

    table = pa.table({
        "scene_id":                  pa.array([scene_id],                           type=pa.string()),
        "attempt_ts":                pa.array([attempt_ts],                          type=pa.string()),
        "status":                    pa.array([status],                              type=pa.string()),
        "failure_reason":            pa.array([failure_reason or ""],                type=pa.string()),
        "num_frames_input":          pa.array([num_frames_input],                    type=pa.int32()),
        "num_frames_registered":     pa.array([num_frames_registered],               type=pa.int32()),
        "reprojection_error_px":     pa.array([reprojection_error_px],               type=pa.float32()),
        "matcher_type":              pa.array(["sequential"],                        type=pa.string()),
        "mean_inter_frame_dist_m":   pa.array([preflight_stats.get("mean_dist_m", 0.0)], type=pa.float32()),
        "max_inter_frame_dist_m":    pa.array([preflight_stats.get("max_dist_m", 0.0)],  type=pa.float32()),
        "preflight_warnings":        pa.array([json.dumps(preflight_stats.get("warnings", []))], type=pa.string()),
    })

    safe_ts = attempt_ts.replace(":", "-").replace(" ", "_")
    out_path = output_dir / f"{scene_id}__{safe_ts}.parquet"
    pq.write_table(table, out_path)
    print(f"[*] Intento registrado en Bronze: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Reconstruir Polígono 3D a Escala Métrica")
    parser.add_argument("--parquet", default="datalake/silver/telemetry/**/*.parquet")
    parser.add_argument("--frames-dir", default="datalake/bronze/frames")
    parser.add_argument("--scene-id", default="roi_sincelejo_001")
    args = parser.parse_args()

    attempt_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Carga y filtro ROI
    frames, telemetry = load_telemetry_for_roi(args.parquet, args.frames_dir)
    print(f"\n[*] ROI contiene {len(frames)} frames utilizables.")

    # 2. Preflight check — falla rápido antes de gastar ~20min en COLMAP
    preflight = check_preflight(telemetry)

    for w in preflight["warnings"]:
        print(f"[⚠] Preflight: {w}")

    if preflight["errors"]:
        for e in preflight["errors"]:
            print(f"[❌] Preflight FAIL: {e}")
        log_reconstruction_attempt(
            scene_id=args.scene_id,
            attempt_ts=attempt_ts,
            status="preflight_failed",
            failure_reason=" | ".join(preflight["errors"]),
            num_frames_input=len(frames),
            num_frames_registered=0,
            reprojection_error_px=0.0,
            preflight_stats=preflight,
        )
        return

    if len(frames) < 30:
        print(f"[❌] Solo {len(frames)} frames — mínimo recomendado: 30. Abortando.")
        log_reconstruction_attempt(
            scene_id=args.scene_id,
            attempt_ts=attempt_ts,
            status="preflight_failed",
            failure_reason=f"insufficient_frames:{len(frames)}",
            num_frames_input=len(frames),
            num_frames_registered=0,
            reprojection_error_px=0.0,
            preflight_stats=preflight,
        )
        return

    print(f"[✓] Preflight OK — dist media: {preflight['mean_dist_m']}m, dist max: {preflight['max_dist_m']}m")

    # 3. Adaptadores
    workspace_dir = f"/tmp/trafficlens_workspace/{args.scene_id}"
    colmap_adapter = ColmapSfMAdapter(workspace_dir=f"{workspace_dir}/colmap")
    nerf_adapter = NerfstudioSplatfactoAdapter(output_dir=f"{workspace_dir}/nerfstudio")

    contract = InferenceContract(
        min_gaussians=50_000,
        max_reprojection_error=2.0,
        min_camera_poses=len(frames) // 2,
    )
    use_case = ReconstructSceneUseCase(colmap_adapter, nerf_adapter, contract)

    # 4. Pipeline
    print(f"\n[*] Iniciando Reconstrucción 3D (Escala Métrica Real)...")
    try:
        scene = use_case.execute(frame_paths=frames, scene_id=args.scene_id, telemetry=telemetry)

        log_reconstruction_attempt(
            scene_id=args.scene_id,
            attempt_ts=attempt_ts,
            status="success",
            failure_reason=None,
            num_frames_input=len(frames),
            num_frames_registered=len(scene.camera_poses),
            reprojection_error_px=scene.average_reprojection_error,
            preflight_stats=preflight,
        )

        print("\n" + "=" * 50)
        print("RECONSTRUCCION COMPLETADA CON EXITO")
        print("=" * 50)
        print(f"Escena ID       : {scene.scene_id}")
        print(f"Frames registrados: {len(scene.camera_poses)} / {len(frames)}")
        print(f"Gaussianos (pts): {scene.num_gaussians:,}")
        print(f"Error Reproy.   : {scene.average_reprojection_error:.2f} px")
        print(f"\nVISUALIZADOR 3D:")
        print(f"  ns-viewer --load-config {workspace_dir}/nerfstudio/{args.scene_id}/splatfacto/config.yml")

    except Exception as e:
        failure_reason = type(e).__name__ + ": " + str(e)[:300]
        log_reconstruction_attempt(
            scene_id=args.scene_id,
            attempt_ts=attempt_ts,
            status="failed",
            failure_reason=failure_reason,
            num_frames_input=len(frames),
            num_frames_registered=0,
            reprojection_error_px=0.0,
            preflight_stats=preflight,
        )
        print(f"\n[❌] Error Crítico durante la reconstrucción: \n{e}")


if __name__ == "__main__":
    main()
