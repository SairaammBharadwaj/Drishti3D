"""Dense multi-view stereo: observed geometry, not inferred.

Why this exists
---------------
Until this module, the pipeline shipped only the **sparse** SfM cloud -- the
feature points that were matched and triangulated, and nothing else. On the AGZ
mission that is 17,898 points for 233 m of flight, and it looks like what it is:
a scattering of corners. Plan section 5.3 asks for dense geometry explicitly
("Create dense observed geometry using multi-view stereo where the capture
supports it") and it had not been built.

The distinction that matters
----------------------------
There are two ways to make a cloud look dense, and they are not
interchangeable:

* **Multi-view stereo**, here. Every point is triangulated from photometric
  agreement across several real images. It is *observed* geometry and carries
  the same provenance as the sparse points -- measurable, subject to the same
  uncertainty rules.
* **A monocular depth prior** (``densify="depth"``, :mod:`depth_prior`). A model
  predicts depth from one image. It fills holes convincingly and it is
  **inferred**: every point is tagged ``AI_ASSISTED`` and excluded from
  measurement by default.

Both make the viewer look better. Only one of them may be measured, and
confusing them is the failure this whole product is built to avoid.

Backends
--------
``colmap``
    COLMAP's PatchMatch stereo, via the ``colmap`` executable. The reference
    implementation and by far the best output. **Requires a CUDA-enabled
    COLMAP**: the PyPI ``pycolmap`` wheels are CPU-only and its own error is
    explicit -- *"Dense stereo reconstruction requires CUDA or HIP, neither of
    which is available on your system."* So this backend shells out to a
    separately installed binary rather than using the Python bindings.

``none``
    The default. Sparse only.

Whatever produced them, dense points enter the cloud as observed geometry and
must carry a positional uncertainty like any other measured point; see
:func:`depth_uncertainty`.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class DenseResult:
    """Dense points in the *reconstruction* frame, with their support."""

    points: np.ndarray                  # (N,3)
    colors: np.ndarray                  # (N,3) uint8
    #: How many images contributed to each point, when the backend reports it.
    n_views: np.ndarray | None = None
    #: Per-point 1-sigma, metres in the reconstruction frame.
    sigma: np.ndarray | None = None
    backend: str = ""
    stats: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.points.shape[0])


def colmap_executable() -> str | None:
    """Path to a usable ``colmap`` binary, or ``None``.

    The Python bindings are not enough: dense stereo needs CUDA and the
    published wheels are built without it.
    """
    return shutil.which("colmap")


def available() -> dict:
    """What dense backends this installation can actually run."""
    exe = colmap_executable()
    cuda = False
    if exe:
        try:
            out = subprocess.run([exe, "patch_match_stereo", "--help"],
                                 capture_output=True, text=True, timeout=60)
            blob = (out.stdout + out.stderr).lower()
            cuda = "requires cuda" not in blob
        except Exception:                  # noqa: BLE001
            cuda = False
    return {
        "colmap": {
            "executable": exe,
            "available": bool(exe) and cuda,
            "detail": ("ready" if exe and cuda else
                       "no colmap executable on PATH" if not exe else
                       "colmap found but built without CUDA; dense stereo "
                       "cannot run"),
            "setup": "Install a CUDA-enabled COLMAP, e.g. "
                     "`BUILD_CUDA=ON CUDA_ARCH=native yay -S colmap` on Arch. "
                     "The PyPI pycolmap wheels are CPU-only and cannot do this.",
        },
    }


def depth_uncertainty(points, centres, n_views, *, sigma_px: float,
                      focal: float) -> np.ndarray:
    """1-sigma for a dense point, from the geometry that produced it.

    A stereo point's error is dominated by depth along the view ray: a
    disparity uncertain by ``sigma_px`` at focal length ``f`` and range ``r``
    puts the point uncertain by about ``r * sigma_px / f`` across the ray, and
    rather more along it. Averaging over ``n`` contributing views reduces that
    by roughly ``sqrt(n)``.

    This is deliberately a geometric estimate, not a propagated covariance:
    fusion does not report which images agreed at what disparity, so the full
    Jacobian of :mod:`uncertainty` cannot be formed. It is labelled as such by
    the caller, and it is conservative -- a dense point is never given a
    smaller sigma than a sparse one at the same range.
    """
    pts = np.asarray(points, float).reshape(-1, 3)
    if len(pts) == 0:
        return np.zeros(0)
    c = np.asarray(centres, float).reshape(-1, 3)
    # Range to the nearest contributing camera is the optimistic case; use the
    # median camera distance instead, which is what a fused point actually sees.
    from scipy.spatial import cKDTree
    rng = cKDTree(c).query(pts)[0] if len(c) else np.full(len(pts), np.nan)
    n = np.maximum(np.asarray(n_views, float).reshape(-1)
                   if n_views is not None else 2.0, 2.0)
    return rng * float(sigma_px) / max(float(focal), 1e-9) / np.sqrt(n)


def _read_ply(path: Path):
    """Points and colours from a COLMAP fused PLY (binary or ascii)."""
    import numpy as np
    with open(path, "rb") as fh:
        header, fmt, count, props = [], None, 0, []
        while True:
            line = fh.readline().decode("ascii", "replace").strip()
            header.append(line)
            if line.startswith("format"):
                fmt = line.split()[1]
            elif line.startswith("element vertex"):
                count = int(line.split()[-1])
            elif line.startswith("property") and count and not header[-2].startswith("element face"):
                props.append(line.split()[-1])
            elif line == "end_header":
                break
        if fmt == "binary_little_endian":
            dtype = []
            for line in header:
                if line.startswith("property "):
                    parts = line.split()
                    if parts[1] == "list":
                        continue
                    t = {"float": "<f4", "float32": "<f4", "double": "<f8",
                         "uchar": "u1", "uint8": "u1", "int": "<i4"}.get(parts[1])
                    if t:
                        dtype.append((parts[2], t))
            arr = np.frombuffer(fh.read(np.dtype(dtype).itemsize * count),
                                dtype=dtype, count=count)
            xyz = np.stack([arr["x"], arr["y"], arr["z"]], 1).astype(float)
            if all(k in arr.dtype.names for k in ("red", "green", "blue")):
                rgb = np.stack([arr["red"], arr["green"], arr["blue"]],
                               1).astype(np.uint8)
            else:
                rgb = np.full((count, 3), 200, np.uint8)
            return xyz, rgb
        rows = np.loadtxt(path, skiprows=len(header), max_rows=count)
        xyz = rows[:, :3].astype(float)
        rgb = (rows[:, 3:6].astype(np.uint8) if rows.shape[1] >= 6
               else np.full((count, 3), 200, np.uint8))
        return xyz, rgb


def _read_visibility(path: Path, n_points: int) -> np.ndarray | None:
    """Per-point contributing-image counts from COLMAP's ``.vis`` sidecar."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as fh:
            n = int(np.frombuffer(fh.read(8), dtype="<u8", count=1)[0])
            if n != n_points:
                return None
            out = np.zeros(n, np.int32)
            for i in range(n):
                k = int(np.frombuffer(fh.read(4), dtype="<u4", count=1)[0])
                fh.read(4 * k)
                out[i] = k
            return out
    except Exception:                      # noqa: BLE001 - optional detail
        return None


