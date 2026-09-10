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
        """True only when *usable* weights exist.

        This used to return True whenever torch imported, while ``_load``
        built the network with ``weights=None`` -- i.e. randomly initialised.
        The backend therefore reported itself available and returned an argmax
        over random logits. Because masking runs BEFORE matching, those random
        masks delete real image content from the reconstruction, so the failure
        was silent and destructive rather than merely useless.
        """
        import os
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
        except Exception:
            return False
        ckpt = os.environ.get("DRISHTI_SEG_WEIGHTS")
        return bool(ckpt and os.path.exists(ckpt))

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
        if not (ckpt and os.path.exists(ckpt)):
            raise RuntimeError(
                "TorchvisionSemanticMask has no weights: set DRISHTI_SEG_WEIGHTS "
                "to a local checkpoint, or use the 'maskrcnn' backend, which "
                "carries its own pretrained weights. Refusing to run an "
                "untrained network -- its masks would be random and would "
                "silently delete real image content before matching.")
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


class MaskRCNNDynamicMask(MaskBackend):
    """Instance segmentation of dynamic objects (doc stage 2, "Mask-Before-Match").

    The architecture document names YOLOv8-Seg or FastSAM. Both are
    Ultralytics, licensed **AGPL-3.0** -- a network-copyleft licence that would
    propagate to this entire codebase on distribution. This project already
    refuses SuperPoint over a non-commercial clause (see ``features.py``), and
    AGPL is the stronger constraint of the two, so the same rule applies.
    torchvision's Mask R-CNN is BSD-3, carries COCO-pretrained weights, and
    detects every dynamic class the document lists -- people, cars, trucks,
    buses, motorcycles, boats, trains and animals. Recorded as D-034.

    Instance segmentation rather than semantic: per-object masks come with
    per-object scores, so a confidence threshold is meaningful and a single
    uncertain detection cannot mask a whole class of pixels.
    """

    name = "maskrcnn"
    #: COCO indices for things that move. Index 0 is background.
    _DYNAMIC_COCO = {
        1,   # person
        2, 3, 4, 6, 7, 8, 9,        # bicycle, car, motorcycle, bus, train, truck, boat
        16, 17, 18, 19, 20, 21, 22, 23, 24, 25,   # animals: bird..giraffe
    }

    def __init__(self, score_thr: float = 0.5, mask_thr: float = 0.5,
                 dilate: int = 11, max_side: int = 1024,
                 max_instance_frac: float = 0.02):
        self.score_thr = score_thr
        self.mask_thr = mask_thr
        self.dilate = dilate
        self.max_side = max_side
        #: Reject any single instance covering more than this fraction of the
        #: frame. A COCO detector on nadir aerial imagery produces *confident*
        #: false positives on large elongated static structures: measured on a
        #: school roof, "train" at score 0.74 covering 46.8 % of the frame.
        #: Because masking runs before matching, that silently deleted the
        #: primary structure the reconstruction exists to recover.
        #:
        #: The threshold is measured, not guessed. Over 322 dynamic-class
        #: instances across all real footage in this repo, genuine objects
        #: (car/person/truck/motorcycle/bicycle) reach only 0.52 % of frame at
        #: p90, while *every* instance above 5 % was a "train" (10) or "boat"
        #: (8) hallucinated on a roof or facade. 2 % sits an order of magnitude
        #: above real objects and an order below the false positives.
        self.max_instance_frac = max_instance_frac
        self._model = None
        #: Instances rejected by the area cap, for reporting.
        self.rejected_large = 0

    @staticmethod
    def _weights_cached() -> bool:
        """Are the pretrained weights already on disk?

        Availability must not depend on a network call: a backend that reports
        itself available and then blocks on a 180 MB download inside the
        pipeline is a worse failure than one that declines.
        """
        try:
            import os
            import torch
            from torchvision.models.detection import (
                MaskRCNN_ResNet50_FPN_V2_Weights as W)
            url = W.DEFAULT.url
            fn = os.path.basename(url)
            return os.path.exists(os.path.join(torch.hub.get_dir(),
                                               "checkpoints", fn))
        except Exception:
            return False

    def is_available(self) -> bool:
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
        except Exception:
            return False
        return self._weights_cached()

    @classmethod
    def prefetch(cls):
        """Download the weights once, outside any reconstruction run."""
        from torchvision.models.detection import (
            maskrcnn_resnet50_fpn_v2, MaskRCNN_ResNet50_FPN_V2_Weights as W)
        maskrcnn_resnet50_fpn_v2(weights=W.DEFAULT)
        return cls._weights_cached()

    def _load(self):
        if self._model is not None:
            return
        import os
        import torch
        from torchvision.models.detection import (
            maskrcnn_resnet50_fpn_v2, MaskRCNN_ResNet50_FPN_V2_Weights as W)
        pref = os.environ.get("DRISHTI_DEVICE", "").lower()
        use_cuda = (pref == "cuda") or (pref != "cpu" and torch.cuda.is_available())
        self._device = torch.device("cuda" if use_cuda else "cpu")
        self._model = maskrcnn_resnet50_fpn_v2(weights=W.DEFAULT)
        self._model.eval().to(self._device)
        self._torch = torch

    def mask(self, prev_bgr, cur_bgr) -> np.ndarray:
        """Return 255 where pixels may be used, 0 where a dynamic object is."""
        self._load()
        torch = self._torch
        h, w = cur_bgr.shape[:2]
        # Detect at bounded resolution, then upsample the mask: detection
        # quality saturates well below drone-frame resolution while cost does
        # not, and the mask is dilated afterwards regardless.
        scale = min(1.0, self.max_side / max(h, w))
        img = cur_bgr if scale >= 1.0 else cv2.resize(
            cur_bgr, (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = torch.from_numpy(rgb).permute(2, 0, 1).to(self._device)
        with torch.no_grad():
            out = self._model([x])[0]

        dh, dw = img.shape[:2]
        dyn = np.zeros((dh, dw), np.uint8)
        labels = out["labels"].cpu().numpy()
        scores = out["scores"].cpu().numpy()
        masks = out["masks"].cpu().numpy()[:, 0]
        frame_px = float(dh * dw)
        for lab, sc, m in zip(labels, scores, masks):
            if sc < self.score_thr or int(lab) not in self._DYNAMIC_COCO:
                continue
            inst = (m >= self.mask_thr)
            if inst.sum() / frame_px > self.max_instance_frac:
                # implausibly large for a dynamic object seen from a drone
                self.rejected_large += 1
                continue
            dyn |= inst.astype(np.uint8)
        dyn *= 255
        if scale < 1.0:
            dyn = cv2.resize(dyn, (w, h), interpolation=cv2.INTER_NEAREST)
        if self.dilate > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.dilate, self.dilate))
            dyn = cv2.dilate(dyn, k)
        keep = np.full((h, w), 255, np.uint8)
        keep[dyn > 0] = 0
        return keep


