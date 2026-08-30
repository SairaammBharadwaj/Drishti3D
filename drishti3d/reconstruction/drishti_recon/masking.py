"""Dynamic-object masking (pluggable).

Default implementation uses optical-flow residual after global-motion
compensation to flag independently moving regions -- it needs no downloaded
weights and runs on CPU.  An optional torchvision semantic segmentation model
can be enabled for humans/vehicles/animals.  If a requested backend is
unavailable the pipeline continues with a clear warning (never a crash).

Masks follow OpenCV convention: 255 = keep (static), 0 = ignore (dynamic).
"""
from __future__ import annotations

import numpy as np
import cv2


class MaskBackend:
    name = "base"

    def is_available(self) -> bool:
        return True

    def mask(self, prev_bgr, cur_bgr) -> np.ndarray:
        raise NotImplementedError


class OpticalFlowMask(MaskBackend):
    """Flag pixels whose flow disagrees with the dominant (camera) flow."""

    name = "optical_flow_residual"

    def __init__(self, residual_thresh: float = 6.0, dilate: int = 9,
                 min_area_frac: float = 0.002):
        # Higher threshold + a minimum connected-component area so that scene
        # PARALLAX (e.g. a tall building seen from a low pass) is not mistaken
        # for motion; only large, coherent moving blobs are masked.
        self.residual_thresh = residual_thresh
        self.dilate = dilate
        self.min_area_frac = min_area_frac

    def mask(self, prev_bgr, cur_bgr) -> np.ndarray:
        h, w = cur_bgr.shape[:2]
        if prev_bgr is None:
            return np.full((h, w), 255, np.uint8)
        g0 = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
        g1 = cv2.cvtColor(cur_bgr, cv2.COLOR_BGR2GRAY)
        flow = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 21, 3, 5, 1.2, 0)
        # estimate a global affine motion and subtract it
        ys, xs = np.mgrid[0:h:16, 0:w:16]
        pts0 = np.stack([xs.ravel(), ys.ravel()], 1).astype(np.float32)
        fx = flow[ys, xs, 0].ravel()
        fy = flow[ys, xs, 1].ravel()
        pts1 = pts0 + np.stack([fx, fy], 1)
        M, _ = cv2.estimateAffinePartial2D(pts0, pts1, method=cv2.RANSAC)
        keep = np.full((h, w), 255, np.uint8)
        if M is None:
            return keep
        yy, xx = np.mgrid[0:h, 0:w]
        pred_x = M[0, 0] * xx + M[0, 1] * yy + M[0, 2] - xx
        pred_y = M[1, 0] * xx + M[1, 1] * yy + M[1, 2] - yy
        resid = np.hypot(flow[..., 0] - pred_x, flow[..., 1] - pred_y)
        dyn = (resid > self.residual_thresh).astype(np.uint8) * 255
        # drop small/scattered residual blobs (parallax speckle)
        min_area = int(self.min_area_frac * h * w)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(dyn, 8)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] < min_area:
                dyn[labels == i] = 0
        if self.dilate > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.dilate, self.dilate))
            dyn = cv2.dilate(dyn, k)
        keep[dyn > 0] = 0
        return keep


class TorchvisionSemanticMask(MaskBackend):
    """Optional: mask people/vehicles/animals via a torchvision seg model."""

    name = "torchvision_semantic"
    _DYNAMIC_CLASSES = {15, 8, 7, 6, 14, 13, 12, 19}  # VOC person/animals/vehicles

    def __init__(self, dilate: int = 11):
        self.dilate = dilate
        self._model = None

    def is_available(self) -> bool:
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self):
        if self._model is not None:
            return
        import os
        import torch
        from torchvision.models.segmentation import (
            deeplabv3_mobilenet_v3_large)
        # Device: honour DRISHTI_DEVICE ("cpu"/"cuda"), else use CUDA if present.
        pref = os.environ.get("DRISHTI_DEVICE", "").lower()
        use_cuda = (pref == "cuda") or (pref != "cpu" and torch.cuda.is_available())
        self._device = torch.device("cuda" if use_cuda else "cpu")
        # weights=None -> no network download; runs untrained unless user
        # provides a local checkpoint via DRISHTI_SEG_WEIGHTS.
        self._model = deeplabv3_mobilenet_v3_large(weights=None, num_classes=21)
        ckpt = os.environ.get("DRISHTI_SEG_WEIGHTS")
        if ckpt and os.path.exists(ckpt):
            self._model.load_state_dict(torch.load(ckpt, map_location="cpu"))
        self._model.eval().to(self._device)
        self._torch = torch

    def mask(self, prev_bgr, cur_bgr) -> np.ndarray:
        self._load()
        import torch
        h, w = cur_bgr.shape[:2]
        rgb = cv2.cvtColor(cur_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(self._device)
        with torch.no_grad():
            out = self._model(x)["out"][0].argmax(0).cpu().numpy()
        keep = np.full((h, w), 255, np.uint8)
        dyn = np.isin(out, list(self._DYNAMIC_CLASSES)).astype(np.uint8) * 255
        if self.dilate > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.dilate, self.dilate))
            dyn = cv2.dilate(dyn, k)
        keep[dyn > 0] = 0
        return keep


def get_backend(name: str = "optical_flow") -> tuple[MaskBackend, str | None]:
    """Return (backend, warning).  Falls back gracefully."""
    if name in ("semantic", "torchvision"):
        b = TorchvisionSemanticMask()
        if b.is_available():
            return b, None
        return OpticalFlowMask(), ("torchvision unavailable; using optical-flow "
                                   "residual masking instead")
    if name in ("none", "off"):
        return _NullMask(), None
    return OpticalFlowMask(), None


class _NullMask(MaskBackend):
    name = "none"

    def mask(self, prev_bgr, cur_bgr):
        h, w = cur_bgr.shape[:2]
        return np.full((h, w), 255, np.uint8)


def compute_masks(frames, backend_name: str = "optical_flow"):
    """frames: ordered list of bgr images. Returns (masks, backend_name, warning)."""
    backend, warn = get_backend(backend_name)
    masks = []
    prev = None
    for img in frames:
        masks.append(backend.mask(prev, img))
        prev = img
    return masks, backend.name, warn
