"""
Infrastructure Layer — ColmapSfMAdapter

Concrete adapter implementing SfMMapperPort using COLMAP as a local subprocess.

Responsibilities (this adapter owns these, not the domain):
  1. Running COLMAP (feature_extractor → exhaustive_matcher → mapper) as subprocesses.
  2. Normalizing COLMAP's raw quaternion floats to unit length before constructing CameraPose.
  3. Parsing sparse/0/images.txt into CameraPose domain objects.
  4. Raising ColmapReconstructionError with enough context for debugging.

Apple Silicon (MPS) optimization:
  - COLMAP is built with CUDA/Metal support — uses Metal (MPS) on macOS via OpenGL/Metal backend.
  - The adapter passes `--ImageReader.single_camera 1` to reduce memory usage on unified memory.
  - Workspace is kept local (not /tmp) to leverage fast NVMe I/O on M-series chips.

Clean Architecture constraint:
  - This file is the ONLY place in the codebase that knows about COLMAP.
  - The domain layer (CameraPose, SplatScene, ports) must NEVER import from here.
"""
import math
import os
import shutil
import subprocess
from pathlib import Path

from core.domain.ports import SfMMapperPort
from core.domain.spatial_reconstruction import CameraPose


# ---------------------------------------------------------------------------
# Custom Infrastructure Exception
# ---------------------------------------------------------------------------

class ColmapReconstructionError(RuntimeError):
    """
    Raised when COLMAP exits with a non-zero status or produces no usable output.
    Carries the subprocess exit code and command for debugging.
    """
    pass


# ---------------------------------------------------------------------------
# ColmapSfMAdapter
# ---------------------------------------------------------------------------

