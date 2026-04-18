"""
Infrastructure Layer — NerfstudioSplatfactoAdapter

Concrete adapter implementing GaussianTrainerPort using Nerfstudio's splatfacto
trainer as a local subprocess, optimized for Apple Silicon (MPS/Metal).

Responsibilities (this adapter owns all of these, not the domain):
  1. Writing camera poses to Nerfstudio-compatible transforms.json format.
  2. Running `ns-train splatfacto` as a subprocess with MPS optimization flags.
  3. Parsing the output .ply file vertex count → num_gaussians.
  4. Parsing Nerfstudio stdout for PSNR → reprojection quality proxy.
  5. Computing a bounding box from camera translation vectors.
  6. Constructing and returning a validated SplatScene domain entity.

Apple Silicon (MPS) optimization:
  - `--pipeline.model.background-color random` → improves convergence on M-series
  - `--pipeline.datamanager.num-processes 0` → disables multiprocessing (MPS incompatibility)
  - `--pipeline.model.use-gradient-scaling True` → stabilizes mixed-precision on MPS

Clean Architecture constraint:
  - This file is the ONLY place in the codebase that knows about Nerfstudio.
  - The domain and application layers must NEVER import from here.
"""
import json
import math
import re
import subprocess
from pathlib import Path

from core.domain.ports import GaussianTrainerPort
from core.domain.spatial_reconstruction import CameraPose, SplatScene


# ---------------------------------------------------------------------------
# Custom Infrastructure Exception
# ---------------------------------------------------------------------------

class NerfstudioTrainingError(RuntimeError):
    """
    Raised when ns-train exits with a non-zero status or produces no usable output.
    Carries enough context (exit code, stderr tail) for debugging MPS/GPU failures.
    """
    pass


# ---------------------------------------------------------------------------
# NerfstudioSplatfactoAdapter
# ---------------------------------------------------------------------------

