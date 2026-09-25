"""Point-cloud fusion, cleanup and provenance assignment.

Operates only in a common metric ENU frame.  Applies voxel downsampling and
statistical outlier removal, assigns per-point provenance classes from
confidence, and never fills unseen regions as observed geometry.  Uses Open3D
when available, with a pure-numpy fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .provenance import Provenance, classify

try:
    import open3d as o3d
    _HAVE_O3D = True
except Exception:
    _HAVE_O3D = False


@dataclass
class PointCloud:
    points: np.ndarray          # (N,3) ENU metres
    colors: np.ndarray          # (N,3) uint8
    confidence: np.ndarray      # (N,)
    provenance: np.ndarray      # (N,) int (Provenance)
    normals: np.ndarray | None = None
    #: Propagated 1-sigma positional uncertainty in metres (see
    #: :mod:`uncertainty`).  ``sigma`` is the isotropic-equivalent value used for
    #: display; ``sigma_major`` is the worst-constrained axis and is what
    #: measurements use, because reporting the optimistic direction of an
    #: anisotropic error would understate the risk of the number a user acts on.
    sigma: np.ndarray | None = None          # (N,)
    sigma_major: np.ndarray | None = None    # (N,)
    #: For each surviving point, the index it had in the array passed to
    #: :func:`fuse`.  Cleaning reindexes the cloud -- voxel downsampling keeps
    #: one representative per cell and outlier removal deletes rows -- so
    #: anything keyed to the pre-fusion ordering, observation lineage above all,
    #: is unrecoverable without this map.
    source_index: np.ndarray | None = None   # (N,) int32

    def __len__(self):
        return int(self.points.shape[0])

    def class_counts(self) -> dict:
        out = {}
        for p in Provenance:
            out[p.name] = int((self.provenance == int(p)).sum())
        return out


def _voxel_downsample_np(pts, cols, conf, voxel):
    keys = np.floor(pts / voxel).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    idx.sort()
    return pts[idx], cols[idx], conf[idx]


def _statistical_outlier_np(pts, k=12, std_ratio=2.0):
    from scipy.spatial import cKDTree
    if len(pts) < k + 1:
        return np.ones(len(pts), bool)
    tree = cKDTree(pts)
    d, _ = tree.query(pts, k=k + 1)
    mean_d = d[:, 1:].mean(1)
    thresh = mean_d.mean() + std_ratio * mean_d.std()
    return mean_d < thresh


def fuse(points, colors, confidence, *, voxel: float = 0.2,
         remove_outliers: bool = True, compute_normals: bool = True,
         sigma=None, sigma_major=None,
         max_sigma_major_m: float | None = None) -> PointCloud:
    """Clean and label a metric-frame cloud.

    ``max_sigma_major_m`` demotes a point to ``OBSERVED_LOW_CONFIDENCE`` when its
    predicted uncertainty exceeds it, whatever its confidence. Dense confidence
    is a function of view count alone, and fusion already requires four views,
    so 86% of MARS-LVIG dense points were "high confidence" -- a class whose
    error (vertical p90 1.26 m) barely differed from the whole cloud's (1.30 m).
    ``sigma_major`` ranks real error much better (DEC-043).

    ``sigma`` / ``sigma_major`` are optional per-point uncertainties carried
    through the same downsampling and outlier indexing as colour and confidence,
    so a shipped point keeps the uncertainty that belongs to it.

    The returned cloud also carries ``source_index``, mapping each surviving
    point back to its row in ``points``.  Two things reindex the cloud here and
    both would otherwise break any lineage keyed to the input ordering:

    * **Voxel downsampling** keeps one point per cell.  On the numpy path the
      survivor is a real input point and the map is exact.  On the Open3D path
      the survivor is a cell centroid, so the map is to the *nearest* input
      point -- the same nearest-point mapping already used to carry confidence
      and sigma across, so lineage cannot disagree with them.
    * **Statistical outlier removal** deletes rows outright.

    A point that was merged away loses its observations rather than donating
    them to the survivor.  That understates support for the survivor, which is
    the safe direction: claiming a point was seen from views that actually
    measured a different point is exactly the overstatement this whole path
    exists to prevent.
    """
    points = np.asarray(points, float)
    colors = np.asarray(colors, np.uint8)
    confidence = np.asarray(confidence, float)
    sigma = None if sigma is None else np.asarray(sigma, float)
    sigma_major = None if sigma_major is None else np.asarray(sigma_major, float)
    if len(points) == 0:
        return PointCloud(points, colors, confidence,
                          np.zeros(0, int), None, sigma, sigma_major,
                          np.zeros(0, np.int32))

    src = np.arange(len(points), dtype=np.int32)

    normals = None
    if _HAVE_O3D:
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(points)
        pc.colors = o3d.utility.Vector3dVector(colors.astype(float) / 255.0)
        # carry confidence via a parallel array through the same index ops
        if voxel > 0:
            pc = pc.voxel_down_sample(voxel)
        # map confidence by nearest original point
        from scipy.spatial import cKDTree
        tree = cKDTree(points)
        ds_pts = np.asarray(pc.points)
        _, nn = tree.query(ds_pts)
        conf2 = confidence[nn]
        src2 = src[nn]
        sig2 = None if sigma is None else sigma[nn]
        sigm2 = None if sigma_major is None else sigma_major[nn]
        cols2 = (np.asarray(pc.colors) * 255).astype(np.uint8)
        if remove_outliers and len(ds_pts) > 20:
            pc2, keep = pc.remove_statistical_outlier(nb_neighbors=12, std_ratio=2.0)
            ds_pts = np.asarray(pc2.points)
            cols2 = (np.asarray(pc2.colors) * 255).astype(np.uint8)
            conf2 = conf2[keep]
            src2 = src2[keep]
            sig2 = None if sig2 is None else sig2[keep]
            sigm2 = None if sigm2 is None else sigm2[keep]
        points, colors, confidence = ds_pts, cols2, conf2
        sigma, sigma_major, src = sig2, sigm2, src2
        if compute_normals and len(points) > 10:
            pc3 = o3d.geometry.PointCloud()
            pc3.points = o3d.utility.Vector3dVector(points)
            pc3.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 4, max_nn=20))
            normals = np.asarray(pc3.normals)
    else:
        if voxel > 0:
            keys = np.floor(points / voxel).astype(np.int64)
            _, idx = np.unique(keys, axis=0, return_index=True)
            idx.sort()
            points, colors, confidence = points[idx], colors[idx], confidence[idx]
            src = src[idx]
            sigma = None if sigma is None else sigma[idx]
            sigma_major = None if sigma_major is None else sigma_major[idx]
        if remove_outliers:
            keep = _statistical_outlier_np(points)
            points, colors, confidence = points[keep], colors[keep], confidence[keep]
            src = src[keep]
            sigma = None if sigma is None else sigma[keep]
            sigma_major = None if sigma_major is None else sigma_major[keep]

    provenance = np.array([int(classify(c)) for c in confidence], int)
    if max_sigma_major_m is not None and sigma_major is not None:
        too_uncertain = np.isfinite(sigma_major) & (sigma_major > max_sigma_major_m)
        high = provenance == int(Provenance.OBSERVED_HIGH_CONFIDENCE)
        provenance[high & too_uncertain] = int(Provenance.OBSERVED_LOW_CONFIDENCE)
    return PointCloud(points, colors, confidence, provenance, normals,
                      sigma, sigma_major, np.asarray(src, np.int32))


def add_inferred_layer(cloud: PointCloud, inferred_pts, inferred_cols=None) -> PointCloud:
    """Append AI-assisted/inferred points as a SEPARATE provenance layer.

    Inferred geometry is stored distinctly and excluded from measurement by
    default -- it is never merged into observed geometry.
    """
    inferred_pts = np.asarray(inferred_pts, float)
    if len(inferred_pts) == 0:
        return cloud
    if inferred_cols is None:
        inferred_cols = np.tile(Provenance.AI_ASSISTED.color, (len(inferred_pts), 1))
    pts = np.vstack([cloud.points, inferred_pts])
    cols = np.vstack([cloud.colors, inferred_cols.astype(np.uint8)])
    conf = np.concatenate([cloud.confidence, np.zeros(len(inferred_pts))])
    prov = np.concatenate([cloud.provenance,
                           np.full(len(inferred_pts), int(Provenance.AI_ASSISTED))])
    # Inferred points have no propagated uncertainty -- they were never
    # triangulated from real observations, so their sigma is infinite rather
    # than zero.  A missing uncertainty must never read as a confident one.
    def _ext(arr):
        if arr is None:
            return None
        return np.concatenate([arr, np.full(len(inferred_pts), np.inf)])
    # Inferred points have no source row in the triangulated cloud, so their
    # index is -1: "there is nothing behind this", which a lineage lookup must
    # be able to distinguish from row zero.
    src = None if cloud.source_index is None else np.concatenate(
        [cloud.source_index, np.full(len(inferred_pts), -1, np.int32)])
    return PointCloud(pts, cols, conf, prov, None,
                      _ext(cloud.sigma), _ext(cloud.sigma_major), src)
