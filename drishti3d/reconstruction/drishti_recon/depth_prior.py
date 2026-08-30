"""Monocular depth-prior densification (Depth Anything V2).

The single-pass moat.  A single linear drone fly-over gives classical SfM tiny
parallax and no loop closure, so textureless regions (asphalt, rooftops, water)
fail feature matching and the cloud comes out sparse and holey.  We fuse a
learned monocular depth prior with the *classical* cameras:

  1. predict an affine-invariant depth (disparity) for each keyframe,
  2. fit its scale+shift to the sparse SfM points that ARE visible in that frame
     (so the learned depth inherits real metric scale, not a guess),
  3. back-project a pixel grid into the metric reconstruction frame.

Every densified point is tagged ``AI_ASSISTED`` (never OBSERVED): the trust map
draws it in a distinct colour and measurements exclude it by default.  This is
the honest answer to "how do we know the AI didn't hallucinate that wall?".

CPU-capable but GPU-accelerated: the model runs on CUDA when available (set
``DRISHTI_DEVICE=cpu`` to force CPU).  Weights download once from the HF hub; set
``DRISHTI_DEPTH_MODEL`` to pin a different checkpoint or a local path.
"""
from __future__ import annotations

import cv2  # noqa: F401  -- import BEFORE torch to avoid a Windows cv2/torch DLL clash
import os
import numpy as np

_MODEL = None
_PROC = None
_DEVICE = None


def _pick_device() -> str:
    pref = os.environ.get("DRISHTI_DEVICE", "").lower()
    if pref in ("cpu", "cuda"):
        return pref
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def is_available() -> bool:
    """True if transformers + torch are importable (weights fetch lazily)."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def _load(device: str):
    global _MODEL, _PROC, _DEVICE
    if _MODEL is not None and _DEVICE == device:
        return _MODEL, _PROC
    import torch  # noqa: F401
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    mid = os.environ.get("DRISHTI_DEPTH_MODEL",
                         "depth-anything/Depth-Anything-V2-Small-hf")
    _PROC = AutoImageProcessor.from_pretrained(mid)
    _MODEL = AutoModelForDepthEstimation.from_pretrained(mid).to(device).eval()
    _DEVICE = device
    return _MODEL, _PROC


def _predict_disparity(img_rgb: np.ndarray, device: str) -> np.ndarray:
    """Return the model's affine-invariant depth at image resolution.

    Depth Anything V2 (relative) emits a disparity-like map: larger = closer.
    We keep it as-is and let the per-frame affine fit resolve scale/shift/sign.
    """
    import torch
    model, proc = _load(device)
    inp = proc(images=img_rgb, return_tensors="pt").to(device)
    with torch.no_grad():
        d = model(**inp).predicted_depth
    d = torch.nn.functional.interpolate(
        d.unsqueeze(1), size=img_rgb.shape[:2], mode="bicubic",
        align_corners=False)[0, 0]
    return d.float().cpu().numpy()


def _robust_affine(x: np.ndarray, y: np.ndarray, iters: int = 3):
    """Fit y ~ a*x + b, re-weighting to reject outliers (IRLS-lite)."""
    if len(x) < 8:
        return None, None
    w = np.ones_like(x)
    a = b = 0.0
    for _ in range(iters):
        W = np.sqrt(w)
        A = np.stack([x * W, W], 1)
        sol, *_ = np.linalg.lstsq(A, y * W, rcond=None)
        a, b = float(sol[0]), float(sol[1])
        r = np.abs(a * x + b - y)
        s = np.median(r) + 1e-9
        w = 1.0 / (1.0 + (r / (2.0 * s)) ** 2)   # Cauchy weights
    return a, b


def densify(recon, kf_frames, *, device: str | None = None, pixel_stride: int = 8,
            min_anchors: int = 20, max_points_per_frame: int = 45000,
            max_total: int = 500000, progress=None):
    """Densify a classical reconstruction with a monocular depth prior.

    Returns (points_local (M,3), colors_rgb (M,3) uint8, warnings) in the SAME
    reconstruction frame as ``recon.points`` -- the caller applies the geo Sim(3).
    """
    device = device or _pick_device()
    K = np.asarray(recon.K, float)
    Kinv = np.linalg.inv(K)
    pts_w = recon.points
    warns: list[str] = []
    out_pts: list[np.ndarray] = []
    out_cols: list[np.ndarray] = []
    used = 0
    n_cam = len(recon.cameras)
    n_fit = 0

    for ci, cam in enumerate(recon.cameras):
        if progress:
            progress(ci / max(1, n_cam))
        img = kf_frames[cam.frame_index]
        H, W = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # sparse anchors: project recon points into this camera
        Xc = (cam.R @ pts_w.T + cam.t.reshape(3, 1)).T          # (N,3) cam frame
        z = Xc[:, 2]
        front = z > 1e-6
        if front.sum() < min_anchors:
            continue
        proj = (K @ Xc[front].T).T
        u = proj[:, 0] / proj[:, 2]
        v = proj[:, 1] / proj[:, 2]
        zc = z[front]
        inb = (u >= 0) & (u <= W - 1) & (v >= 0) & (v <= H - 1)
        if inb.sum() < min_anchors:
            continue
        ui = u[inb].astype(int)
        vi = v[inb].astype(int)
        zc = zc[inb]

        disp = _predict_disparity(rgb, device)                  # (H,W)
        d_anchor = disp[vi, ui]
        # fit inverse-depth (1/z) ~ a*disparity + b  (both live in disparity space)
        a, b = _robust_affine(d_anchor, 1.0 / zc)
        if a is None:
            continue
        n_fit += 1

        # back-project a strided pixel grid
        ys, xs = np.mgrid[0:H:pixel_stride, 0:W:pixel_stride]
        ys = ys.ravel(); xs = xs.ravel()
        inv_z = a * disp[ys, xs] + b
        good = inv_z > 1e-3                                      # in front of camera
        if not good.any():
            continue
        zpix = 1.0 / inv_z[good]
        xu = xs[good]; yv = ys[good]
        # reject wild extrapolation beyond the anchored depth range
        zlo = max(1e-3, np.percentile(zc, 1) * 0.5)
        zhi = np.percentile(zc, 99) * 2.5
        keep = (zpix > zlo) & (zpix < zhi)
        zpix = zpix[keep]; xu = xu[keep]; yv = yv[keep]
        if len(zpix) == 0:
            continue
        if len(zpix) > max_points_per_frame:
            sel = np.random.default_rng(ci).choice(len(zpix), max_points_per_frame,
                                                   replace=False)
            zpix = zpix[sel]; xu = xu[sel]; yv = yv[sel]

        pix = np.stack([xu, yv, np.ones_like(xu)], 1).astype(float)   # (M,3)
        Xc2 = (Kinv @ pix.T).T * zpix[:, None]                        # cam frame
        Xw = (cam.R.T @ (Xc2 - cam.t.reshape(1, 3)).T).T             # world/recon
        out_pts.append(Xw)
        out_cols.append(rgb[yv, xu])
        used += len(Xw)
        if used >= max_total:
            warns.append(f"depth densification capped at {max_total} points")
            break

    if not out_pts:
        return (np.zeros((0, 3)), np.zeros((0, 3), np.uint8),
                ["depth densification produced no points (too few anchors)"])
    warns.append(f"depth prior densified {n_fit}/{n_cam} keyframes on {device} "
                 f"-> {used} AI-assisted points")
    return np.vstack(out_pts), np.vstack(out_cols).astype(np.uint8), warns