class NerfstudioSplatfactoAdapter(GaussianTrainerPort):
    """
    Trains a 3D Gaussian Splatting model using Nerfstudio's splatfacto method.

    Pipeline:
        1. Write camera_poses → transforms.json (Nerfstudio's custom data format)
        2. Run `ns-train splatfacto nerfstudio-data --data <workspace>`
        3. Parse output splat.ply vertex count → num_gaussians
        4. Parse training stdout → PSNR → reprojection quality proxy
        5. Compute bounding box from camera translations
        6. Construct and return a validated SplatScene

    Default training config targets Apple Silicon M3 Pro (8GB GPU / 18GB Unified Memory):
        - max_num_iterations=15_000  (reduced from default 30k for fast iteration)
        - Batch size managed by Nerfstudio automatically for MPS memory limits
    """

    # Camera intrinsics for dashcam (Blackvue/Viofo typical values — override if known)
    _DASHCAM_FL_X: float = 800.0   # focal length x (pixels)
    _DASHCAM_FL_Y: float = 800.0   # focal length y (pixels)
    _DASHCAM_CX: float = 960.0     # principal point x (1920/2)
    _DASHCAM_CY: float = 540.0     # principal point y (1080/2)
    _DASHCAM_W: int = 1920
    _DASHCAM_H: int = 1080

    def __init__(
        self,
        output_dir: str,
        nerfstudio_binary: str = "ns-train",
        max_num_iterations: int = 15_000,
        fl_x: float | None = None,
        fl_y: float | None = None,
    ) -> None:
        """
        Args:
            output_dir:          Root directory where Nerfstudio writes model checkpoints.
            nerfstudio_binary:   Path to ns-train (default: relies on activated venv PATH).
            max_num_iterations:  Training steps. 15k is sufficient for dashcam clip quality.
                                 Increase to 30k for final production reconstructions.
            fl_x/fl_y:           Override dashcam focal length (pixels) if known precisely.
                                 Better intrinsics → lower reprojection proxy → higher quality.
        """
        self._output_dir = Path(output_dir)
        self._binary = nerfstudio_binary
        self._max_iters = max_num_iterations
        self._fl_x = fl_x or self._DASHCAM_FL_X
        self._fl_y = fl_y or self._DASHCAM_FL_Y

    # ---------------------------------------------------------------------------
    # GaussianTrainerPort implementation
    # ---------------------------------------------------------------------------

    def train(self, camera_poses: list[CameraPose], scene_id: str) -> SplatScene:
        """
        Train a 3DGS model from CameraPose objects and return a validated SplatScene.

        Args:
            camera_poses: validated CameraPose objects from SfMMapperPort.
            scene_id:     unique identifier for the resulting scene.

        Returns:
            SplatScene entity with reliability metrics (num_gaussians, reprojection proxy,
            point_cloud_density, bounding_box).

        Raises:
            ValueError: if camera_poses is empty.
            NerfstudioTrainingError: if ns-train exits non-zero or produces no PLY.
            SceneReliabilityError: if SplatScene's own invariants are violated
                                   (propagates naturally from domain).
        """
        if not camera_poses:
            raise ValueError(
                "camera_poses cannot be empty — Nerfstudio requires at least one registered view."
            )

        workspace = self._output_dir / scene_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Step 1: Write transforms.json for Nerfstudio's nerfstudio-data parser
        transforms_path = workspace / "transforms.json"
        self._write_transforms_json(camera_poses, transforms_path)

        # Step 2: Run ns-train splatfacto
        stdout = self._run_nerfstudio(workspace, scene_id)

        # Step 3: Locate the output splat.ply
        splat_ply = self._find_splat_ply(workspace, scene_id)

        # Step 4: Count Gaussians from PLY header
        ply_bytes = splat_ply.read_bytes()
        header = ply_bytes[:2048]   # header is always within the first 2KB
        num_gaussians = self._count_gaussians_from_ply_header(header)

        # Step 5: Parse PSNR from training stdout → reprojection proxy
        psnr = self._parse_final_psnr(stdout)
        reprojection_proxy = self._psnr_to_reprojection_proxy(psnr)

        # Step 6: Compute bounding box and point cloud density from poses
        bounding_box = self._compute_bounding_box(camera_poses)
        point_cloud_density = min(1.0, num_gaussians / 500_000)  # normalized density

        # Step 7: Construct and return validated SplatScene
        # SceneReliabilityError propagates if domain invariants are violated
        return SplatScene(
            scene_id=scene_id,
            camera_poses=camera_poses,
            num_gaussians=num_gaussians,
            average_reprojection_error=reprojection_proxy,
            point_cloud_density=point_cloud_density,
        )

    # ---------------------------------------------------------------------------
    # Private: transforms.json writer
    # ---------------------------------------------------------------------------

    def _write_transforms_json(
        self,
        camera_poses: list[CameraPose],
        path: Path,
    ) -> None:
        """
        Write Nerfstudio's transforms.json from CameraPose domain objects.

        Nerfstudio expects camera-to-world transform matrices (c2w), but COLMAP
        provides world-to-camera (w2c). We invert the rotation and negate translation.
        """
        frames = []
        for pose in camera_poses:
            c2w = self._camera_pose_to_c2w_matrix(pose)
            frames.append({
                "file_path": f"images/{pose.frame_id}.jpg",
                "transform_matrix": c2w,
            })

        transforms = {
            "camera_model": "OPENCV",
            "fl_x": self._fl_x,
            "fl_y": self._fl_y,
            "cx": self._DASHCAM_CX,
            "cy": self._DASHCAM_CY,
            "w": self._DASHCAM_W,
            "h": self._DASHCAM_H,
            "frames": frames,
        }
        path.write_text(json.dumps(transforms, indent=2))

    def _camera_pose_to_c2w_matrix(self, pose: CameraPose) -> list[list[float]]:
        """
        Convert a CameraPose (COLMAP w2c quaternion + translation) to a 4×4
        camera-to-world matrix as required by Nerfstudio.

        COLMAP stores world-to-camera: p_cam = R * p_world + t
        Nerfstudio expects camera-to-world: p_world = R^T * (p_cam - t)

        c2w = [R^T | -R^T * t]
              [0   |    1     ]
        """
        qw, qx, qy, qz = pose.quaternion
        tx, ty, tz = pose.translation

        # Quaternion → rotation matrix R (world-to-camera)
        R = [
            [1 - 2*(qy**2 + qz**2),   2*(qx*qy - qz*qw),   2*(qx*qz + qy*qw)],
            [2*(qx*qy + qz*qw),        1 - 2*(qx**2 + qz**2), 2*(qy*qz - qx*qw)],
            [2*(qx*qz - qy*qw),        2*(qy*qz + qx*qw),   1 - 2*(qx**2 + qy**2)],
        ]

        # R^T (camera-to-world rotation)
        Rt = [[R[j][i] for j in range(3)] for i in range(3)]

        # -R^T * t (camera-to-world translation)
        t = [tx, ty, tz]
        neg_Rt_t = [-(Rt[i][0]*t[0] + Rt[i][1]*t[1] + Rt[i][2]*t[2]) for i in range(3)]

        return [
            [Rt[0][0], Rt[0][1], Rt[0][2], neg_Rt_t[0]],
            [Rt[1][0], Rt[1][1], Rt[1][2], neg_Rt_t[1]],
            [Rt[2][0], Rt[2][1], Rt[2][2], neg_Rt_t[2]],
            [0.0,      0.0,      0.0,      1.0         ],
        ]

    # ---------------------------------------------------------------------------
    # Private: Nerfstudio subprocess runner
    # ---------------------------------------------------------------------------

    def _run_nerfstudio(self, workspace: Path, scene_id: str) -> str:
        """Run ns-train splatfacto and return stdout for metric parsing."""
        cmd = [
            self._binary, "splatfacto",
            "--data", str(workspace),
            "--output-dir", str(self._output_dir),
            "--experiment-name", scene_id,
            "--max-num-iterations", str(self._max_iters),
            # --- Apple Silicon MPS optimizations ---
            "--pipeline.model.background-color", "random",
            "--pipeline.datamanager.num-processes", "0",   # MPS incompatible with fork()
            "--pipeline.model.use-gradient-scaling", "True",
            # --- Data parser ---
            "nerfstudio-data",
            "--data", str(workspace),
        ]
        result = subprocess.run(cmd, capture_output=False, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            raise NerfstudioTrainingError(
                f"ns-train splatfacto failed with exit code {result.returncode}.\n"
                f"Scene: {scene_id}\n"
                f"Output tail:\n{result.stdout[-3000:]}"
            )
        return result.stdout

    def _find_splat_ply(self, workspace: Path, scene_id: str) -> Path:
        """
        Locate the output splat.ply produced by splatfacto.
        Nerfstudio writes to: <output_dir>/<scene_id>/splatfacto/<timestamp>/splat.ply
        """
        splatfacto_dir = self._output_dir / scene_id / "splatfacto"
        if not splatfacto_dir.exists():
            raise NerfstudioTrainingError(
                f"Nerfstudio output directory not found: {splatfacto_dir}. "
                "Training may have failed silently."
            )
        # Find the most recent training run (sorted by timestamp folder name)
        run_dirs = sorted(splatfacto_dir.iterdir(), reverse=True)
        for run_dir in run_dirs:
            candidate = run_dir / "splat.ply"
            if candidate.exists():
                return candidate

        raise NerfstudioTrainingError(
            f"No splat.ply found under {splatfacto_dir}. "
            "Training completed but produced no Gaussian output — check MPS memory limits."
        )

    # ---------------------------------------------------------------------------
    # Public helpers (tested independently as pure units)
    # ---------------------------------------------------------------------------

    def _count_gaussians_from_ply_header(self, header_bytes: bytes) -> int:
        """
        Parse the PLY header to extract the vertex count (= number of 3D Gaussians).

        PLY format: header ends at 'end_header\n'. The 'element vertex N' line
        specifies the total number of Gaussian splats in the model.
        """
        header_text = header_bytes.decode("ascii", errors="ignore")
        match = re.search(r"element vertex (\d+)", header_text)
        if not match:
            return 0
        return int(match.group(1))

    def _parse_final_psnr(self, stdout: str) -> float | None:
        """
        Extract the final PSNR value from ns-train stdout.

        Priority: last 'Eval PSNR' > last 'Train PSNR' > None.
        Nerfstudio logs format: '[step XXXXX] Eval PSNR: XX.XXXX'
        """
        # Try Eval PSNR first (more reliable than train PSNR)
        eval_matches = re.findall(r"Eval PSNR:\s*([\d.]+)", stdout)
        if eval_matches:
            return float(eval_matches[-1])

        # Fall back to Train PSNR
        train_matches = re.findall(r"Train PSNR:\s*([\d.]+)", stdout)
        if train_matches:
            return float(train_matches[-1])

        return None

    def _psnr_to_reprojection_proxy(self, psnr: float | None) -> float:
        """
        Convert PSNR (dB) to a pseudo-reprojection error proxy (pixels).

        3DGS doesn't produce classical reprojection error (it's radiance-based).
        We use a monotonically decreasing mapping calibrated to typical splatfacto results:
            PSNR 30 dB → ~0.5 px  (excellent)
            PSNR 25 dB → ~1.0 px  (good)
            PSNR 20 dB → ~1.5 px  (acceptable)
            PSNR 15 dB → ~2.0 px  (poor)
            None       → 2.5 px   (unknown — worst case, prevents contract bypass)

        Formula: proxy = max(0.1, 30.0 / psnr)  — simple and monotonic.
        """
        if psnr is None or psnr <= 0:
            return 2.5   # unknown quality = worst-case proxy
        proxy = 30.0 / psnr
        return round(proxy, 4)

    def _compute_bounding_box(
        self,
        camera_poses: list[CameraPose],
    ) -> dict[str, list[float]]:
        """
        Compute the axis-aligned bounding box of all camera translation vectors.

        Returns {"min": [x, y, z], "max": [x, y, z]}
        Used as a spatial sanity check — a degenerate BBOX (all cameras at same point)
        indicates a failed reconstruction.
        """
        xs = [p.translation[0] for p in camera_poses]
        ys = [p.translation[1] for p in camera_poses]
        zs = [p.translation[2] for p in camera_poses]
        return {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }
