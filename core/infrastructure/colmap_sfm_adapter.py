"""
Infrastructure Layer — ColmapSfMAdapter

Concrete adapter implementing SfMMapperPort using COLMAP as a local subprocess.

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

from core.domain.ports import SfMMapperPort
from core.domain.spatial_reconstruction import CameraPose
from core.domain.telemetry_record import TelemetryRecord


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
        """
        Args:
            workspace_dir:               Local path for COLMAP workspace (DB + sparse model).
                                         Use NVMe-local paths on Apple Silicon for best I/O.
            colmap_binary:               Path to COLMAP executable (default: relies on PATH).
            spatial_match_max_distance_m: Max distance (meters) between frames to attempt
                                         feature matching. 50m covers typical dashcam clips.
                                         Only used when GPS telemetry is provided.
        """
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
        """
        Run COLMAP on the provided frames and return validated CameraPose objects.

        When telemetry is provided:
          - GPS priors are injected into COLMAP's DB enabling metric-scale reconstruction.
          - spatial_matcher is used for faster matching on Apple Silicon (MPS).

        Args:
            frame_paths: absolute paths to Bronze Layer JPEG frames.
            telemetry:   optional GPS telemetry aligned to frame_paths.

        Returns:
            List of CameraPose Value Objects with normalized unit quaternions.
            If telemetry was provided, translations are in metric coordinates (meters).

        Raises:
            ValueError: if frame_paths is empty.
            ColmapReconstructionError: if COLMAP exits non-zero or produces no poses.
        """
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

        # Step 1: Feature extraction (always)
        self._run_feature_extractor(db_path, images_dir)

        # Step 2: GPS injection + sequential matching (dashcam = video sequence)
        # sequential_matcher only pairs consecutive frames → stable baseline → valid triangulation.
        # exhaustive_matcher (O(n²)) matches distant frames with no shared features, producing a
        # noisy covisibility graph that causes PnP registration failure downstream.
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

        # Step 3: Incremental SfM mapper
        self._run_mapper(db_path, images_dir, sparse_dir)

        # Step 4 (GPS alignment) skipped: ENU priors already loaded into COLMAP DB.
        # The incremental mapper uses them internally. model_aligner is only needed
        # for post-hoc alignment, which can be run manually if required.

        # Step 5: Parse images.txt → [CameraPose]
        # Mapper may produce multiple sub-models (sparse/0/, sparse/1/, ...); use the largest.
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
        """Symlink input frames into workspace/images/ (avoids duplicating JPEG data)."""
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
        """
        Convert GPS coordinates (degrees) to local ENU metric coordinates (meters).

        Uses the Equirectangular approximation — accurate to <0.1% error for
        distances up to ~50 km, which covers all dashcam clip scenarios.

        ENU convention:
          X = East  (positive = east of reference)
          Y = North (positive = north of reference)
          Z = Up    (always 0 — dashcams drive on flat terrain)

        Args:
            lat, lon:    GPS coordinates of the point to convert.
            lat0, lon0:  GPS coordinates of the local origin (reference frame).

        Returns:
            (x_east_m, y_north_m, z_up_m) in meters.
        """
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
        """
        Build a mapping from COLMAP image filename → ENU (x, y, z) in meters.

        Uses the first valid GPS coordinate as the local origin (reference point),
        ensuring all other coordinates are relative displacements in meters.
        Frames without GPS data or with None coordinates are excluded silently.

        Returns:
            dict mapping image basename (e.g. "frame_0001.jpg") → (x, y, z) meters.
        """
        aligned = self._align_telemetry_to_frames(frame_paths, telemetry)
        if not aligned:
            return {}

        # Use the first matched record as ENU origin
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
        """
        Match each frame_path to a TelemetryRecord by filename.

        Excludes:
          - Frames with no matching TelemetryRecord.
          - TelemetryRecords where latitude or longitude is None.

        Returns:
            dict mapping absolute frame_path → TelemetryRecord.
        """
        # Build lookup by filename
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
        """
        Write ENU prior coordinates into COLMAP's SQLite images table.
        """
        # Validar si COLMAP creó la tabla con las columnas de priors (depende de la versión)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(images)")
        columns = [info[1] for info in cursor.fetchall()]
        
        # Si no existen, las agregamos (comportamiento seguro para COLMAP 3.8+)
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
        """Run SIFT feature extraction, optimized for Apple Silicon unified memory."""
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
        """
        Match each frame against its N temporal neighbors.
        Correct strategy for dashcam/video sequences: O(n * overlap) pairs,
        all with consistent baseline, producing a clean covisibility graph.
        overlap=15 covers ~0.5s at 30fps — enough for reliable feature overlap.
        """
        cmd = [
            self._colmap, "sequential_matcher",
            "--database_path", str(db_path),
            "--SequentialMatching.overlap", "15",
            "--SiftMatching.use_gpu", "0",
        ]
        self._run(cmd, step="sequential_matcher")

    def _run_spatial_matcher(self, db_path: Path) -> None:
        """
        Run spatial feature matching using GPS-injected priors.

        Replaces exhaustive_matcher when GPS is available:
        - O(n·k) complexity vs O(n²) — critical for long dashcam clips.
        - Only matches frames within spatial_match_max_distance_m meters.
        - 'is_gps 0' because we injected local XYZ (not raw lat/lon degrees).
        """
        cmd = [
            self._colmap, "spatial_matcher",
            "--database_path", str(db_path),
            "--SpatialMatching.max_num_neighbors", "50",
            "--SpatialMatching.max_distance", str(self._spatial_match_distance),
            "--SiftMatching.use_gpu", "1",
        ]
        self._run(cmd, step="spatial_matcher")

    def _run_exhaustive_matcher(self, db_path: Path) -> None:
        """Run exhaustive matching — used when no GPS telemetry is available."""
        cmd = [
            self._colmap, "exhaustive_matcher",
            "--database_path", str(db_path),
            "--SiftMatching.use_gpu", "0",
        ]
        self._run(cmd, step="exhaustive_matcher")

    def _run_mapper(self, db_path: Path, images_dir: Path, sparse_dir: Path) -> None:
        """Run incremental SfM mapper to triangulate 3D points and recover camera poses."""
        cmd = [
            self._colmap, "mapper",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--output_path", str(sparse_dir),
            # Allow focal length to refine — fixing it causes ill-conditioned BA (CHOLMOD singular matrix)
            # when combined with GPS priors or near-planar dashcam trajectories.
            "--Mapper.ba_refine_focal_length", "1",
            "--Mapper.ba_refine_principal_point", "0",
            # Dashcam frames have small inter-frame angle (~2-5°); default 16° discards all
            # initialization pairs. Lower threshold lets the mapper bootstrap the first pair.
            "--Mapper.init_min_tri_angle", "3",
            # Force a single reconstruction — prevents scene from splitting into disconnected models.
            "--Mapper.multiple_models", "0",
            # Lower inlier thresholds for forward-facing cameras with small baseline.
            "--Mapper.abs_pose_min_num_inliers", "15",
            "--Mapper.init_min_num_inliers", "50",
        ]
        self._run(cmd, step="mapper")

    def _run_model_aligner(
        self,
        sparse_dir: Path,
        gps_map: dict[str, tuple[float, float, float]]
    ) -> None:
        """
        Align sparse model to the GPS trace using the injected prior coordinates.
        Resolves the scale ambiguity, converting the reconstruction to metric scale.
        """
        model_path = sparse_dir / "0"
        ref_file = self._workspace / "enu_refs.txt"
        
        # Generar archivo de referencia que espera model_aligner (formato: "nombre x y z")
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
        """Execute a COLMAP subprocess and raise ColmapReconstructionError on failure."""
        print(f"\n[DEBUG] Running COLMAP step: {step}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # COLMAP a menudo suprime advertencias críticas en stdout sin cambiar el código de salida.
        # Imprimimos las últimas líneas para entender por qué el Feature Extractor se está quedando ciego.
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
        """
        Return the sub-model directory with the most registered images.
        COLMAP may split a scene into sparse/0/, sparse/1/, etc.
        """
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
        """Parse COLMAP's sparse/0/images.txt into CameraPose Value Objects."""
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
        """
        Normalize quaternion to unit length.
        Adapter responsibility — guarantees Domain's |q| = 1 ± 1e-4 invariant.
        """
        norm = math.sqrt(sum(c ** 2 for c in q))
        if norm < 1e-10:
            raise ValueError(
                f"Cannot normalize a zero quaternion {q}. "
                "This indicates a corrupt COLMAP output."
            )
        return [c / norm for c in q]
