"""
Infrastructure Layer — NerfstudioSplatfactoAdapter

Concrete adapter implementing GaussianTrainerPort using Nerfstudio's splatfacto
trainer as a local subprocess, optimized for Apple Silicon (MPS/Metal).

Canonical location: core/spatial_reconstruction/adapters/nerfstudio_splatfacto_adapter.py

Clean Architecture constraint:
  - This file is the ONLY place in the codebase that knows about Nerfstudio.
  - The domain and application layers must NEVER import from here.
"""
import json
import math
import re
import subprocess
from pathlib import Path

from core.spatial_reconstruction.domain.ports.i_spatial_reconstruction_ports import GaussianTrainerPort
from core.spatial_reconstruction.domain.model import CameraPose, SplatScene


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

    Default training config targets Apple Silicon M3 Pro (8GB GPU / 18GB Unified Memory):
        - max_num_iterations=15_000  (reduced from default 30k for fast iteration)
        - Batch size managed by Nerfstudio automatically for MPS memory limits
    """

    _DASHCAM_FL_X: float = 800.0
    _DASHCAM_FL_Y: float = 800.0
    _DASHCAM_CX: float = 960.0
    _DASHCAM_CY: float = 540.0
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
        self._output_dir = Path(output_dir)
        self._binary = nerfstudio_binary
        self._max_iters = max_num_iterations
        self._fl_x = fl_x or self._DASHCAM_FL_X
        self._fl_y = fl_y or self._DASHCAM_FL_Y

    # ---------------------------------------------------------------------------
    # GaussianTrainerPort implementation
    # ---------------------------------------------------------------------------

    def train(self, camera_poses: list[CameraPose], scene_id: str) -> SplatScene:
        if not camera_poses:
            raise ValueError(
                "camera_poses cannot be empty — Nerfstudio requires at least one registered view."
            )

        workspace = self._output_dir / scene_id
        workspace.mkdir(parents=True, exist_ok=True)

        transforms_path = workspace / "transforms.json"
        self._write_transforms_json(camera_poses, transforms_path)

        stdout = self._run_nerfstudio(workspace, scene_id)

        splat_ply = self._find_splat_ply(workspace, scene_id)

        ply_bytes = splat_ply.read_bytes()
        header = ply_bytes[:2048]
        num_gaussians = self._count_gaussians_from_ply_header(header)

        psnr = self._parse_final_psnr(stdout)
        reprojection_proxy = self._psnr_to_reprojection_proxy(psnr)

        bounding_box = self._compute_bounding_box(camera_poses)
        point_cloud_density = min(1.0, num_gaussians / 500_000)

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
        qw, qx, qy, qz = pose.quaternion
        tx, ty, tz = pose.translation

        R = [
            [1 - 2*(qy**2 + qz**2),   2*(qx*qy - qz*qw),   2*(qx*qz + qy*qw)],
            [2*(qx*qy + qz*qw),        1 - 2*(qx**2 + qz**2), 2*(qy*qz - qx*qw)],
            [2*(qx*qz - qy*qw),        2*(qy*qz + qx*qw),   1 - 2*(qx**2 + qy**2)],
        ]

        Rt = [[R[j][i] for j in range(3)] for i in range(3)]

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
        cmd = [
            self._binary, "splatfacto",
            "--data", str(workspace),
            "--output-dir", str(self._output_dir),
            "--experiment-name", scene_id,
            "--max-num-iterations", str(self._max_iters),
            "--pipeline.model.background-color", "random",
            "--pipeline.datamanager.num-processes", "0",
            "--pipeline.model.use-gradient-scaling", "True",
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
        splatfacto_dir = self._output_dir / scene_id / "splatfacto"
        if not splatfacto_dir.exists():
            raise NerfstudioTrainingError(
                f"Nerfstudio output directory not found: {splatfacto_dir}. "
                "Training may have failed silently."
            )
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
        header_text = header_bytes.decode("ascii", errors="ignore")
        match = re.search(r"element vertex (\d+)", header_text)
        if not match:
            return 0
        return int(match.group(1))

    def _parse_final_psnr(self, stdout: str) -> float | None:
        eval_matches = re.findall(r"Eval PSNR:\s*([\d.]+)", stdout)
        if eval_matches:
            return float(eval_matches[-1])

        train_matches = re.findall(r"Train PSNR:\s*([\d.]+)", stdout)
        if train_matches:
            return float(train_matches[-1])

        return None

    def _psnr_to_reprojection_proxy(self, psnr: float | None) -> float:
        if psnr is None or psnr <= 0:
            return 2.5
        proxy = 30.0 / psnr
        return round(proxy, 4)

    def _compute_bounding_box(
        self,
        camera_poses: list[CameraPose],
    ) -> dict[str, list[float]]:
        xs = [p.translation[0] for p in camera_poses]
        ys = [p.translation[1] for p in camera_poses]
        zs = [p.translation[2] for p in camera_poses]
        return {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }
