"""Pluggable feature detection and matching backends.

Why an adapter rather than a swap
---------------------------------
The roadmap's requirement for evaluating a learned matcher is that it be compared
against SIFT **on the identical pair graph**, so that any difference is
attributable to the matcher and not to which images happened to be compared. That
rules out forking the reconstruction path: the pair graph, the geometric
verification, the triangulation thresholds and the registration order all have to
stay byte-identical while only feature extraction and descriptor matching change.

So a backend here owns exactly two operations -- detect keypoints in one image,
and match two descriptor sets -- and nothing else. Everything downstream is shared.

Licensing note
--------------
This matters for a deliverable product and is easy to get wrong. LightGlue's code
is Apache-2.0, but the original **SuperPoint weights are MagicLeap's
non-commercial licence**. The learned backend here therefore defaults to
**DISK** or **ALIKED** (both permissive, both LightGlue-compatible) and refuses
to silently load a non-commercial checkpoint. Every backend reports its licence
in :meth:`FeatureBackend.info` so a run's provenance records what it used.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class BackendInfo:
    name: str
    kind: str                    # classical | learned
    licence: str
    device: str = "cpu"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "licence": self.licence,
                "device": self.device, **self.detail}


class FeatureBackend:
    """Detect keypoints and match descriptors. Subclasses implement both."""

    name = "base"
    kind = "classical"
    licence = "unknown"

    def detect(self, gray, mask=None):
        """Return ``(keypoints_xy (N,2) float32, descriptors)``."""
        raise NotImplementedError

    def match(self, desc1, desc2, kp1=None, kp2=None, shape=None):
        """Return a list of ``(index_in_1, index_in_2)`` putative matches."""
        raise NotImplementedError

    def info(self) -> BackendInfo:
        return BackendInfo(self.name, self.kind, self.licence)


# --------------------------------------------------------------------------- #
# classical
# --------------------------------------------------------------------------- #
class SiftBackend(FeatureBackend):
    """SIFT + brute-force L2 with Lowe's ratio test.

    The reference path. Its behaviour is deliberately unchanged from the original
    inline implementation so that every previously archived benchmark remains
    comparable with new runs.
    """

    name = "sift"
    kind = "classical"
    licence = "Apache-2.0 (OpenCV; SIFT patent expired 2020)"

    def __init__(self, nfeatures: int = 4000, ratio: float = 0.75,
                 contrast_threshold: float = 0.02):
        import cv2
        self.ratio = float(ratio)
        self.nfeatures = int(nfeatures)
        self._sift = cv2.SIFT_create(nfeatures=nfeatures,
                                     contrastThreshold=contrast_threshold)

    def detect(self, gray, mask=None):
        kp, desc = self._sift.detectAndCompute(gray, mask)
        pts = (np.array([k.pt for k in kp], np.float32)
               if kp else np.zeros((0, 2), np.float32))
        return pts, desc

    def match(self, desc1, desc2, kp1=None, kp2=None, shape=None):
        import cv2
        if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
            return []
        bf = cv2.BFMatcher(cv2.NORM_L2)
        knn = bf.knnMatch(desc1, desc2, k=2)
        good = []
        for m_n in knn:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < self.ratio * n.distance:
                good.append((m.queryIdx, m.trainIdx))
        return good

    def info(self) -> BackendInfo:
        return BackendInfo(self.name, self.kind, self.licence, "cpu",
                           {"nfeatures": self.nfeatures, "ratio": self.ratio})


class OrbBackend(FeatureBackend):
    """ORB binary descriptors + Hamming matching.

    Included as a *classical control*, not as a serious competitor to SIFT: it
    exercises the adapter with a genuinely different descriptor type (binary
    rather than float) and a different distance metric, which is what proves the
    abstraction is real rather than SIFT-shaped. It needs no download, so the
    adapter stays testable even where torch is unavailable.

    (AKAZE would have served the same purpose but was removed in OpenCV 5.0,
    which is the version this project pins.)
    """

    name = "orb"
    kind = "classical"
    licence = "Apache-2.0 (OpenCV)"

    def __init__(self, ratio: float = 0.8, nfeatures: int = 4000):
        import cv2
        self.ratio = float(ratio)
        self.nfeatures = int(nfeatures)
        self._orb = cv2.ORB_create(nfeatures=nfeatures)

    def detect(self, gray, mask=None):
        kp, desc = self._orb.detectAndCompute(gray, mask)
        pts = (np.array([k.pt for k in kp], np.float32)
               if kp else np.zeros((0, 2), np.float32))
        return pts, desc

    def match(self, desc1, desc2, kp1=None, kp2=None, shape=None):
        import cv2
        if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
            return []
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        knn = bf.knnMatch(desc1, desc2, k=2)
        good = []
        for m_n in knn:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < self.ratio * n.distance:
                good.append((m.queryIdx, m.trainIdx))
        return good

    def info(self) -> BackendInfo:
        return BackendInfo(self.name, self.kind, self.licence, "cpu",
                           {"ratio": self.ratio, "nfeatures": self.nfeatures})


# --------------------------------------------------------------------------- #
# learned
# --------------------------------------------------------------------------- #
#: Detectors whose published weights carry a licence that permits commercial use.
_PERMISSIVE_DETECTORS = {"disk": "Apache-2.0 (DISK, via kornia)",
                         "aliked": "BSD-3-Clause (ALIKED, via kornia)"}
#: Refused by default: the weights, not the code, are the problem.
_RESTRICTED_DETECTORS = {
    "superpoint": ("MagicLeap SuperPoint weights are licensed for "
                   "non-commercial research use only"),
}


class LightGlueBackend(FeatureBackend):
    """Learned local features matched by LightGlue.

    Detection and matching are both learned, so unlike the classical backends the
    matcher needs the *keypoints*, not only the descriptors -- LightGlue reasons
    about spatial layout. That is why :meth:`match` takes ``kp1``/``kp2`` and the
    image shape; the classical backends simply ignore them.

    ``allow_restricted_licence`` must be set explicitly to load SuperPoint. The
    default is to refuse, because a non-commercial checkpoint quietly baked into a
    deliverable is a licensing problem discovered far too late.
    """

    name = "lightglue"
    kind = "learned"

    def __init__(self, detector: str = "disk", device: str | None = None,
                 max_keypoints: int = 4096,
                 allow_restricted_licence: bool = False):
        detector = detector.lower()
        if detector in _RESTRICTED_DETECTORS and not allow_restricted_licence:
            raise ValueError(
                f"refusing to load '{detector}': {_RESTRICTED_DETECTORS[detector]}. "
                f"Use one of {sorted(_PERMISSIVE_DETECTORS)}, or pass "
                "allow_restricted_licence=True if the terms are acceptable for "
                "your use.")
        try:
            import torch
            import kornia.feature as KF
        except Exception as exc:                       # pragma: no cover
            raise ImportError(
                "the learned matcher needs torch and kornia: "
                "pip install torch kornia") from exc

        self.torch = torch
        self.detector_name = detector
        self.max_keypoints = int(max_keypoints)
        self.licence = _PERMISSIVE_DETECTORS.get(
            detector, "non-commercial (restricted) -- explicitly allowed by caller")
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu"))

        if detector == "disk":
            self._extractor = KF.DISK.from_pretrained("depth").to(self.device).eval()
        elif detector == "aliked":
            self._extractor = KF.ALIKED().to(self.device).eval()
        else:
            self._extractor = KF.SuperPoint().to(self.device).eval()
        self._matcher = KF.LightGlueMatcher(detector).to(self.device).eval()

    def _to_tensor(self, gray):
        """(H,W) or (H,W,3) uint8 -> a (1,3,H,W) float tensor.

        The learned detectors are trained on RGB and reject a single channel, but
        the reconstruction pipeline works in grayscale. Replicating the channel
        keeps the interface identical to the classical backends rather than
        forcing colour frames through every call site.
        """
        arr = np.ascontiguousarray(gray)
        t = self.torch.from_numpy(arr).float() / 255.0
        if t.ndim == 2:                       # (H,W) -> (3,H,W)
            t = t[None].repeat(3, 1, 1)
        elif t.ndim == 3:                     # (H,W,C) -> (C,H,W)
            t = t.permute(2, 0, 1)
            if t.shape[0] == 1:
                t = t.repeat(3, 1, 1)
        return t[None].to(self.device)        # (1,3,H,W)

    def detect(self, gray, mask=None):
        import torch
        with torch.inference_mode():
            img = self._to_tensor(gray)
            if self.detector_name == "disk":
                feats = self._extractor(img, self.max_keypoints,
                                        pad_if_not_divisible=True)[0]
                kpts, desc = feats.keypoints, feats.descriptors
            else:
                out = self._extractor(img)
                # kornia returns a dataclass for ALIKED and a tuple for
                # SuperPoint; normalise rather than assuming one shape.
                if hasattr(out, "keypoints"):
                    kpts, desc = out.keypoints[0], out.descriptors[0]
                elif isinstance(out, (list, tuple)) and len(out) >= 2:
                    kpts, desc = out[0][0], out[1][0]
                else:
                    kpts, desc = out[0].keypoints[0], out[0].descriptors[0]
        pts = kpts.detach().cpu().numpy().astype(np.float32)
        d = desc.detach().cpu().numpy().astype(np.float32)
        # Guard the extractor's output shape. kornia's per-detector return types
        # differ, and a mis-unpacked tensor yields a plausible-looking but
        # meaningless handful of keypoints rather than an error -- which would
        # silently poison a benchmark run labelled as this backend.
        if pts.ndim != 2 or pts.shape[1] != 2 or d.ndim != 2 or len(d) != len(pts):
            raise RuntimeError(
                f"{self.detector_name}: unexpected extractor output "
                f"(keypoints {pts.shape}, descriptors {d.shape}). This backend "
                "is not correctly wired for the installed kornia version.")
        if mask is not None and len(pts):
            # Honour dynamic masks the same way the classical detectors do:
            # a keypoint on a masked (moving) region must not enter the solve.
            ij = np.round(pts[:, ::-1]).astype(int)
            h, w = mask.shape[:2]
            ij[:, 0] = np.clip(ij[:, 0], 0, h - 1)
            ij[:, 1] = np.clip(ij[:, 1], 0, w - 1)
            keep = mask[ij[:, 0], ij[:, 1]] > 0
            pts, d = pts[keep], d[keep]
        return pts, d

    def match(self, desc1, desc2, kp1=None, kp2=None, shape=None):
        import torch
        import kornia.feature as KF
        if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
            return []
        if kp1 is None or kp2 is None or shape is None:
            raise ValueError("LightGlue needs keypoints and the image shape")
        h, w = shape[:2]
        # LightGlue attention is O(N^2) in keypoints; a frame carrying several
        # orientations can exhaust an 8 GB card. Fall back to CPU for that pair
        # rather than losing it -- a slow match beats a missing one.
        try:
            return self._match_on(self.device, desc1, desc2, kp1, kp2, h, w)
        except torch.OutOfMemoryError:
            torch.cuda.empty_cache()
            return self._match_on(torch.device("cpu"), desc1, desc2, kp1, kp2, h, w)

    def _match_on(self, device, desc1, desc2, kp1, kp2, h, w):
        import torch
        import kornia.feature as KF
        matcher = self._matcher if device == self.device else self._matcher.to(device)
        with torch.inference_mode():
            d1 = torch.from_numpy(np.asarray(desc1)).to(device)
            d2 = torch.from_numpy(np.asarray(desc2)).to(device)
            lafs1 = KF.laf_from_center_scale_ori(
                torch.from_numpy(np.asarray(kp1, np.float32))[None].to(device))
            lafs2 = KF.laf_from_center_scale_ori(
                torch.from_numpy(np.asarray(kp2, np.float32))[None].to(device))
            _dists, idxs = matcher(d1, d2, lafs1, lafs2, hw1=(h, w), hw2=(h, w))
        if device != self.device:
            self._matcher.to(self.device)
        pairs = idxs.detach().cpu().numpy()
        return [(int(a), int(b)) for a, b in pairs]

    def info(self) -> BackendInfo:
        return BackendInfo(f"lightglue+{self.detector_name}", "learned",
                           self.licence, str(self.device),
                           {"max_keypoints": self.max_keypoints})


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def create(name: str = "sift", **kwargs) -> FeatureBackend:
    """Build a backend by name. Unknown names fail loudly rather than defaulting.

    Silently falling back to SIFT when a learned backend is unavailable would be
    the worst outcome for a benchmark: the run would be labelled as the learned
    variant while measuring the classical one.
    """
    name = (name or "sift").lower()
    if name == "sift":
        return SiftBackend(**kwargs)
    if name == "orb":
        return OrbBackend(**kwargs)
    if name in ("lightglue", "disk", "aliked", "superpoint"):
        # A caller may address the backend either by matcher name
        # (`create("lightglue", detector="aliked")`) or by detector name
        # (`create("aliked")`); an explicit `detector` kwarg wins.
        det = kwargs.pop("detector", None) or ("disk" if name == "lightglue" else name)
        return LightGlueBackend(detector=det, **kwargs)
    raise ValueError(f"unknown feature backend {name!r}; "
                     "known: sift, orb, lightglue, disk, aliked, superpoint")


def available() -> dict:
    """Which backends can actually run here, and why not when they cannot."""
    out = {"sift": True, "orb": True}
    try:
        import torch  # noqa: F401
        import kornia  # noqa: F401
        out["lightglue"] = True
    except Exception as exc:
        out["lightglue"] = f"unavailable: {exc}"
    return out
