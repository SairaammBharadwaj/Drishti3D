"""Dense feed-forward reconstruction (Intelligence Edition stage 3).

Wraps the MASt3R family: a transformer that predicts dense pointmaps, relative
poses and per-pixel confidence for image pairs, followed by MASt3R's sparse
global alignment over a sequential + log-spaced-skip pair graph. This replaces
feature matching entirely for the dense path — the doc's answer to limited
parallax and textureless surfaces on single-pass video.

License gate: the MASt3R checkpoint is CC-BY-NC-SA (non-commercial), the same
class of restriction as SuperPoint, which ``features.py`` refuses by default.
Same policy here: the engine must be explicitly enabled with
``allow_noncommercial=True`` and every result carries a license warning.

Outputs use the repo's conventions: world-from-camera poses, camera centres in
the reconstruction frame, per-point confidence in [0, 1].
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
_MAST3R = _ROOT / "third_party" / "mast3r"
_CKPT = _ROOT / "models" / "mast3r_metric"

LICENSE_WARNING = (
    "dense3d uses the MASt3R checkpoint (CC-BY-NC-SA, non-commercial). "
    "Fine for research/SIH evaluation; a commercial deployment must swap it."
)

_model = None


def is_available() -> bool:
    return (_MAST3R / "mast3r").is_dir() and \
        (_CKPT / "model.safetensors").is_file()


def _paths():
    for p in (str(_MAST3R), str(_MAST3R / "dust3r")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_model(device: str):
    global _model
    if _model is None:
        _paths()
        from mast3r.model import AsymmetricMASt3R
        _model = AsymmetricMASt3R.from_pretrained(str(_CKPT)).to(device).eval()
    return _model


def reconstruct_dir(image_dir, work_dir, *,
                    allow_noncommercial: bool = False,
                    scene_graph: str = "logwin-4-noncyclic",
                    image_size: int = 512,
                    subsample: int = 8,
                    device: str = "cuda",
                    shared_intrinsics: bool = True,
                    matching_conf_thr: float = 0.0):
    """Run MASt3R sparse global alignment over a directory of frames.

    Returns a dict with ``cam2w`` (N,4,4) world-from-camera, ``centres`` (N,3),
    ``focals`` (N,), ``points`` (M,3), ``colors`` (M,3 uint8), ``conf`` (M,)
    in [0,1], ``image_names``, plus ``license_warning``.

    ``scene_graph='logwin-4-noncyclic'`` builds the doc's pairing: each frame
    against a window of successors at offsets 1,2,4,8 — sequential edges for
    local structure and log-spaced skips for the long-range constraints that
    resist bowing. ``shared_intrinsics=True`` because a single video has one
    camera (the per-image self-calibration failure mode is documented in
    BENCHMARK.md: focals diverged 1062..2044 px against a surveyed 893).
    """
    if not allow_noncommercial:
        raise RuntimeError(
            "dense3d is disabled by default: " + LICENSE_WARNING +
            " Pass allow_noncommercial=True to enable.")
    if not is_available():
        raise RuntimeError("MASt3R repo or checkpoint missing under "
                           f"{_MAST3R} / {_CKPT}")
    _paths()
    import torch
    from dust3r.utils.image import load_images
    from dust3r.image_pairs import make_pairs
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment

    image_dir = Path(image_dir)
    work_dir = Path(work_dir); work_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(p for p in os.listdir(image_dir)
                   if p.lower().endswith((".jpg", ".jpeg", ".png")))
    files = [str(image_dir / n) for n in names]
    if len(files) < 3:
        raise RuntimeError(f"need >= 3 frames, found {len(files)}")

    model = _load_model(device)
    imgs = load_images(files, size=image_size, verbose=False)
    # symmetrize=True is required: sparse_ga's correspondence bookkeeping
    # indexes reversed (j, i) pairs and KeyErrors without them.
    pairs = make_pairs(imgs, scene_graph=scene_graph, prefilter=None,
                       symmetrize=True)

    scene = sparse_global_alignment(
        files, pairs, str(work_dir / "cache"), model,
        subsample=subsample, device=device,
        shared_intrinsics=shared_intrinsics,
        matching_conf_thr=matching_conf_thr)

    cam2w = scene.cam2w.detach().cpu().numpy()
    focals = np.array([float(f) for f in scene.get_focals().detach().cpu()])
    pts, cols, confs = [], [], []
    for i, (p, c) in enumerate(zip(scene.pts3d, scene.pts3d_colors)):
        p = p.detach().cpu().numpy().reshape(-1, 3)
        conf = scene.conf[i].detach().cpu().numpy().ravel() \
            if hasattr(scene, "conf") else np.ones(len(p))
        pts.append(p); cols.append(np.asarray(c).reshape(-1, 3)); confs.append(conf)
    points = np.concatenate(pts) if pts else np.zeros((0, 3))
    colors = np.concatenate(cols).astype(np.uint8) if cols else np.zeros((0, 3), np.uint8)
    conf = np.concatenate(confs)[: len(points)] if confs else np.zeros(0)
    # squash raw confidences to [0, 1]
    if conf.size and conf.max() > 1.0:
        conf = 1.0 - np.exp(-conf / max(np.median(conf), 1e-6))

    return dict(cam2w=cam2w, centres=cam2w[:, :3, 3].copy(), focals=focals,
                points=points, colors=colors, conf=conf,
                image_names=names, engine="mast3r",
                license_warning=LICENSE_WARNING)


def relative_edges(cam2w, *, offsets=(1, 2, 4, 8)):
    """Turn aligned poses into pose-graph edges for :mod:`pose_graph`.

    Edge (i, j) carries the pose of j in i's camera frame, from the globally
    aligned solution. Used to hand the dense backbone's local geometry to the
    GPS-anchored pose graph, which is where the bow is actually removed.
    """
    from .pose_graph import Edge
    cam2w = np.asarray(cam2w, float)
    n = len(cam2w)
    R = cam2w[:, :3, :3]; c = cam2w[:, :3, 3]
    edges = []
    for off in offsets:
        for i in range(0, n - off):
            j = i + off
            R_ij = R[i].T @ R[j]
            t_ij = R[i].T @ (c[j] - c[i])
            edges.append(Edge(i, j, R_ij, t_ij, weight=1.0 / off))
    return edges


def pairwise_edges_dir(image_dir, *,
                       allow_noncommercial: bool = False,
                       offsets=(1, 2, 4, 8),
                       image_size: int = 512,
                       device: str = "cuda",
                       batch_size: int = 4,
                       conf_quantile: float = 0.5):
    """Per-pair relative poses straight from the dense model — no global step.

    The Intelligence Edition pipeline separates concerns: the dense model
    (stage 3) supplies *pairwise* geometry; the pose graph (stage 4) is the
    global assembler, anchored by GPS. Measured motivation: MASt3R's own
    global alignment on the AGZ pass produced locally-clean but globally
    broken geometry — robust Sim(3) to GPS accepted only 12/62 cameras.
    Skipping the model's global stage and assembling with our GPS-anchored
    pose graph avoids inheriting that break.

    For each pair (i, j) the model predicts view-j's pointmap twice: in j's
    own frame and in i's frame. The rigid transform between those two clouds
    IS the relative pose, recovered by confidence-weighted Procrustes over
    the most confident half of the pixels. MASt3R's metric training makes the
    translation approximately metric.

    Returns (edges, names, diag) where ``edges`` feed :mod:`pose_graph` and
    ``diag`` carries per-edge residuals for gating.
    """
    if not allow_noncommercial:
        raise RuntimeError(
            "dense3d is disabled by default: " + LICENSE_WARNING +
            " Pass allow_noncommercial=True to enable.")
    _paths()
    import torch
    from dust3r.utils.image import load_images
    from dust3r.inference import inference
    from .pose_graph import Edge

    image_dir = Path(image_dir)
    names = sorted(p for p in os.listdir(image_dir)
                   if p.lower().endswith((".jpg", ".jpeg", ".png")))
    files = [str(image_dir / n) for n in names]
    n = len(files)
    model = _load_model(device)
    imgs = load_images(files, size=image_size, verbose=False)

    wanted = []
    for off in offsets:
        wanted += [(i, i + off) for i in range(0, n - off)]

    edges, diag = [], []
    for a in range(0, len(wanted), batch_size):
        chunk = wanted[a:a + batch_size]
        batch = [(imgs[i], imgs[j]) for i, j in chunk]
        with torch.no_grad():
            out = inference(batch, model, device,
                            batch_size=batch_size, verbose=False)
        p1, p2 = out["pred1"], out["pred2"]
        for k, (i, j) in enumerate(chunk):
            # view j's points in its own frame and in i's frame
            Xj = p2["pts3d_in_other_view"][k].reshape(-1, 3)   # in frame i
            cj = p2["conf"][k].reshape(-1)
            # j's own-frame pointmap: run of (j, j) is wasteful; instead use
            # depth-consistent trick: model also emits pred1 for image i; for
            # frame-j-own geometry, use the symmetric pair below.
            edges.append((i, j, Xj.detach().cpu().numpy(),
                          cj.detach().cpu().numpy()))
    # second pass: same pairs reversed, giving view j in its own frame
    own = {}
    for a in range(0, len(wanted), batch_size):
        chunk = wanted[a:a + batch_size]
        batch = [(imgs[j], imgs[i]) for i, j in chunk]      # reversed
        with torch.no_grad():
            out = inference(batch, model, device,
                            batch_size=batch_size, verbose=False)
        p1 = out["pred1"]
        for k, (i, j) in enumerate(chunk):
            own[(i, j)] = (p1["pts3d"][k].reshape(-1, 3).detach().cpu().numpy(),
                           p1["conf"][k].reshape(-1).detach().cpu().numpy())

    out_edges, out_diag = [], []
    for (i, j, Xj_in_i, cj) in edges:
        Xj_own, cj_own = own[(i, j)]
        w = np.minimum(cj, cj_own)
        keep = w >= np.quantile(w, conf_quantile)
        A = Xj_own[keep]; B = Xj_in_i[keep]; ww = w[keep]
        # weighted rigid Procrustes A (j frame) -> B (i frame)
        ma = np.average(A, 0, ww); mb = np.average(B, 0, ww)
        H = ((A - ma) * ww[:, None]).T @ (B - mb)
        U, S, Vt = np.linalg.svd(H)
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        R_ij = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
        t_ij = mb - R_ij @ ma
        resid = np.sqrt(np.average(
            np.sum((B - ((R_ij @ A.T).T + t_ij)) ** 2, 1), weights=ww))
        off = j - i
        out_edges.append(Edge(i, j, R_ij, t_ij, weight=1.0 / off))
        out_diag.append(dict(i=i, j=j, resid=float(resid),
                             conf=float(np.median(w))))
    return out_edges, names, out_diag
