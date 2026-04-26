"""
Infrastructure Layer — ColmapSfMAdapter

Concrete adapter implementing SfMMapperPort using COLMAP as a local subprocess.

Canonical location: core/spatial_reconstruction/adapters/colmap_sfm_adapter.py

Responsibilities (this adapter owns all of these, not the domain):
  1. Running COLMAP (feature_extractor → spatial/exhaustive_matcher → mapper).
  2. Injecting GPS priors into COLMAP's SQLite database for metric-scale reconstruction.
  3. Converting GPS (lat/lon) to local ENU (East-North-Up) metric coordinates.
  4. Normalizing COLMAP's raw quaternions to unit length before constructing CameraPose.
  5. Parsing sparse/0/images.txt into CameraPose domain objects.
  6. Raising ColmapReconstructionError with enough context for debugging.

Apple Silicon (MPS) optimization:
  - When GPS is available, spatial_matcher replaces exhaustive_matcher (logarithmic scaling).
  - exhaustive_matcher = O(n²) frame pairs —— spatial_matcher = O(n * k) where k << n.
  - `--ImageReader.single_camera 1` reduces unified memory usage on M3 Pro.
  - Symlinks instead of file copies leverage fast NVMe I/O.

Clean Architecture constraint:
  - This file is the ONLY place in the codebase that knows about COLMAP.
  - The domain and application layers must NEVER import from here.
"""
import math
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from core.spatial_reconstruction.domain.ports.i_spatial_reconstruction_ports import SfMMapperPort
from core.spatial_reconstruction.domain.model import CameraPose
from core.telemetry.domain.model import TelemetryRecord


# ---------------------------------------------------------------------------
# Custom Infrastructure Exception
# ---------------------------------------------------------------------------

class ColmapReconstructionError(RuntimeError):
    """
    Raised when COLMAP exits with a non-zero status or produces no usable output.
    Carries subprocess exit code and command for debugging.
    """
    pass


# ---------------------------------------------------------------------------
# ColmapSfMAdapter
# ---------------------------------------------------------------------------