def get_backend(name: str = "optical_flow") -> tuple[MaskBackend, str | None]:
    """Return (backend, warning).  Falls back gracefully."""
    if name in ("maskrcnn", "instance", "yolo", "fastsam"):
        # 'yolo'/'fastsam' are accepted as aliases and served by Mask R-CNN:
        # the Ultralytics models the architecture document names are AGPL-3.0
        # (see MaskRCNNDynamicMask and D-034).
        b = MaskRCNNDynamicMask()
        alias = None
        if name in ("yolo", "fastsam"):
            alias = (f"'{name}' is AGPL-3.0 (Ultralytics); using the BSD-3 "
                     "Mask R-CNN backend instead, which covers the same "
                     "dynamic classes")
        if b.is_available():
            return b, alias
        return OpticalFlowMask(), (
            "Mask R-CNN weights are not cached; run "
            "MaskRCNNDynamicMask.prefetch() once with network access. "
            "Using optical-flow residual masking instead."
            + (" " + alias if alias else ""))
    if name in ("semantic", "torchvision"):
        b = TorchvisionSemanticMask()
        if b.is_available():
            return b, None
        return OpticalFlowMask(), (
            "semantic backend has no weights (set DRISHTI_SEG_WEIGHTS); using "
            "optical-flow residual masking instead")
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
