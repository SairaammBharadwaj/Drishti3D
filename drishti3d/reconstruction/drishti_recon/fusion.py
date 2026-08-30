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
         remove_outliers: bool = True, compute_normals: bool = True) -> PointCloud:
    """Clean and label a metric-frame cloud."""
    points = np.asarray(points, float)
    colors = np.asarray(colors, np.uint8)
    confidence = np.asarray(confidence, float)
    if len(points) == 0:
        return PointCloud(points, colors, confidence,
                          np.zeros(0, int), None)

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
        cols2 = (np.asarray(pc.colors) * 255).astype(np.uint8)
        if remove_outliers and len(ds_pts) > 20:
            pc2, keep = pc.remove_statistical_outlier(nb_neighbors=12, std_ratio=2.0)
            ds_pts = np.asarray(pc2.points)
            cols2 = (np.asarray(pc2.colors) * 255).astype(np.uint8)
            conf2 = conf2[keep]
        points, colors, confidence = ds_pts, cols2, conf2
        if compute_normals and len(points) > 10:
            pc3 = o3d.geometry.PointCloud()
            pc3.points = o3d.utility.Vector3dVector(points)
            pc3.estimate_normals(
                o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 4, max_nn=20))
            normals = np.asarray(pc3.normals)
    else:
        if voxel > 0:
            points, colors, confidence = _voxel_downsample_np(
                points, colors, confidence, voxel)
        if remove_outliers:
            keep = _statistical_outlier_np(points)
            points, colors, confidence = points[keep], colors[keep], confidence[keep]

    provenance = np.array([int(classify(c)) for c in confidence], int)
    return PointCloud(points, colors, confidence, provenance, normals)


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
    return PointCloud(pts, cols, conf, prov, None)
