"""Feed-forward pointmaps -> initial 3D Gaussians (the SuGaR handshake).

SuGaR meshes an existing 3D Gaussian Splatting model, and 3DGS is normally
initialised from a COLMAP sparse cloud. This pipeline reaches a dense cloud
without COLMAP, so the bridge has to be built: every Gaussian attribute that
3DGS expects must be derived from what a feed-forward model actually returns
(positions, colours, per-point confidence).

The mapping, and where each value comes from:

===========  ==========================================================
attribute    derivation
===========  ==========================================================
position     the pointmap directly
SH DC term   colour, converted through the degree-0 SH basis constant
SH rest      zero -- a feed-forward model gives one colour per point and
             no view-dependent information to seed higher bands with
scale        distance to the k nearest neighbours, so a Gaussian spans
             the gap to its neighbours and the surface has no holes
rotation     aligned to the local surface normal from PCA, flattest axis
             along the normal -- SuGaR wants surface-aligned Gaussians
             and flattens them during training anyway
opacity      the model's own confidence
===========  ==========================================================

**Every stored value is pre-activation.** 3DGS applies ``exp`` to scale and
``sigmoid`` to opacity when it loads, so this module stores ``log`` and
``logit``. Writing post-activation values is the classic silent failure: the
file loads, the numbers look plausible, and the model renders as fog or not at
all.
"""
from __future__ import annotations

import numpy as np

#: Degree-0 spherical-harmonic basis constant, 0.5*sqrt(1/pi). 3DGS stores the
#: DC colour term as ``(rgb - 0.5) / C0`` so that the SH evaluation reproduces
#: the original colour.
SH_C0 = 0.28209479177387814


def rgb_to_sh_dc(rgb_uint8) -> np.ndarray:
    """uint8 RGB -> degree-0 SH coefficients."""
    c = np.asarray(rgb_uint8, float).reshape(-1, 3) / 255.0
    return (c - 0.5) / SH_C0


def sh_dc_to_rgb(dc) -> np.ndarray:
    """Inverse of :func:`rgb_to_sh_dc`, for verification."""
    c = np.asarray(dc, float).reshape(-1, 3) * SH_C0 + 0.5
    return np.clip(c * 255.0, 0, 255).astype(np.uint8)


