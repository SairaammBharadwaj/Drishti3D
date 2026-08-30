"""Feature-based incremental Structure-from-Motion (the *verified* path).

This is a genuine reconstruction engine built on OpenCV: it detects and matches
features across keyframes, estimates relative pose from the essential matrix,
triangulates 3D points, registers remaining frames by PnP, and fuses feature
tracks into a sparse point cloud with real per-point statistics (observation
count, reprojection error, triangulation angle).

No COLMAP, CUDA, or downloaded weights are required.  COLMAP is available as an
optional higher-accuracy adapter (see :mod:`colmap_adapter`).  Nothing here is
fabricated: every 3D point is triangulated from >= 2 real observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np
import cv2

Progress = Callable[[str, float], None]


def _noop(msg: str, frac: float) -> None:  # default progress sink
    pass


@dataclass
class Camera:
    frame_index: int          # index into the keyframe list
    R: np.ndarray             # world -> camera rotation (3,3)
    t: np.ndarray             # world -> camera translation (3,)
    registered: bool = True

    @property
    def center(self) -> np.ndarray:
        return (-self.R.T @ self.t).ravel()

    def projection(self, K) -> np.ndarray:
        return K @ np.hstack([self.R, self.t.reshape(3, 1)])


@dataclass
class ReconResult:
    points: np.ndarray                 # (N,3) reconstruction frame
    colors: np.ndarray                 # (N,3) uint8
    confidence: np.ndarray             # (N,) [0,1]
    obs_count: np.ndarray              # (N,) int
    reproj_err: np.ndarray             # (N,) px
    tri_angle: np.ndarray              # (N,) deg
    cameras: list                      # list[Camera] (registered only)
    K: np.ndarray
    stats: dict = field(default_factory=dict)


class _UnionFind:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _detect(gray, masks_i, nfeatures):
    sift = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=0.02)
    kp, desc = sift.detectAndCompute(gray, masks_i)
    return kp, desc


def _match(desc1, desc2, ratio=0.75):
    if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
        return []
    bf = cv2.BFMatcher(cv2.NORM_L2)
    knn = bf.knnMatch(desc1, desc2, k=2)
    good = []
    for m_n in knn:
        if len(m_n) < 2:
            continue
        m, n = m_n
        if m.distance < ratio * n.distance:
            good.append((m.queryIdx, m.trainIdx))
    return good


def _triangulate_track(obs, cams, K):
    """Linear DLT multi-view triangulation.

    obs: list of (cam_list_index, (u,v)).  Returns (X, reproj_err, tri_angle_deg)
    or None if degenerate.
    """
    rows = []
    Ps = []
    for ci, (u, v) in obs:
        P = cams[ci].projection(K)
        Ps.append((ci, P))
        rows.append(u * P[2] - P[0])
        rows.append(v * P[2] - P[1])
    A = np.stack(rows, 0)
    _, _, vt = np.linalg.svd(A)
    Xh = vt[-1]
    if abs(Xh[3]) < 1e-9:
        return None
    X = Xh[:3] / Xh[3]

    # cheirality + reprojection error
    errs = []
    rays = []
    for ci, (u, v) in obs:
        cam = cams[ci]
        Xc = cam.R @ X + cam.t
        if Xc[2] <= 0:
            return None
        proj = K @ Xc
        proj = proj[:2] / proj[2]
        errs.append(np.hypot(*(proj - np.array([u, v]))))
        rays.append((X - cam.center) / (np.linalg.norm(X - cam.center) + 1e-12))
    reproj = float(np.mean(errs))
    # max pairwise ray angle = triangulation angle
    max_ang = 0.0
    for a in range(len(rays)):
        for b in range(a + 1, len(rays)):
            c = np.clip(np.dot(rays[a], rays[b]), -1, 1)
            max_ang = max(max_ang, np.degrees(np.arccos(c)))
    return X, reproj, max_ang


def reconstruct(frames: list[np.ndarray], K: np.ndarray, *,
                masks: Optional[list[np.ndarray]] = None,
                positions: Optional[np.ndarray] = None,
                nfeatures: int = 4000, ratio: float = 0.75,
                max_reproj: float = 4.0, min_tri_angle: float = 1.0,
                progress: Progress = _noop) -> ReconResult:
    """Run incremental SfM over an ordered list of BGR keyframes.

    ``masks`` (optional) are per-frame uint8 masks where 0 = ignore (dynamic).
    ``positions`` (optional, N x 3) are per-frame GPS/ENU camera positions used
    to propose overlapping image pairs by spatial proximity -- this makes the
    matcher robust to non-sequential capture orders (e.g. lawn-mower aerial
    mapping grids), not just continuous video passes.
    Returns a :class:`ReconResult` in an arbitrary metric-consistent frame
    (scale is recovered later by GPS alignment).
    """
    n = len(frames)
    if n < 2:
        raise ValueError("need >= 2 keyframes for reconstruction")
    K = np.asarray(K, float)

    # 1) Features
    progress("features", 0.0)
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    kpts, descs = [], []
    for i in range(n):
        mi = masks[i] if masks is not None else None
        kp, desc = _detect(grays[i], mi, nfeatures)
        kpts.append(kp)
        descs.append(desc)
        progress("features", (i + 1) / n)

    # 2) Match sequential pairs (+ one skip) plus GPS-proximity neighbours, then
    #    geometric-verify.  Proximity pairs make grid/aerial captures work.
    progress("matching", 0.0)
    pair_set = set((i, i + 1) for i in range(n - 1))
    pair_set |= set((i, i + 2) for i in range(n - 2))
    if positions is not None and len(positions) == n and n > 3:
        from scipy.spatial import cKDTree
        pos = np.asarray(positions, float)
        kk = min(7, n)
        tree = cKDTree(pos)
        for i in range(n):
            _, idx = tree.query(pos[i], k=kk)
            for j in np.atleast_1d(idx):
                if int(j) != i:
                    pair_set.add((min(i, int(j)), max(i, int(j))))
    pairs = sorted(pair_set)
    uf = _UnionFind()
    pair_inliers: dict = {}
    for k, (i, j) in enumerate(pairs):
        good = _match(descs[i], descs[j], ratio)
        if len(good) < 20:
            continue
        pi = np.float32([kpts[i][a].pt for a, _ in good])
        pj = np.float32([kpts[j][b].pt for _, b in good])
        E, mask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, 1.0)
        if E is None or mask is None:
            continue
        mask = mask.ravel().astype(bool)
        inl = [g for g, m in zip(good, mask) if m]
        pair_inliers[(i, j)] = (inl, int(mask.sum()))
        for a, b in inl:
            uf.union((i, a), (j, b))
        progress("matching", (k + 1) / len(pairs))

    # 3) Build tracks: node -> track id; collect observations per track
    tracks: dict = {}
    for i in range(n):
        for a in range(len(kpts[i])):
            node = (i, a)
            if node in uf.parent:
                root = uf.find(node)
                tracks.setdefault(root, {})[i] = a  # one obs per frame per track
    # keep multi-view tracks
    tracks = {r: obs for r, obs in tracks.items() if len(obs) >= 2}

    # 4) Two-view initialisation from the consecutive pair with most inliers
    init_pair = None
    best = 0
    for (i, j), (inl, cnt) in pair_inliers.items():
        if j == i + 1 and cnt > best:
            best, init_pair = cnt, (i, j)
    if init_pair is None:
        init_pair = min(pair_inliers, key=lambda p: p[0]) if pair_inliers else (0, 1)
    i0, j0 = init_pair
    progress("initialize", 0.2)
    inl0, _ = pair_inliers[init_pair]
    pi = np.float32([kpts[i0][a].pt for a, _ in inl0])
    pj = np.float32([kpts[j0][b].pt for _, b in inl0])
    E, mask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, 1.0)
    _, Rrel, trel, _ = cv2.recoverPose(E, pi, pj, K, mask=mask)

    cams: dict = {}
    cams[i0] = Camera(i0, np.eye(3), np.zeros(3))
    cams[j0] = Camera(j0, Rrel, trel.ravel())

    # 5) Triangulate + incrementally register remaining frames by PnP
    point_of_track: dict = {}     # track root -> (X, reproj, angle, obs_count)

    def _retriangulate():
        for root, obs in tracks.items():
            reg_obs = [(f, kpts[f][a].pt) for f, a in obs.items() if f in cams]
            if len(reg_obs) < 2:
                continue
            cam_list = list(cams.values())
            idx = {c.frame_index: k for k, c in enumerate(cam_list)}
            packed = [(idx[f], pt) for f, pt in reg_obs]
            out = _triangulate_track(packed, cam_list, K)
            if out is None:
                continue
            X, reproj, ang = out
            if reproj > max_reproj or ang < min_tri_angle:
                continue
            point_of_track[root] = (X, reproj, ang, len(reg_obs))

    _retriangulate()

    order = sorted(set(range(n)) - {i0, j0})
    retri_every = 4  # amortise the O(tracks) retriangulation pass
    for step, f in enumerate(order):
        # gather 2D-3D correspondences from tracks with a point
        obj_pts, img_pts = [], []
        for root, (X, *_ ) in point_of_track.items():
            obs = tracks[root]
            if f in obs:
                obj_pts.append(X)
                img_pts.append(kpts[f][obs[f]].pt)
        if len(obj_pts) >= 6:
            obj = np.asarray(obj_pts, float)
            img = np.asarray(img_pts, float)
            ok, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj, img, K, None, reprojectionError=4.0,
                confidence=0.999, iterationsCount=200, flags=cv2.SOLVEPNP_EPNP)
            if ok and inliers is not None and len(inliers) >= 6:
                R, _ = cv2.Rodrigues(rvec)
                cams[f] = Camera(f, R, tvec.ravel())
                if step % retri_every == 0:
                    _retriangulate()
        progress("registering", (step + 1) / max(1, len(order)))
    _retriangulate()  # final pass over all registered cameras

    # 6) Assemble point cloud with colour + confidence
    progress("fusion", 0.0)
    pts, cols, conf, oc, rep, ang = [], [], [], [], [], []
    for root, (X, reproj, tri, cnt) in point_of_track.items():
        obs = tracks[root]
        # colour from first registered observation
        f = next(fr for fr in obs if fr in cams)
        u, v = kpts[f][obs[f]].pt
        h, w = grays[f].shape
        col = frames[f][int(np.clip(v, 0, h - 1)), int(np.clip(u, 0, w - 1))]
        pts.append(X)
        cols.append(col[::-1])  # BGR->RGB
        oc.append(cnt)
        rep.append(reproj)
        ang.append(tri)
        # confidence: more observations, lower reproj err, wider angle -> higher
        c_obs = min(1.0, (cnt - 2) / 4.0)
        c_rep = max(0.0, 1.0 - reproj / max_reproj)
        c_ang = min(1.0, tri / 10.0)
        conf.append(float(0.4 * c_obs + 0.35 * c_rep + 0.25 * c_ang))

    pts = np.array(pts) if pts else np.zeros((0, 3))
    result = ReconResult(
        points=pts,
        colors=np.array(cols, np.uint8) if cols else np.zeros((0, 3), np.uint8),
        confidence=np.array(conf) if conf else np.zeros(0),
        obs_count=np.array(oc, int) if oc else np.zeros(0, int),
        reproj_err=np.array(rep) if rep else np.zeros(0),
        tri_angle=np.array(ang) if ang else np.zeros(0),
        cameras=[cams[f] for f in sorted(cams)],
        K=K,
    )
    result.stats = {
        "n_keyframes": n,
        "n_registered": len(cams),
        "registered_fraction": len(cams) / n,
        "n_points": int(pts.shape[0]),
        "median_reproj_err": float(np.median(rep)) if rep else None,
        "p90_reproj_err": float(np.percentile(rep, 90)) if rep else None,
        "mean_track_length": float(np.mean(oc)) if oc else None,
        "mean_tri_angle": float(np.mean(ang)) if ang else None,
    }
    progress("fusion", 1.0)
    return result