class ColmapSfMAdapter(SfMMapperPort):
    """
    Runs COLMAP locally to extract CameraPose objects from a set of frame images.

    When GPS telemetry is provided:
      - GPS coordinates are converted to local ENU metric XYZ (pure Python math).
      - XYZ priors are injected into COLMAP's SQLite DB before matching.
      - spatial_matcher replaces exhaustive_matcher for O(n·k) scaling on MPS.
      - colmap model_aligner aligns the sparse model to the GPS trace.

    COLMAP pipeline:
        feature_extractor → [spatial|exhaustive]_matcher → mapper → model_aligner*
        (* only when GPS telemetry is available)

    The adapter normalizes quaternions from COLMAP output before constructing
    CameraPose objects, satisfying the Domain's strict |q| = 1 ± 1e-4 invariant.
    """

    _IMAGE_LINE_FIELD_COUNT = 10

    # WGS84 Earth radius in meters
    _EARTH_RADIUS_M: float = 6_378_137.0

    def __init__(
        self,
        workspace_dir: str,
        colmap_binary: str = "colmap",
        spatial_match_max_distance_m: float = 50.0,
    ) -> None:
        self._workspace = Path(workspace_dir)
        self._colmap = colmap_binary
        self._spatial_match_distance = spatial_match_max_distance_m

    # ---------------------------------------------------------------------------
    # SfMMapperPort implementation
    # ---------------------------------------------------------------------------

    def map_poses(
        self,
        frame_paths: list[str],
        telemetry: list[TelemetryRecord] | None = None,
    ) -> list[CameraPose]:
        if not frame_paths:
            raise ValueError(
                "frame_paths cannot be empty — COLMAP requires at least one frame."
            )

        images_dir = self._prepare_workspace(frame_paths)
        db_path = self._workspace / "colmap.db"
        if db_path.exists():
            db_path.unlink()

        sparse_dir = self._workspace / "sparse"
        sparse_dir.mkdir(exist_ok=True)

        self._run_feature_extractor(db_path, images_dir)

        if telemetry:
            gps_map = self._build_enu_map(frame_paths, telemetry)
            if gps_map:
                conn = sqlite3.connect(str(db_path))
                try:
                    self._inject_gps_priors_to_db(conn, gps_map)
                    conn.commit()
                finally:
                    conn.close()
        self._run_sequential_matcher(db_path)

        self._run_mapper(db_path, images_dir, sparse_dir)

        model_dir = self._find_best_sparse_model(sparse_dir)
        if model_dir is None:
            raise ColmapReconstructionError(
                f"COLMAP mapper produced no sparse model under {sparse_dir}. "
                "This usually means insufficient frame overlap for triangulation. "
                "Ensure frames have >60% visual overlap between consecutive shots."
            )
        images_txt = model_dir / "images.txt"

        poses = self._parse_images_txt(images_txt.read_text())
        if not poses:
            raise ColmapReconstructionError(
                f"COLMAP registered 0 camera poses from {len(frame_paths)} frames. "
                "The scene may lack texture or frame overlap is too low."
            )

        return poses

    # ---------------------------------------------------------------------------
    # Private: Workspace preparation
    # ---------------------------------------------------------------------------

    def _prepare_workspace(self, frame_paths: list[str]) -> Path:
        images_dir = self._workspace / "images"
        if images_dir.exists():
            shutil.rmtree(images_dir)
        images_dir.mkdir(parents=True)

        for src_path in frame_paths:
            src = Path(src_path)
            dst = images_dir / src.name
            shutil.copy2(src.resolve(), dst)

        return images_dir

    # ---------------------------------------------------------------------------
    # Private: GPS → ENU helpers (pure Python math — no dependencies)
    # ---------------------------------------------------------------------------

    def _lat_lon_to_local_xyz(
        self,
        lat: float,
        lon: float,
        lat0: float,
        lon0: float,
    ) -> tuple[float, float, float]:
        lat0_rad = math.radians(lat0)
        d_lat = math.radians(lat - lat0)
        d_lon = math.radians(lon - lon0)

        x_east  = d_lon * math.cos(lat0_rad) * self._EARTH_RADIUS_M
        y_north = d_lat * self._EARTH_RADIUS_M
        z_up    = 0.0

        return x_east, y_north, z_up

    def _build_enu_map(
        self,
        frame_paths: list[str],
        telemetry: list[TelemetryRecord],
    ) -> dict[str, tuple[float, float, float]]:
        aligned = self._align_telemetry_to_frames(frame_paths, telemetry)
        if not aligned:
            return {}

        first_record = next(iter(aligned.values()))
        lat0 = first_record.latitude
        lon0 = first_record.longitude

        enu_map: dict[str, tuple[float, float, float]] = {}
        for path, record in aligned.items():
            name = Path(path).name
            x, y, z = self._lat_lon_to_local_xyz(
                record.latitude,
                record.longitude,
                lat0,
                lon0,
            )
            enu_map[name] = (x, y, z)

        return enu_map

    def _align_telemetry_to_frames(
        self,
        frame_paths: list[str],
        telemetry: list[TelemetryRecord],
    ) -> dict[str, TelemetryRecord]:
        telem_by_name: dict[str, TelemetryRecord] = {}
        for record in telemetry:
            if (
                record.frame_filename is not None
                and record.latitude is not None
                and record.longitude is not None
            ):
                telem_by_name[record.frame_filename] = record

        matched: dict[str, TelemetryRecord] = {}
        for path in frame_paths:
            name = Path(path).name
            if name in telem_by_name:
                matched[path] = telem_by_name[name]

        return matched

    def _inject_gps_priors_to_db(
        self,
        conn: sqlite3.Connection,
        gps_map: dict[str, tuple[float, float, float]],
    ) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(images)")
        columns = [info[1] for info in cursor.fetchall()]

        if "prior_tx" not in columns:
            cursor.execute("ALTER TABLE images ADD COLUMN prior_tx REAL")
            cursor.execute("ALTER TABLE images ADD COLUMN prior_ty REAL")
            cursor.execute("ALTER TABLE images ADD COLUMN prior_tz REAL")

        for name, (px, py, pz) in gps_map.items():
            conn.execute(
                """
                UPDATE images
                   SET prior_tx = ?, prior_ty = ?, prior_tz = ?
                 WHERE name = ?
                """,
                (px, py, pz, name),
            )

    # ---------------------------------------------------------------------------
    # Private: COLMAP subprocess runners
    # ---------------------------------------------------------------------------

    def _run_feature_extractor(self, db_path: Path, images_dir: Path) -> None:
        cmd = [
            self._colmap, "feature_extractor",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--ImageReader.camera_model", "OPENCV",
            "--ImageReader.single_camera", "1",
            "--SiftExtraction.use_gpu", "0",
            "--SiftExtraction.max_image_size", "1600",
        ]
        self._run(cmd, step="feature_extractor")

    def _run_sequential_matcher(self, db_path: Path) -> None:
        cmd = [
            self._colmap, "sequential_matcher",
            "--database_path", str(db_path),
            "--SequentialMatching.overlap", "15",
            "--SiftMatching.use_gpu", "0",
        ]
        self._run(cmd, step="sequential_matcher")

    def _run_spatial_matcher(self, db_path: Path) -> None:
        cmd = [
            self._colmap, "spatial_matcher",
            "--database_path", str(db_path),
            "--SpatialMatching.max_num_neighbors", "50",
            "--SpatialMatching.max_distance", str(self._spatial_match_distance),
            "--SiftMatching.use_gpu", "1",
        ]
        self._run(cmd, step="spatial_matcher")

    def _run_exhaustive_matcher(self, db_path: Path) -> None:
        cmd = [
            self._colmap, "exhaustive_matcher",
            "--database_path", str(db_path),
            "--SiftMatching.use_gpu", "0",
        ]
        self._run(cmd, step="exhaustive_matcher")

    def _run_mapper(self, db_path: Path, images_dir: Path, sparse_dir: Path) -> None:
        cmd = [
            self._colmap, "mapper",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--output_path", str(sparse_dir),
            "--Mapper.ba_refine_focal_length", "1",
            "--Mapper.ba_refine_principal_point", "0",
            "--Mapper.init_min_tri_angle", "3",
            "--Mapper.multiple_models", "0",
            "--Mapper.abs_pose_min_num_inliers", "15",
            "--Mapper.init_min_num_inliers", "50",
        ]
        self._run(cmd, step="mapper")

    def _run_model_aligner(
        self,
        sparse_dir: Path,
        gps_map: dict[str, tuple[float, float, float]]
    ) -> None:
        model_path = sparse_dir / "0"
        ref_file = self._workspace / "enu_refs.txt"

        lines = [f"{name} {x} {y} {z}" for name, (x, y, z) in gps_map.items()]
        ref_file.write_text("\n".join(lines))

        cmd = [
            self._colmap, "model_aligner",
            "--input_path", str(model_path),
            "--output_path", str(model_path),
            "--ref_images_path", str(ref_file),
            "--ref_is_gps", "0",
            "--alignment_type", "custom",
            "--alignment_max_error", "100.0",
        ]
        self._run(cmd, step="model_aligner")

    def _run(self, cmd: list[str], step: str) -> None:
        print(f"\n[DEBUG] Running COLMAP step: {step}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stderr.strip():
            lines = result.stderr.strip().splitlines()
            print(f"[DEBUG {step} log snippet]:")
            for line in lines[-15:]:
                print("   ", line)

        if result.returncode != 0:
            raise ColmapReconstructionError(
                f"COLMAP {step} failed with exit code {result.returncode}.\n"
                f"Command: {' '.join(cmd)}\n"
                f"stderr: {result.stderr[-2000:]}"
            )

    # ---------------------------------------------------------------------------
    # Private: COLMAP output parser
    # ---------------------------------------------------------------------------

    def _find_best_sparse_model(self, sparse_dir: Path) -> Path | None:
        best: Path | None = None
        best_count = 0
        for candidate in sorted(sparse_dir.iterdir()):
            images_txt = candidate / "images.txt"
            if not images_txt.exists():
                continue
            count = sum(
                1 for line in images_txt.read_text().splitlines()
                if line and not line.startswith("#") and len(line.split()) == self._IMAGE_LINE_FIELD_COUNT
            )
            print(f"[DEBUG] sparse model {candidate.name}: {count} registered images")
            if count > best_count:
                best_count = count
                best = candidate
        return best

    def _parse_images_txt(self, content: str) -> list[CameraPose]:
        poses: list[CameraPose] = []
        lines = content.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("#"):
                i += 1
                continue

            parts = line.split()
            if len(parts) == self._IMAGE_LINE_FIELD_COUNT:
                _, qw, qx, qy, qz, tx, ty, tz, _, name = parts

                q = self._normalize_quaternion(
                    [float(qw), float(qx), float(qy), float(qz)]
                )
                pose = CameraPose(
                    frame_id=Path(name).stem,
                    translation=[float(tx), float(ty), float(tz)],
                    quaternion=q,
                )
                poses.append(pose)
                i += 2  # skip the POINTS2D line
            else:
                i += 1

        return poses

    def _normalize_quaternion(self, q: list[float]) -> list[float]:
        norm = math.sqrt(sum(c ** 2 for c in q))
        if norm < 1e-10:
            raise ValueError(
                f"Cannot normalize a zero quaternion {q}. "
                "This indicates a corrupt COLMAP output."
            )
        return [c / norm for c in q]