class ColmapSfMAdapter(SfMMapperPort):
    """
    Runs COLMAP locally to extract CameraPose objects from a set of frame images.

    COLMAP pipeline executed:
        1. feature_extractor  → detects SIFT keypoints in each frame
        2. exhaustive_matcher → matches keypoints across all frame pairs
        3. mapper             → triangulates 3D points and estimates camera poses
        4. Parser             → reads sparse/0/images.txt → [CameraPose]

    The adapter normalizes quaternions from COLMAP output before constructing
    CameraPose objects, satisfying the Domain's strict |q| = 1 ± 1e-4 invariant.
    """

    # COLMAP's images.txt has 9 fields per registered image line:
    # IMAGE_ID  QW  QX  QY  QZ  TX  TY  TZ  CAMERA_ID  NAME
    _IMAGE_LINE_FIELD_COUNT = 10

    def __init__(
        self,
        workspace_dir: str,
        colmap_binary: str = "colmap",
        vocab_tree_path: str | None = None,
    ) -> None:
        """
        Args:
            workspace_dir:    Path where COLMAP will write its database and sparse model.
                              Should be on local NVMe storage for Apple Silicon performance.
            colmap_binary:    Path to the COLMAP executable (default: relies on PATH).
            vocab_tree_path:  Optional path to a vocabulary tree for faster matching
                              on large frame sets (>500 frames). If None, uses
                              exhaustive matching (suitable for dashcam clips <5 min).
        """
        self._workspace = Path(workspace_dir)
        self._colmap = colmap_binary
        self._vocab_tree = vocab_tree_path

    # ---------------------------------------------------------------------------
    # SfMMapperPort implementation
    # ---------------------------------------------------------------------------

    def map_poses(self, frame_paths: list[str]) -> list[CameraPose]:
        """
        Run COLMAP on the provided frames and return validated CameraPose objects.

        Args:
            frame_paths: absolute paths to Bronze Layer JPEG frames.

        Returns:
            List of CameraPose Value Objects with normalized unit quaternions.

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
        sparse_dir = self._workspace / "sparse"
        sparse_dir.mkdir(exist_ok=True)

        self._run_feature_extractor(db_path, images_dir)
        self._run_matcher(db_path)
        self._run_mapper(db_path, images_dir, sparse_dir)

        images_txt = sparse_dir / "0" / "images.txt"
        if not images_txt.exists():
            raise ColmapReconstructionError(
                f"COLMAP mapper produced no sparse model at {images_txt}. "
                "This usually means insufficient frame overlap for triangulation. "
                "Check that frames have >60% visual overlap between consecutive shots."
            )

        poses = self._parse_images_txt(images_txt.read_text())
        if not poses:
            raise ColmapReconstructionError(
                f"COLMAP registered 0 camera poses from {len(frame_paths)} frames. "
                "The scene may lack texture (blank walls, sky) or frame overlap is too low."
            )

        return poses

    # ---------------------------------------------------------------------------
    # Private: Workspace preparation
    # ---------------------------------------------------------------------------

    def _prepare_workspace(self, frame_paths: list[str]) -> Path:
        """
        Create a COLMAP workspace and symlink the input frames into it.
        Using symlinks avoids duplicating potentially large JPEG files on disk.
        """
        images_dir = self._workspace / "images"
        if images_dir.exists():
            shutil.rmtree(images_dir)
        images_dir.mkdir(parents=True)

        for src_path in frame_paths:
            src = Path(src_path)
            dst = images_dir / src.name
            os.symlink(src.resolve(), dst)

        return images_dir

    # ---------------------------------------------------------------------------
    # Private: COLMAP subprocess runners
    # ---------------------------------------------------------------------------

    def _run_feature_extractor(self, db_path: Path, images_dir: Path) -> None:
        """Run COLMAP SIFT feature extraction. Optimized for Apple Silicon unified memory."""
        cmd = [
            self._colmap, "feature_extractor",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--ImageReader.single_camera", "1",      # reduces memory usage (unified memory)
            "--SiftExtraction.use_gpu", "1",          # uses Metal on macOS via OpenGL
            "--SiftExtraction.max_image_size", "1600", # balance quality vs. MPS memory
        ]
        self._run(cmd, step="feature_extractor")

    def _run_matcher(self, db_path: Path) -> None:
        """Run feature matching. Uses exhaustive or vocab-tree depending on config."""
        if self._vocab_tree:
            cmd = [
                self._colmap, "vocab_tree_matcher",
                "--database_path", str(db_path),
                "--VocabTreeMatching.vocab_tree_path", self._vocab_tree,
            ]
        else:
            cmd = [
                self._colmap, "exhaustive_matcher",
                "--database_path", str(db_path),
                "--SiftMatching.use_gpu", "1",
            ]
        self._run(cmd, step="matcher")

    def _run_mapper(self, db_path: Path, images_dir: Path, sparse_dir: Path) -> None:
        """Run incremental SfM mapper to triangulate 3D points and recover camera poses."""
        cmd = [
            self._colmap, "mapper",
            "--database_path", str(db_path),
            "--image_path", str(images_dir),
            "--output_path", str(sparse_dir),
            "--Mapper.ba_refine_focal_length", "0",  # dashcams have fixed focal length
            "--Mapper.ba_refine_principal_point", "0",
        ]
        self._run(cmd, step="mapper")

    def _run(self, cmd: list[str], step: str) -> None:
        """Execute a COLMAP subprocess and raise ColmapReconstructionError on failure."""
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ColmapReconstructionError(
                f"COLMAP {step} failed with exit code {result.returncode}.\n"
                f"Command: {' '.join(cmd)}\n"
                f"stderr: {result.stderr[-2000:]}"  # last 2000 chars to avoid log flooding
            )

    # ---------------------------------------------------------------------------
    # Private: COLMAP output parser
    # ---------------------------------------------------------------------------

    def _parse_images_txt(self, content: str) -> list[CameraPose]:
        """
        Parse COLMAP's sparse/0/images.txt format into CameraPose Value Objects.

        images.txt format (two lines per registered image):
            IMAGE_ID  QW  QX  QY  QZ  TX  TY  TZ  CAMERA_ID  NAME
            POINTS2D[] as (X, Y, POINT3D_ID)  ← skipped

        Returns an empty list if no images were registered (caller handles the error).
        """
        poses: list[CameraPose] = []
        lines = content.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip comment lines and empty lines
            if not line or line.startswith("#"):
                i += 1
                continue

            parts = line.split()
            if len(parts) == self._IMAGE_LINE_FIELD_COUNT:
                # This is an image registration line
                _, qw, qx, qy, qz, tx, ty, tz, _, name = parts

                raw_quaternion = [float(qw), float(qx), float(qy), float(qz)]
                translation = [float(tx), float(ty), float(tz)]

                # Adapter responsibility: normalize before handing to domain
                normalized_q = self._normalize_quaternion(raw_quaternion)

                # frame_id = filename stem (e.g. "frame_0001" from "frame_0001.jpg")
                frame_id = Path(name).stem

                pose = CameraPose(
                    frame_id=frame_id,
                    translation=translation,
                    quaternion=normalized_q,
                )
                poses.append(pose)

                # Skip the POINTS2D line that follows each image line
                i += 2
            else:
                i += 1

        return poses

    def _normalize_quaternion(self, q: list[float]) -> list[float]:
        """
        Normalize a quaternion [qw, qx, qy, qz] to unit length.

        This is the adapter's core responsibility: raw COLMAP floats may deviate
        slightly from unit length due to floating-point arithmetic in the mapper.
        By normalizing here, we guarantee the Domain's strict |q| = 1 ± 1e-4 invariant.

        Raises:
            ValueError: if the quaternion is a zero vector (indicates a corrupt output).
        """
        norm = math.sqrt(sum(c ** 2 for c in q))
        if norm < 1e-10:
            raise ValueError(
                f"Cannot normalize a zero quaternion {q}. "
                "This indicates a corrupt COLMAP output — check the sparse reconstruction."
            )
        return [c / norm for c in q]