def _logit(p, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(np.asarray(p, float), eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


def local_geometry(points, k: int = 4, max_points_for_tree: int | None = None):
    """Per-point neighbour spacing and surface normal.

    Returns ``(spacing, normals)``. ``spacing`` is the mean distance to the k
    nearest neighbours -- the natural scale for a Gaussian that should just
    close the gap to its neighbours. ``normals`` come from the smallest
    principal axis of the same neighbourhood.
    """
    from scipy.spatial import cKDTree
    P = np.asarray(points, float)
    n = len(P)
    tree = cKDTree(P)
    kk = min(k + 1, n)
    d, idx = tree.query(P, k=kk)
    if kk == 1:
        return np.ones(n), np.tile([0.0, 0.0, 1.0], (n, 1))
    spacing = d[:, 1:].mean(axis=1)
    # PCA over each neighbourhood; smallest eigenvector is the normal
    nb = P[idx]                                   # (n, kk, 3)
    nb = nb - nb.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / max(kk - 1, 1)
    _, vecs = np.linalg.eigh(cov)                 # ascending eigenvalues
    normals = vecs[:, :, 0]
    norm = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.where(norm > 1e-12, normals / np.maximum(norm, 1e-12),
                       np.array([0.0, 0.0, 1.0]))
    return spacing, normals


def quat_from_normal(normals) -> np.ndarray:
    """Quaternions (w, x, y, z) rotating +z onto each normal.

    The Gaussian's third axis carries the flattened scale, so aligning +z with
    the surface normal makes the ellipsoid lie *in* the surface rather than
    across it.
    """
    n = np.asarray(normals, float).reshape(-1, 3)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    z = np.array([0.0, 0.0, 1.0])
    dot = np.clip(n @ z, -1.0, 1.0)
    axis = np.cross(np.broadcast_to(z, n.shape), n)
    s = np.linalg.norm(axis, axis=1)
    q = np.zeros((len(n), 4))
    q[:, 0] = 1.0                                  # identity where aligned
    ok = s > 1e-9
    if ok.any():
        ang = np.arctan2(s[ok], dot[ok])
        a = axis[ok] / s[ok][:, None]
        q[ok, 0] = np.cos(ang / 2)
        q[ok, 1:] = a * np.sin(ang / 2)[:, None]
    # antiparallel: any axis perpendicular to z gives a 180 deg turn
    flip = (~ok) & (dot < 0)
    if flip.any():
        q[flip] = np.array([0.0, 1.0, 0.0, 0.0])
    return q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)


def from_pointmap(points, colors, conf=None, *, k: int = 4,
                  flatten: float = 0.1, opacity_floor: float = 0.1,
                  opacity_ceiling: float = 0.99, sh_degree: int = 3):
    """Build 3DGS initial attributes from a dense pointmap.

    ``flatten`` scales the normal-direction axis relative to the two in-surface
    axes. SuGaR's whole premise is that a surface-aligned, flattened Gaussian
    field meshes cleanly, so seeding flat rather than spherical starts the
    optimisation where it is trying to go.

    ``conf`` is mapped to opacity through ``opacity_floor``/``opacity_ceiling``
    rather than used raw: a Gaussian at opacity 0 is invisible and receives no
    gradient, so a low-confidence point initialised at zero can never recover.
    """
    P = np.asarray(points, float).reshape(-1, 3)
    spacing, normals = local_geometry(P, k=k)
    # guard degenerate spacing (duplicated points) so log() stays finite
    spacing = np.maximum(spacing, 1e-6)

    s_tan = spacing
    s_norm = spacing * float(flatten)
    scales = np.stack([s_tan, s_tan, np.maximum(s_norm, 1e-7)], axis=1)

    if conf is None:
        op = np.full(len(P), 0.8)
    else:
        c = np.asarray(conf, float).ravel()[: len(P)]
        lo, hi = np.nanmin(c), np.nanmax(c)
        c = (c - lo) / (hi - lo) if hi > lo else np.full_like(c, 0.8)
        op = opacity_floor + c * (opacity_ceiling - opacity_floor)

    n_rest = 3 * ((sh_degree + 1) ** 2 - 1)
    return dict(
        xyz=P,
        normals=normals,
        f_dc=rgb_to_sh_dc(colors),
        f_rest=np.zeros((len(P), n_rest)),
        opacity=_logit(op)[:, None],               # pre-sigmoid
        scaling=np.log(scales),                    # pre-exp
        rotation=quat_from_normal(normals),
        sh_degree=sh_degree,
    )


def write_ply(path, g) -> str:
    """Write 3DGS-format binary PLY (the layout SuGaR and 3DGS both read)."""
    import struct
    xyz = g["xyz"]; n = len(xyz)
    names = ["x", "y", "z", "nx", "ny", "nz"]
    names += [f"f_dc_{i}" for i in range(3)]
    names += [f"f_rest_{i}" for i in range(g["f_rest"].shape[1])]
    names += ["opacity", "scale_0", "scale_1", "scale_2",
              "rot_0", "rot_1", "rot_2", "rot_3"]
    data = np.concatenate([
        xyz, g["normals"], g["f_dc"], g["f_rest"],
        g["opacity"], g["scaling"], g["rotation"]], axis=1).astype(np.float32)
    assert data.shape[1] == len(names), (data.shape, len(names))
    header = ["ply", "format binary_little_endian 1.0", f"element vertex {n}"]
    header += [f"property float {nm}" for nm in names]
    header.append("end_header")
    with open(path, "wb") as f:
        f.write(("\n".join(header) + "\n").encode())
        f.write(data.tobytes())
    return str(path)
