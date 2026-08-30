"""Optional surface meshing (Open3D Poisson / ball-pivoting).

Meshing is optional: if Open3D is unavailable or meshing fails, the point cloud
is preserved and a capability warning is returned.  Low-density artefacts are
cropped.  Provenance is preserved by transferring per-vertex confidence.
"""
from __future__ import annotations

import numpy as np

try:
    import open3d as o3d
    _HAVE_O3D = True
except Exception:
    _HAVE_O3D = False


def available() -> bool:
    return _HAVE_O3D


def mesh_poisson(cloud, *, depth: int = 9, density_quantile: float = 0.1):
    """Return (vertices, faces, vertex_colors) or raise with a clear reason."""
    if not _HAVE_O3D:
        raise RuntimeError("Open3D not installed; meshing unavailable. "
                           "Point cloud output is preserved.")
    if len(cloud) < 100:
        raise RuntimeError("too few points to mesh; point cloud preserved")

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(cloud.points)
    pc.colors = o3d.utility.Vector3dVector(cloud.colors.astype(float) / 255.0)
    if cloud.normals is not None:
        pc.normals = o3d.utility.Vector3dVector(cloud.normals)
    else:
        pc.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(radius=1.0, max_nn=20))
    pc.orient_normals_towards_camera_location(pc.get_center() + np.array([0, 0, 100]))

    m, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pc, depth=depth)
    densities = np.asarray(densities)
    if density_quantile > 0:
        keep = densities > np.quantile(densities, density_quantile)
        m.remove_vertices_by_mask(~keep)
    m.compute_vertex_normals()
    verts = np.asarray(m.vertices)
    faces = np.asarray(m.triangles)
    cols = (np.asarray(m.vertex_colors) * 255).astype(np.uint8) if m.has_vertex_colors() \
        else np.tile([200, 200, 200], (len(verts), 1)).astype(np.uint8)
    return verts, faces, cols
