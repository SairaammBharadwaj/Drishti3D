"""VGGT feed-forward reconstruction backend.

An alternative to :mod:`dense3d` (MASt3R). VGGT predicts camera pose, depth and
world-frame pointmaps for a whole image set in a single forward pass, rather
than per pair, so there is no separate global-alignment stage to go wrong --
which matters here, because MASt3R's own global alignment produced locally
clean but globally broken geometry on this data (robust Sim(3) accepted 12/62
cameras).

Outputs follow the repo's conventions: world-from-camera poses, camera centres
in the reconstruction frame, per-point confidence in [0, 1].

License: VGGT weights and code are CC-BY-NC 4.0 (non-commercial), the same
class as MASt3R and SuperPoint, so the same gate applies -- explicit opt-in
via ``allow_noncommercial=True``, with the warning carried on every result.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
_CODE = _ROOT / "third_party" / "vggt"
_CKPT = _ROOT / "models" / "vggt"

LICENSE_WARNING = (
    "vggt_engine uses the VGGT-1B checkpoint (CC-BY-NC 4.0, non-commercial). "
    "Fine for research and SIH evaluation; a commercial deployment must swap it."
)

_model = None


def is_available() -> bool:
    return (_CODE / "vggt").is_dir() and (_CKPT / "model.safetensors").is_file()


def _paths():
    p = str(_CODE)
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(device: str):
    global _model
    if _model is None:
        _paths()
        import torch
        from vggt.models.vggt import VGGT
        m = VGGT()
        from safetensors.torch import load_file
        sd = load_file(str(_CKPT / "model.safetensors"))
        missing, unexpected = m.load_state_dict(sd, strict=False)
        if len(missing) > 40:
            raise RuntimeError(
                f"VGGT checkpoint does not match the model: {len(missing)} "
                "missing tensors. Refusing to run a partly-initialised network "
                "-- it would return confident nonsense.")
        _model = m.to(device).eval()
    return _model


def reconstruct_dir(image_dir, *, allow_noncommercial: bool = False,
                    device: str = "cuda", max_frames: int | None = None,
                    conf_percentile: float = 50.0, dtype=None):
    """Run VGGT over a directory of frames in one forward pass.

    Returns ``cam2w`` (N,4,4), ``centres`` (N,3), ``intrinsics`` (N,3,3),
    ``points`` (M,3), ``colors`` (M,3 uint8), ``conf`` (M,) in [0,1],
    ``image_names`` and ``license_warning``.

    ``conf_percentile`` drops the least-confident half of predicted points by
    default. The model emits a pointmap for every pixel including sky and
    motion blur, and those carry confidence but not geometry.
    """
    if not allow_noncommercial:
        raise RuntimeError("vggt_engine is disabled by default: "
                           + LICENSE_WARNING
                           + " Pass allow_noncommercial=True to enable.")
    if not is_available():
        raise RuntimeError(f"VGGT code or weights missing under {_CODE} / {_CKPT}")
    _paths()
    import torch
    from vggt.utils.load_fn import load_and_preprocess_images
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    image_dir = Path(image_dir)
    names = sorted(p for p in os.listdir(image_dir)
                   if p.lower().endswith((".jpg", ".jpeg", ".png")))
    if max_frames:
        names = names[:max_frames]
    files = [str(image_dir / n) for n in names]
    if len(files) < 2:
        raise RuntimeError(f"need >= 2 frames, found {len(files)}")

    model = _load(device)
    images = load_and_preprocess_images(files).to(device)
    if dtype is None:
        cap = torch.cuda.get_device_capability()[0] if device == "cuda" else 0
        dtype = torch.bfloat16 if cap >= 8 else torch.float16

    with torch.no_grad():
        with torch.amp.autocast(device, dtype=dtype):
            pred = model(images[None])

    hw = images.shape[-2:]
    extr, intr = pose_encoding_to_extri_intri(pred["pose_enc"], hw)
    extr = extr[0].float().cpu().numpy()            # (N,3,4) world->camera
    intr = intr[0].float().cpu().numpy()

    n = len(extr)
    cam2w = np.tile(np.eye(4), (n, 1, 1))
    for i in range(n):
        R, t = extr[i][:, :3], extr[i][:, 3]
        cam2w[i, :3, :3] = R.T
        cam2w[i, :3, 3] = -R.T @ t

    pts = pred["world_points"][0].float().cpu().numpy().reshape(-1, 3)
    conf = pred["world_points_conf"][0].float().cpu().numpy().ravel()
    rgb = (images.float().cpu().numpy().transpose(0, 2, 3, 1).reshape(-1, 3))
    rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)

    keep = conf >= np.percentile(conf, conf_percentile)
    pts, rgb, conf = pts[keep], rgb[keep], conf[keep]
    # squash raw confidence into [0,1] for the trust layer
    if conf.size and conf.max() > 1.0:
        conf = 1.0 - np.exp(-conf / max(np.median(conf), 1e-6))

    return dict(cam2w=cam2w, centres=cam2w[:, :3, 3].copy(), intrinsics=intr,
                points=pts, colors=rgb, conf=conf, image_names=names,
                engine="vggt", license_warning=LICENSE_WARNING,
                processed_hw=(int(hw[0]), int(hw[1])))


def relative_edges(cam2w, *, offsets=(1, 2, 4, 8)):
    """Pose-graph edges from VGGT's globally-consistent poses."""
    from .dense3d import relative_edges as _re
    return _re(cam2w, offsets=offsets)
