"""Score an estimate against ground truth.

Metrics are all *gauge-free*: a Sim(3) is fitted between estimated and GT camera
centres (the standard ATE alignment), and every spatial number is reported after
that alignment, so a global rotation/translation/scale gauge cannot flatter or
penalise the result.  The recovered scale's deviation from 1.0 is reported
separately as the metric-scale error.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
from scipy.spatial import cKDTree

from drishti_recon import geo

from .cases import EvalCase
from .harness import Estimate


@dataclass
class CaseScore:
    name: str
    kind: str
    n_images: int
    n_solved: int                      # cameras the pipeline registered
    n_matched: int                     # solved cameras with a GT pose
    # trajectory (metres), after Sim(3) alignment to GT centres
    ate_rmse: float | None = None
    ate_median: float | None = None
    ate_max: float | None = None
    ate_axis_rmse: list | None = None  # [E,N,U]
    scale_error: float | None = None   # |recovered_scale - 1|
    # point cloud vs GT cloud (metres, after the same Sim(3))
    cloud_acc_median: float | None = None
    cloud_acc_rmse: float | None = None
    cloud_completeness: float | None = None   # frac GT pts within `thr`
    cloud_thr: float | None = None
    #: "analytic_surface" or "sampled_nn" -- accuracy numbers are only
    #: comparable within the same source.
    cloud_acc_source: str | None = None
    n_cloud_pts: int = 0
    # dimensional accuracy from the pipeline's own GT eval, if present
    dim_error_pct: float | None = None
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _align_sim3(est_centers, gt_centers):
    """Robust Sim(3) est->GT; falls back to plain Umeyama on tiny sets."""
    if len(est_centers) >= 4:
        try:
            res = geo.robust_sim3(est_centers, gt_centers)
            return res.transform
        except Exception:
            pass
    return geo.umeyama_sim3(est_centers, gt_centers)


def score_case(case: EvalCase, est: Estimate, *, cloud_thr: float = 0.5) -> CaseScore:
    warns = list(est.warnings)
    n_images = case.n if case.n else (
        len(case.gt_centers) if case.gt_centers is not None else 0)
    sc = CaseScore(name=case.name, kind=case.kind, n_images=n_images,
                   n_solved=len(est.est_centers_enu), n_matched=0,
                   n_cloud_pts=int(len(est.cloud_pts)))

    sim3 = None
    if case.gt_centers is not None and len(est.est_frames):
        idx = est.est_frames
        valid = idx < len(case.gt_centers)
        est_c = est.est_centers_enu[valid]
        gt_c = case.gt_centers[idx[valid]]
        sc.n_matched = int(valid.sum())
        if sc.n_matched >= 3:
            sim3 = _align_sim3(est_c, gt_c)
            aligned = sim3.apply(est_c)
            err = aligned - gt_c
            d = np.linalg.norm(err, axis=1)
            sc.ate_rmse = float(np.sqrt((d ** 2).mean()))
            sc.ate_median = float(np.median(d))
            sc.ate_max = float(d.max())
            sc.ate_axis_rmse = [float(np.sqrt((err[:, k] ** 2).mean())) for k in range(3)]
            sc.scale_error = float(abs(sim3.scale - 1.0))
        else:
            warns.append(f"only {sc.n_matched} matched cameras; ATE skipped")

    # cloud accuracy / completeness ----------------------------------------
    # Standard MVS protocol: register the reconstruction to the GT cloud with a
    # *rigid* ICP (scale locked at 1, so it cannot flatter the numbers),
    # initialised from the camera Sim(3), then CROP to the GT's evaluation region
    # before scoring -- exactly as ETH3D/Tanks-and-Temples do. Reusing the
    # pipeline's own (uncropped) surface number would count sky/ground outliers
    # far outside the GT and inflate the error several-fold.
    ge = (est.report or {}).get("ground_truth_evaluation") or {}
    gt_cloud = _gt_cloud(case)
    if gt_cloud is not None and sim3 is not None and len(est.cloud_pts):
        aligned, d = _icp_to_cloud(sim3.apply(est.cloud_pts), gt_cloud)
        margin = 1.0
        lo, hi = gt_cloud.min(0) - margin, gt_cloud.max(0) + margin
        inb = np.all((aligned >= lo) & (aligned <= hi), axis=1)
        recon = aligned[inb] if inb.sum() >= 10 else aligned
        # Accuracy: prefer exact point-to-surface distance when the case knows
        # its own geometry. Nearest-neighbour to a sampled cloud measures that
        # cloud's spacing as much as our error -- on the synthetic scene the
        # sampled metric read 0.78 m median where the analytic value is 0.02 m,
        # and the two rank points at only rho = 0.20.
        fn = getattr(case, "gt_surface_distance", None)
        if fn is not None:
            dd = np.asarray(fn(recon), float)
            sc.cloud_acc_source = "analytic_surface"
        else:
            dd = d[inb] if inb.sum() >= 10 else d
            sc.cloud_acc_source = "sampled_nn"
        # Completeness asks the opposite question -- is there a reconstructed
        # point near each truth point -- which a sampled cloud answers soundly.
        comp, _ = cKDTree(recon).query(gt_cloud)
        sc.cloud_acc_median = float(np.median(dd))
        sc.cloud_acc_rmse = float(np.sqrt((dd ** 2).mean()))
        sc.cloud_completeness = float((comp <= cloud_thr).mean())
        sc.cloud_thr = cloud_thr
    elif (sa := ge.get("surface_accuracy_m")):
        # fallback: no GT cloud in the eval layer, but the pipeline scored one
        # in its shared GPS frame (note: uncropped).
        sc.cloud_acc_median = float(sa["median"])
        sc.cloud_acc_rmse = float(sa["rmse"])
        sc.cloud_completeness = ge.get(f"completeness_at_{cloud_thr}m")
        sc.cloud_thr = cloud_thr
        warns.append("cloud accuracy from pipeline's uncropped surface metric")
    elif gt_cloud is not None and sim3 is None:
        warns.append("GT cloud present but no pose alignment; cloud metrics skipped")

    # dimensional accuracy (from the pipeline's own reference-distance check) --
    dims = ge.get("dimensional_accuracy")
    if dims:
        errs = [d["pct_error"] for d in dims if d.get("pct_error") is not None]
        sc.dim_error_pct = float(np.mean(errs)) if errs else None

    sc.warnings = warns
    return sc


def _icp_to_cloud(src, dst, *, iters: int = 25, trim: float = 0.8,
                  cap: int = 60000):
    """Trimmed rigid ICP (scale fixed) aligning src->dst; returns (aligned, dists)."""
    rng = np.random.default_rng(0)
    s = src if len(src) <= cap else src[rng.choice(len(src), cap, replace=False)]
    tree = cKDTree(dst)
    for _ in range(iters):
        d, idx = tree.query(s)
        keep = d <= np.quantile(d, trim)
        if keep.sum() < 3:
            break
        T = geo.umeyama_sim3(s[keep], dst[idx[keep]], with_scale=False)
        s = T.apply(s)
    d, _ = tree.query(s)
    return s, d


def _gt_cloud(case: EvalCase):
    if case.gt_cloud_pts is not None:
        return np.asarray(case.gt_cloud_pts, float)
    if case.gt_cloud_path is not None:
        return _load_cloud_file(case.gt_cloud_path)
    return None


def _load_cloud_file(path):
    """Load a GT cloud from .ply / .las / .laz -> (M,3)."""
    from pathlib import Path
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".las", ".laz"):
        import laspy
        f = laspy.read(str(path))
        return np.column_stack([f.x, f.y, f.z]).astype(float)
    # PLY (ascii or binary) via a light parser through open3d if available
    try:
        import open3d as o3d
        pc = o3d.io.read_point_cloud(str(path))
        return np.asarray(pc.points, float)
    except Exception:
        return _read_ply_xyz(path)


def _read_ply_xyz(path):
    """Minimal ascii/binary-little-endian PLY xyz reader (fallback)."""
    import struct
    from pathlib import Path
    data = Path(path).read_bytes()
    hdr_end = data.index(b"end_header\n") + len(b"end_header\n")
    header = data[:hdr_end].decode("ascii", "ignore").splitlines()
    fmt = next((l.split()[1] for l in header if l.startswith("format")), "ascii")
    n = next(int(l.split()[2]) for l in header if l.startswith("element vertex"))
    props = [l.split()[-1] for l in header if l.startswith("property")]
    xi, yi, zi = props.index("x"), props.index("y"), props.index("z")
    if fmt.startswith("ascii"):
        rows = data[hdr_end:].decode("ascii", "ignore").split()
        stride = len(props)
        out = []
        for k in range(n):
            base = k * stride
            out.append([float(rows[base + xi]), float(rows[base + yi]),
                        float(rows[base + zi])])
        return np.array(out, float)
    # binary_little_endian, assume all float32 props (common for xyz-only)
    stride = len(props) * 4
    buf = data[hdr_end:hdr_end + n * stride]
    arr = np.frombuffer(buf, dtype="<f4").reshape(n, len(props))
    return arr[:, [xi, yi, zi]].astype(float)