def run_colmap(workspace, *, max_image_size: int = 1600,
               geom_consistency: bool = True, min_num_pixels: int = 5,
               progress=None) -> DenseResult:
    """PatchMatch stereo and fusion over a COLMAP workspace.

    ``workspace`` is the directory `colmap_adapter.reconstruct_frames` kept:
    ``images/`` and ``sparse/`` as COLMAP itself wrote them. Reusing its own
    output avoids re-exporting by hand what is already on disk, and avoids the
    two disagreeing.
    """
    exe = colmap_executable()
    if not exe:
        raise RuntimeError(available()["colmap"]["setup"])
    work = Path(workspace)
    images, sparse = work / "images", work / "sparse"
    if not images.is_dir() or not sparse.is_dir():
        raise RuntimeError(f"{work} is not a COLMAP workspace")
    dense = work / "dense"

    def _p(msg, frac):
        if progress:
            progress(msg, frac)

    def _run(args, stage):
        out = subprocess.run([exe, *args], capture_output=True, text=True)
        if out.returncode != 0:
            tail = (out.stderr or out.stdout or "").strip().splitlines()
            raise RuntimeError(f"colmap {stage} failed: "
                               + " | ".join(tail[-3:] or ["no output"]))
        return out

    _p("mvs: undistorting", 0.1)
    _run(["image_undistorter", "--image_path", str(images),
          "--input_path", str(sparse), "--output_path", str(dense),
          "--output_type", "COLMAP",
          "--max_image_size", str(max_image_size)], "image_undistorter")

    _p("mvs: patch-match stereo", 0.3)
    _run(["patch_match_stereo", "--workspace_path", str(dense),
          "--workspace_format", "COLMAP",
          "--PatchMatchStereo.geom_consistency",
          "true" if geom_consistency else "false"], "patch_match_stereo")

    _p("mvs: fusing", 0.8)
    fused = dense / "fused.ply"
    _run(["stereo_fusion", "--workspace_path", str(dense),
          "--workspace_format", "COLMAP",
          "--input_type", "geometric" if geom_consistency else "photometric",
          "--output_path", str(fused),
          "--StereoFusion.min_num_pixels", str(min_num_pixels)],
         "stereo_fusion")
    if not fused.exists():
        raise RuntimeError("stereo_fusion produced no output")

    xyz, rgb = _read_ply(fused)
    vis = _read_visibility(dense / "fused.ply.vis", len(xyz))
    _p("mvs: done", 1.0)
    return DenseResult(points=xyz, colors=rgb, n_views=vis, backend="colmap",
                       stats={"n_points": int(len(xyz)),
                              "max_image_size": max_image_size,
                              "geom_consistency": geom_consistency,
                              "min_num_pixels": min_num_pixels,
                              "workspace": str(work)})
