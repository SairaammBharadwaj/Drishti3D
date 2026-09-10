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

from . import bundle

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
    # Propagated positional uncertainty, aligned with ``points`` (see
    # :mod:`uncertainty`).  ``point_cov`` is in the reconstruction frame and must
    # be pushed through the GNSS similarity before it means metres on the ground.
    point_cov: np.ndarray | None = None        # (N,3,3)
    point_sigma: np.ndarray | None = None      # (N,) isotropic-equivalent 1-sigma
    point_sigma_major: np.ndarray | None = None
    point_observable: np.ndarray | None = None
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


class _KP:
    """Minimal keypoint holding a ``.pt``, so backends can return plain arrays.

    The reconstruction only ever reads ``.pt`` from a keypoint, and requiring
    every backend to construct ``cv2.KeyPoint`` objects would be a pointless
    constraint on a learned detector that natively produces an (N,2) array.
    """

    __slots__ = ("pt",)

    def __init__(self, xy):
        self.pt = (float(xy[0]), float(xy[1]))


def _orientation_mst(grays, masks, pairs, nfeatures, backend, ratio, K,
                     progress=_noop, min_inliers: int = 30,
                     e_ransac_px: float = 1.0):
    """Assign one canonical rotation per frame by propagating over strong pairs.

    Two frames of a lawn-mower survey flown on opposite strips see the same ground
    ~180 degrees apart, and learned descriptors are not rotation invariant. Each
    frame therefore needs a single chosen orientation -- one descriptor set per
    frame, so a physical point stays one track instead of splitting.

    The hard part is *which* orientation, and propagation order decides it.
    Following capture order fails: at a strip turn consecutive frames barely
    overlap, the relative rotation measured there is a guess, and a chain carries
    that mistake to every later frame (measured: 7 of 122 cameras registered).

    So relative rotations are measured for every candidate pair, and absolute
    orientations are propagated over a **maximum spanning tree weighted by
    verified inlier count** -- strongest links first, weak ones never used to
    decide anything. A frame reachable only through a weak edge keeps 0 rather
    than inheriting a guess.

    Returns ``(orientation_deg per frame, diagnostics)``.
    """
    n = len(grays)
    det: dict = {}

    def feats(i, deg):
        key = (i, deg % 360)
        if key not in det:
            mi = masks[i] if masks is not None else None
            det[key] = (_detect(grays[i], mi, nfeatures, backend=backend)
                        if key[1] == 0 else
                        _detect_oriented(grays[i], mi, nfeatures, backend, key[1]))
        return det[key]

    def verify(i, j, deg):
        kp_i, d_i = feats(i, 0)
        kp_j, d_j = feats(j, deg)
        if d_i is None or d_j is None or len(kp_i) < 8 or len(kp_j) < 8:
            return 0
        good = _match(d_i, d_j, ratio, backend=backend, kp1=kp_i, kp2=kp_j,
                      shape=grays[i].shape)
        if len(good) < 20:
            return 0
        pi = np.float32([kp_i[a].pt for a, _ in good])
        pj = np.float32([kp_j[b].pt for _, b in good])
        E, mask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, e_ransac_px)
        return 0 if (E is None or mask is None) else int(mask.sum())

    # Relative rotation for each candidate pair: the rotation of j (relative to
    # i) that maximises verified inliers.
    edges = []
    for k, (i, j) in enumerate(pairs):
        best_deg, best_n = 0, verify(i, j, 0)
        if best_n < min_inliers:
            for deg in (90, 180, 270):
                cnt = verify(i, j, deg)
                if cnt > best_n:
                    best_deg, best_n = deg, cnt
        if best_n >= min_inliers:
            edges.append((best_n, i, j, best_deg))
        if k % 50 == 0:
            progress("features", 0.5 * (k + 1) / max(1, len(pairs)))
        # Keep the working set bounded; only 0-degree sets are reused often.
        if len(det) > 200:
            for key in [x for x in det if x[1] != 0][:100]:
                det.pop(key, None)

    # Maximum spanning tree by inlier count, grown greedily from the strongest
    # edge: a frame's orientation is only ever decided by the best evidence
    # connecting it to something already oriented.
    edges.sort(reverse=True)
    ori = [None] * n
    uf = _UnionFind()
    used = 0
    if edges:
        ori[edges[0][1]] = 0
    # Repeat passes until nothing new is anchored. A single descending-weight
    # pass silently drops any edge whose two endpoints are both unanchored at the
    # moment it is examined, and never revisits it -- which left 68 of 122 frames
    # unanchored and cost half the registrations. Re-scanning propagates outward
    # from every anchored frame while still consuming edges strongest-first.
    changed = True
    while changed:
        changed = False
        for cnt, i, j, deg in edges:
            if uf.find(i) == uf.find(j):
                continue
            if ori[i] is None and ori[j] is None:
                continue
            if ori[i] is None:
                ori[i] = (ori[j] - deg) % 360
            elif ori[j] is None:
                ori[j] = (ori[i] + deg) % 360
            uf.union(i, j)
            used += 1
            changed = True
        # Any frame still unanchored belongs to a component the anchored set
        # cannot reach. Seed the strongest such component and continue, rather
        # than defaulting a third of the survey to an arbitrary 0 degrees.
        if not changed:
            for cnt, i, j, deg in edges:
                if ori[i] is None and ori[j] is None:
                    ori[i] = 0
                    changed = True
                    break
    n_unset = sum(1 for o in ori if o is None)
    ori = [0 if o is None else int(o) for o in ori]
    diag = {"edges_measured": len(edges), "mst_edges_used": used,
            "frames_unanchored": int(n_unset),
            "n_rotated": int(sum(1 for o in ori if o))}
    return ori, diag


def _assign_orientations(grays, masks, nfeatures, backend, ratio, K,
                         progress=_noop):
    """Choose ONE canonical rotation per frame, propagated along the sequence.

    Appending a rotated feature set to a frame was the wrong fix. A frame then
    carries two independent descriptor sets, so pair (i,j) can match into one and
    pair (j,k) into the other -- and the same physical point becomes two separate
    tracks. Tracks stop chaining, which is exactly the symptom that persisted:
    mean track length stuck at 2.34 despite 400 inliers per pair, leaving camera
    positions weakly constrained and georegistration ~8 m off even on the best
    quarter of cameras.

    Instead each frame is detected once, at a single orientation chosen so that it
    agrees with its predecessor. Adjacent strips of a lawn-mower survey are flown
    in opposite directions, so this recovers the ~180 degree flips while leaving
    one feature set per frame and letting tracks chain normally.
    """
    n = len(grays)
    ori = [0] * n
    kp0, d0 = _detect(grays[0], masks[0] if masks is not None else None,
                      nfeatures, backend=backend)
    kps = [kp0]
    descs = [d0]
    for i in range(1, n):
        mi = masks[i] if masks is not None else None
        best_deg, best_n, best = 0, -1, None
        for deg in (0, 90, 180, 270):
            # Bias toward the previous frame's orientation: within a strip the
            # heading does not change, and only a turn should flip it.
            cand_deg = (ori[i - 1] + deg) % 360
            kp_c, d_c = _detect_oriented(grays[i], mi, nfeatures, backend,
                                         cand_deg)
            if d_c is None or len(kp_c) < 8:
                continue
            good = _match(descs[i - 1], d_c, ratio, backend=backend,
                          kp1=kps[i - 1], kp2=kp_c, shape=grays[i].shape)
            if len(good) > best_n:
                best_deg, best_n, best = cand_deg, len(good), (kp_c, d_c)
            if deg == 0 and len(good) >= 200:
                break            # already agrees; no need to try rotations
        if best is None:
            kp_c, d_c = _detect_oriented(grays[i], mi, nfeatures, backend,
                                         ori[i - 1])
            best_deg, best = ori[i - 1], (kp_c, d_c)
        ori[i] = best_deg
        kps.append(best[0])
        descs.append(best[1])
        progress("features", (i + 1) / n)
    return kps, descs, ori


def _detect_oriented(gray, mask, nfeatures, backend, theta_deg):
    """Detect features on a heading-normalised image, in original coordinates.

    Aerial surveys fly adjacent strips in opposite directions, so the same ground
    appears rotated ~180 degrees between them. Learned descriptors (DISK, ALIKED)
    are not rotation invariant, and on the real Bellus set that silently destroyed
    the cross-strip links which make a survey rigid: pairs 3-12 m apart matched 0-2
    features at 0 degrees and 505-1753 once rotated.

    The image is rotated to a common heading *for detection and description only*,
    then keypoints are mapped straight back into the original frame. The camera
    model, triangulation and every geometric threshold are therefore untouched --
    only descriptor comparability changes.
    """
    if not theta_deg:
        return _detect(gray, mask, nfeatures, backend=backend)
    h, w = gray.shape[:2]
    c = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(c, float(theta_deg), 1.0)
    rot = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR)
    rmask = None
    if mask is not None:
        rmask = cv2.warpAffine(mask, M, (w, h), flags=cv2.INTER_NEAREST)
    kp, desc = _detect(rot, rmask, nfeatures, backend=backend)
    if not len(kp):
        return kp, desc
    Minv = cv2.invertAffineTransform(M)
    pts = np.array([k.pt for k in kp], np.float32)
    back = (Minv[:, :2] @ pts.T).T + Minv[:, 2]
    # Drop anything that maps outside the original frame: warpAffine fills the
    # corners with black, and features found there are artefacts of the rotation.
    keep = ((back[:, 0] >= 0) & (back[:, 0] < w) &
            (back[:, 1] >= 0) & (back[:, 1] < h))
    kp2 = [_KP(p) for p in back[keep]]
    d2 = None if desc is None else np.asarray(desc)[keep]
    return kp2, d2


def _detect(gray, masks_i, nfeatures, backend=None):
    """Detect features, via the pluggable backend (SIFT by default)."""
    if backend is None:
        sift = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=0.02)
        return sift.detectAndCompute(gray, masks_i)
    pts, desc = backend.detect(gray, masks_i)
    return [_KP(p) for p in pts], desc


def _match(desc1, desc2, ratio=0.75, backend=None, kp1=None, kp2=None,
           shape=None):
    """Match descriptors, via the pluggable backend (SIFT ratio test by default)."""
    if backend is not None:
        k1 = None if kp1 is None else np.array([k.pt for k in kp1], np.float32)
        k2 = None if kp2 is None else np.array([k.pt for k in kp2], np.float32)
        return backend.match(desc1, desc2, kp1=k1, kp2=k2, shape=shape)
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


def _score_init_pair(kpts, K, i, j, inl, min_tri_angle, e_ransac_px=1.0):
    """Score a candidate seed pair. Higher is better; ``None`` means unusable.

    Inlier count alone is the wrong criterion: it is maximised by the pair with
    the *smallest* baseline, because nearly identical images match almost
    perfectly -- and then triangulate at a near-zero angle, which is exactly the
    configuration that produces a badly scaled reconstruction.

    A pair is judged on the geometry it can actually deliver:

    * **Parallax.** Median triangulation angle of the two-view reconstruction.
    * **Not homographic.** If a homography explains nearly as many inliers as the
      essential matrix, the motion is rotation-only or the scene is planar; the
      baseline is unrecoverable and the pair is rejected.
    * **Spread.** Inliers covering the frame constrain pose far better than a
      tight cluster, so the image-plane spread is a multiplier.
    * **Cheirality.** The fraction of points reconstructed in front of both
      cameras, which catches a wrong pose decomposition.
    """
    if len(inl) < 20:
        return None
    pi = np.float32([kpts[i][a].pt for a, _ in inl])
    pj = np.float32([kpts[j][b].pt for _, b in inl])

    E, emask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, e_ransac_px)
    if E is None or emask is None or E.shape != (3, 3):
        return None
    n_e = int(emask.sum())
    if n_e < 15:
        return None

    # Reject rotation-only / planar pairs: there the homography explains the
    # correspondences just as well and the translation direction is meaningless.
    H, hmask = cv2.findHomography(pi, pj, cv2.RANSAC, 3.0)
    if H is not None and hmask is not None:
        if float(hmask.sum()) / max(n_e, 1) > 0.85:
            return None

    ok, R, t, pmask, X = cv2.recoverPose(
        E, pi, pj, K, distanceThresh=1000.0, mask=emask.copy())
    if not ok or X is None or X.shape[1] < 10:
        return None
    good = (pmask.ravel() > 0)
    cheirality = float(good.mean())
    if cheirality < 0.5 or good.sum() < 15:
        return None

    Xw = (X[:3] / np.where(np.abs(X[3]) < 1e-12, 1e-12, X[3])).T[good]
    c1 = np.zeros(3)
    c2 = (-R.T @ t).ravel()
    r1 = Xw - c1
    r2 = Xw - c2
    r1 /= (np.linalg.norm(r1, axis=1, keepdims=True) + 1e-12)
    r2 /= (np.linalg.norm(r2, axis=1, keepdims=True) + 1e-12)
    angles = np.degrees(np.arccos(np.clip((r1 * r2).sum(1), -1, 1)))
    med_angle = float(np.median(angles))
    if med_angle < max(min_tri_angle, 1.5):
        return None

    inl_pts = pi[good[:len(pi)]] if good.shape[0] >= len(pi) else pi
    spread = float(np.sqrt(inl_pts.var(0).sum())) if len(inl_pts) > 2 else 0.0

    # Parallax is the scarce quantity, so it drives the score; support and
    # spread break ties between pairs that all have enough of it.
    return (med_angle * np.sqrt(good.sum()) * (1.0 + spread / 100.0) * cheirality,
            {"median_tri_angle": med_angle, "n_inliers": int(good.sum()),
             "cheirality": cheirality, "spread_px": spread})


def _connectivity(pair_inliers, i, j) -> int:
    """How many other frames are verified against *both* members of a pair.

    A seed pair needs more than good geometry: the reconstruction has to be able
    to grow from it. On a lawn-mower grid two frames from different strips can
    view the same ground patch with excellent parallax while almost nothing else
    observes that patch -- an isolated island the next-best-view scheduler cannot
    extend. Measured on the real Bellus set, exactly that happened: a pair with
    19.6 deg parallax and 330 inliers registered 2 cameras out of 61.
    """
    nbr_i, nbr_j = set(), set()
    for (a, b) in pair_inliers:
        if a == i:
            nbr_i.add(b)
        elif b == i:
            nbr_i.add(a)
        if a == j:
            nbr_j.add(b)
        elif b == j:
            nbr_j.add(a)
    return len((nbr_i & nbr_j) - {i, j})


def _select_init_pair(pair_inliers, kpts, K, min_tri_angle, progress=None,
                      e_ransac_px=1.0):
    """Pick the best-conditioned seed pair that the model can actually grow from.

    Candidates are ranked by verified inlier count only to bound the work; the
    actual choice combines :func:`_score_init_pair` (can this pair be triangulated
    well?) with :func:`_connectivity` (can the rest of the sequence attach to it?).
    Optimising the first alone produces geometrically perfect islands.
    """
    # Candidates must be sampled across the *baseline* spectrum, not by inlier
    # count.  Ranking by inlier count and truncating selects precisely the
    # adjacent, zero-parallax pairs this function exists to reject -- the
    # wide-baseline pairs sit at the bottom of that ordering and would never be
    # scored at all.  Bucket by temporal separation and take the best-supported
    # few from each bucket, so every scale gets a fair hearing.
    buckets: dict = {}
    for (i, j), (inl, cnt) in pair_inliers.items():
        buckets.setdefault(j - i, []).append(((i, j), inl, cnt))
    cands = []
    for sep in sorted(buckets):
        top = sorted(buckets[sep], key=lambda t: -t[2])[:4]
        cands.extend(((ij, (inl, cnt)) for ij, inl, cnt in top))
    # Best co-visibility available, used to normalise the connectivity term so it
    # is a relative preference rather than an arbitrary absolute count.
    max_conn = max((_connectivity(pair_inliers, i, j) for (i, j), _ in cands),
                   default=0)
    best, best_score, best_info = None, -np.inf, None
    for (i, j), (inl, _cnt) in cands:
        out = _score_init_pair(kpts, K, i, j, inl, min_tri_angle, e_ransac_px)
        if out is None:
            continue
        score, info = out
        # Weight by how well the rest of the sequence can attach to this pair.
        # The floor keeps a well-conditioned pair viable when co-visibility is
        # uniformly low, rather than zeroing every candidate.
        conn = _connectivity(pair_inliers, i, j)
        info["connectivity"] = conn
        if max_conn > 0:
            score *= 0.25 + 0.75 * (conn / max_conn)
        if score > best_score:
            best, best_score, best_info = (i, j), score, info
    return best, best_info


def _point_stats(X, obs, cams, K):
    """Reprojection error and triangulation angle for a *given* 3D point.

    Separate from :func:`_triangulate_track` because after bundle adjustment the
    point position is already optimal -- re-triangulating it linearly would throw
    away the refinement and report statistics for a point we are not shipping.
    Returns ``(reproj_px, tri_angle_deg)`` or ``None`` if the point falls behind
    any camera that claims to see it.
    """
    errs, rays = [], []
    for ci, (u, v) in obs:
        cam = cams[ci]
        Xc = cam.R @ X + cam.t
        if Xc[2] <= 0:
            return None
        proj = K @ Xc
        proj = proj[:2] / proj[2]
        errs.append(np.hypot(*(proj - np.array([u, v]))))
        d = X - cam.center
        rays.append(d / (np.linalg.norm(d) + 1e-12))
    max_ang = 0.0
    for a in range(len(rays)):
        for b in range(a + 1, len(rays)):
            c = np.clip(np.dot(rays[a], rays[b]), -1, 1)
            max_ang = max(max_ang, np.degrees(np.arccos(c)))
    return float(np.mean(errs)), max_ang


def _ba_problem(tracks, point_of_track, cams, kpts):
    """Pack the current reconstruction into bundle-adjustment arrays.

    Returns ``(cam_frames, roots, rvecs, tvecs, pts, cam_idx, pt_idx, uv)`` where
    ``cam_frames`` and ``roots`` give the mapping back to frame indices and track
    ids, so the refined values can be written straight back.
    """
    cam_frames = sorted(cams)
    cam_pos = {f: i for i, f in enumerate(cam_frames)}
    roots = [r for r in point_of_track if any(f in cams for f in tracks[r])]
    root_pos = {r: i for i, r in enumerate(roots)}

    cam_idx, pt_idx, uv = [], [], []
    for r in roots:
        for f, a in tracks[r].items():
            if f in cams:
                cam_idx.append(cam_pos[f])
                pt_idx.append(root_pos[r])
                uv.append(kpts[f][a].pt)
    if not cam_idx:
        return None

    rvecs = np.array([cv2.Rodrigues(cams[f].R)[0].ravel() for f in cam_frames])
    tvecs = np.array([np.asarray(cams[f].t, float).ravel() for f in cam_frames])
    pts = np.array([point_of_track[r][0] for r in roots], float)
    return (cam_frames, roots, rvecs, tvecs, pts,
            np.asarray(cam_idx, int), np.asarray(pt_idx, int),
            np.asarray(uv, float))


def reconstruct(frames: list[np.ndarray], K: np.ndarray, *,
                masks: Optional[list[np.ndarray]] = None,
                positions: Optional[np.ndarray] = None,
                nfeatures: int = 4000, ratio: float = 0.75,
                max_reproj: float = 4.0, min_tri_angle: float = 1.0,
                matcher: str = "sift", matcher_options: dict | None = None,
                orientations=None, rotation_robust: bool = True,
                canonical_orientation_opt: bool = False,
                # 10, not 14. Raised to 14 alongside the (now-disabled)
                # separation prune on the theory that pruning junk freed budget
                # for real neighbours. With the prune off, the extra neighbours
                # are pure additions to the pair graph, and measured on the
                # synthetic regimes they degraded ATE rather than helping --
                # more candidate pairs is not the same as more useful geometry.
                gps_radius_steps: float = 8.0, max_gps_neighbours: int = 10,
                # Separation-based pruning is OFF by default. It was added to
                # drop the 450 physically-non-overlapping pairs a stride graph
                # proposes on a 122-image photo survey, and it does that well --
                # but a threshold in units of the flight step does not transfer.
                # Single-pass video has a tiny step (~0.75 m over 60 frames), so
                # 1.8 steps is 1.35 m and deletes precisely the wide-baseline
                # stride pairs that exist to create parallax. Measured cost on the
                # target single-pass regime: ATE 0.020 -> 0.102 m and
                # 0.074 -> 0.309 m on two cells.
                #
                # The neighbour cap already bounds cost. A correct version of this
                # filter needs predicted ground overlap (footprint from focal
                # length and height above ground), not a multiple of the step.
                max_pair_sep_steps: float | None = None,
                # Epipolar RANSAC band. 1.0 px suits imagery that really is a
                # pinhole -- synthetic renders, or frames whose distortion has
                # been corrected. Loosening it there is actively harmful: it
                # admits bad correspondences into the two-view initialisation
                # and the synthetic end-to-end reconstruction collapses to zero
                # points. Real uncorrected lenses need the opposite; the pipeline
                # raises this to ~3 px when it could not undistort (see
                # PipelineParams.e_ransac_px), matching the thresholds already
                # used for homography (3.0) and PnP (4.0).
                e_ransac_px: float = 1.0,
                max_pairs: int | None = 3000, max_rot_cache: int = 48,
                do_ba: bool = True, ba_every: int = 8,
                refine_focal: bool = False, refine_distortion: bool = False,
                progress: Progress = _noop) -> ReconResult:
    """Run incremental SfM over an ordered list of BGR keyframes.

    ``masks`` (optional) are per-frame uint8 masks where 0 = ignore (dynamic).
    ``positions`` (optional, N x 3) are per-frame GPS/ENU camera positions used
    to propose overlapping image pairs by spatial proximity -- this makes the
    matcher robust to non-sequential capture orders (e.g. lawn-mower aerial
    mapping grids), not just continuous video passes.

    ``do_ba`` runs sparse bundle adjustment (see :mod:`bundle`): intermediate
    solves every ``ba_every`` newly registered cameras to stop drift accumulating
    while the sequence is still being built, then one final global solve.  Each
    solve is accepted only if it lowers the reprojection RMSE, so enabling it
    cannot make the reconstruction worse than the incremental estimate.
    Returns a :class:`ReconResult` in an arbitrary metric-consistent frame
    (scale is recovered later by GPS alignment).
    """
    n = len(frames)
    if n < 2:
        raise ValueError("need >= 2 keyframes for reconstruction")
    K = np.asarray(K, float)

    # `matcher="sift"` keeps the original inline code path exactly, so every
    # previously archived benchmark stays comparable with new runs.
    backend = None
    backend_info = {"name": "sift", "kind": "classical"}
    if matcher and matcher.lower() != "sift":
        from . import features as featmod
        backend = featmod.create(matcher, **(matcher_options or {}))
        backend_info = backend.info().to_dict()
    rotation_sensitive = backend_info.get("kind") == "learned"

    # 1) Features
    progress("features", 0.0)
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    kpts, descs = [], []

    # 2) Build the pair graph, then geometric-verify each candidate.
    #
    # Adjacent video frames match beautifully and triangulate terribly: over a
    # 44 m pass at ~45 m depth, consecutive frames subtend about 1 degree, which
    # is below the angle at which a point can be triangulated at all.  A graph of
    # only near-adjacent pairs therefore contains no well-conditioned pair
    # *anywhere*, and no amount of downstream optimisation can recover the
    # baseline that was never observed.
    #
    # So pairs are proposed at geometrically spaced strides (1, 2, 4, 8, 16...),
    # which adds wide-baseline candidates at O(n log n) cost rather than the
    # O(n^2) of exhaustive matching.  GPS proximity is used to catch non-sequential
    # capture orders (lawn-mower grids), but by *distance band* rather than
    # nearest-neighbour: the nearest frames in space are precisely the ones with
    # the least parallax.
    progress("matching", 0.0)
    pair_set: set = set()
    gps_pairs: set = set()          # proposed by spatial proximity, never pruned
    stride = 1
    while stride < max(2, n):
        pair_set |= set((i, i + stride) for i in range(n - stride))
        stride *= 2
    if positions is not None and len(positions) == n and n > 3:
        from scipy.spatial import cKDTree
        pos = np.asarray(positions, float)
        tree = cKDTree(pos)
        steps = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        step = float(np.median(steps[steps > 0])) if np.any(steps > 0) else 0.0
        # Radius and count do different jobs, and conflating them broke a whole
        # regime. The radius decides *which* frames are eligible; the neighbour
        # cap decides *how many* are taken. Cost is bounded by the cap alone
        # (<= max_gps_neighbours * n pairs), so the radius can stay generous.
        #
        # Tightening the radius instead (8 steps -> 2.5) did bound cost, but on a
        # nadir grid the adjacent strip sits ~6 strip-widths away in units of the
        # along-track step: a small radius cannot reach it, and the cross-strip
        # links that make a survey rigid vanish. Measured cost of that mistake on
        # the synthetic nadir regime: ATE 0.17-2.4 m -> 0.97-3.5 m and scale error
        # 0.0029 -> 0.0539.
        radius = max(step * gps_radius_steps, 1e-6)
        for i in range(n):
            idx = tree.query_ball_point(pos[i], radius)
            if len(idx) > max_gps_neighbours + 1:
                # Keep the nearest few: a rigid graph needs enough links, not
                # every link, and the cost of the extras is quadratic.
                d = np.linalg.norm(pos[np.asarray(idx, int)] - pos[i], axis=1)
                idx = [idx[k] for k in np.argsort(d)[: max_gps_neighbours + 1]]
            for j in idx:
                j = int(j)
                if j != i:
                    pair_set.add((min(i, j), max(i, j)))
                    gps_pairs.add((min(i, j), max(i, j)))
    pairs = sorted(pair_set)

    # Prune pairs the flight geometry says cannot overlap. Index strides are a
    # proxy for "nearby", and on a 20-strip survey that proxy is wrong most of
    # the time: measured on the real Bellus set, 450 of 1,291 proposed pairs
    # (35%) were separated by more than the camera's ground footprint and so had
    # under 20% predicted overlap -- they could never match, but each one still
    # cost a full descriptor match and a RANSAC.
    #
    # GNSS separation answers the question directly. The cutoff is expressed in
    # units of the median flight step because that is available without knowing
    # the flying height: a mapping flight is planned for high forward overlap, so
    # frames more than a couple of steps apart have little left in common.
    if positions is not None and len(positions) == n and n > 3 and max_pair_sep_steps:
        pos = np.asarray(positions, float)
        steps = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        step = float(np.median(steps[steps > 0])) if np.any(steps > 0) else 0.0
        if step > 0:
            limit = step * max_pair_sep_steps
            # Prune ONLY the index-stride candidates. GNSS-proximity pairs were
            # already selected *because* they are spatially closest, and on a
            # lawn-mower grid the frame overlapping from the adjacent strip is
            # far away in index while near in space -- measured at 3.7 steps on
            # the real survey and 7.0 on the synthetic nadir grid. Applying the
            # separation limit to them deleted 86% and 100% of the cross-strip
            # links respectively: the same connectivity the GNSS radius exists to
            # create, thrown away a few lines later.
            backbone = {(i, i + 1) for i in range(n - 1)}
            pairs = sorted(
                {(i, j) for (i, j) in pairs
                 if (i, j) in gps_pairs or (i, j) in backbone
                 or np.linalg.norm(pos[i] - pos[j]) <= limit})

    if max_pairs and len(pairs) > max_pairs:
        # Hard ceiling so a pathological graph cannot consume the machine.
        # Sequential pairs are kept preferentially: they carry the sequence.
        pairs.sort(key=lambda ij: (ij[1] - ij[0]))
        pairs = sorted(pairs[:max_pairs])


    # One canonical orientation per frame for rotation-sensitive backends, so a
    # frame has exactly one descriptor set and tracks can chain through it.
    # Canonical per-frame orientation is OFF by default. The idea is right --
    # one descriptor set per frame lets tracks chain -- but propagating the
    # orientation along the sequential chain is too fragile: at a lawn-mower
    # strip turn consecutive frames barely overlap, the choice there is a guess,
    # and because it is a chain one bad link corrupts every frame after it.
    # Measured on the real survey: 99/122 cameras registered with the per-pair
    # retry, 7/122 with sequential canonical assignment.
    #
    # Making this work needs the orientation propagated over a spanning tree of
    # the *strongest* pairs (or seeded from GPS-adjacent neighbours), not along
    # capture order. Left in place, opt-in, for that work.
    # A rotation-sensitive backend needs one chosen orientation per frame, so a
    # physical point stays a single track instead of splitting across two
    # descriptor sets. Orientations are propagated over a maximum spanning tree
    # of the strongest verified pairs -- never along capture order, which fails
    # at strip turns (see :func:`_orientation_mst`).
    frame_orientations = [0] * n
    orient_diag: dict = {}
    canonical_orientation = bool(rotation_robust and rotation_sensitive and n >= 2)
    if canonical_orientation:
        frame_orientations, orient_diag = _orientation_mst(
            grays, masks, pairs, nfeatures, backend, ratio, K, progress,
            e_ransac_px=e_ransac_px)
    for i in range(n):
        mi = masks[i] if masks is not None else None
        deg = frame_orientations[i]
        kp, desc = (_detect(grays[i], mi, nfeatures, backend=backend) if not deg
                    else _detect_oriented(grays[i], mi, nfeatures, backend, deg))
        kpts.append(kp)
        descs.append(desc)
        progress("features", 0.5 + 0.5 * (i + 1) / n)

    uf = _UnionFind()
    pair_inliers: dict = {}
    # Lazily-built rotated feature sets, used only for pairs that fail upright.
    # Bounded: each entry holds a full descriptor set, and on a large survey an
    # unbounded cache is hundreds of megabytes of descriptors nothing will read
    # again.
    rot_cache: dict = {}

    def _rotated_features(idx, deg):
        key = (idx, deg)
        if key not in rot_cache:
            if len(rot_cache) >= max_rot_cache:
                for k_old in list(rot_cache)[: max(1, max_rot_cache // 4)]:
                    if k_old not in appended_keys:
                        rot_cache.pop(k_old, None)
            mi = masks[idx] if masks is not None else None
            rot_cache[key] = _detect_oriented(grays[idx], mi, nfeatures,
                                              backend, deg)
        return rot_cache[key]

    def _verify(i, j, kp_i, d_i, kp_j, d_j):
        """Match and geometrically verify one pair; returns (inliers, count)."""
        good = _match(d_i, d_j, ratio, backend=backend,
                      kp1=kp_i, kp2=kp_j, shape=grays[i].shape)
        if len(good) < 20:
            return None
        pi = np.float32([kp_i[a].pt for a, _ in good])
        pj = np.float32([kp_j[b].pt for _, b in good])
        E, mask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, e_ransac_px)
        if E is None or mask is None:
            return None
        mask = mask.ravel().astype(bool)
        return [g for g, m in zip(good, mask) if m], int(mask.sum())

    n_rot_rescued = 0
    appended: set = set()
    appended_keys: set = set()      # cache entries that must not be evicted
    for k, (i, j) in enumerate(pairs):
        best = _verify(i, j, kpts[i], descs[i], kpts[j], descs[j])
        best_kp_j, best_deg = kpts[j], 0
        # Aerial surveys fly adjacent strips in opposite directions, so the same
        # ground appears rotated between them. Learned descriptors are not
        # rotation invariant, and on real data this silently destroyed the
        # cross-strip links that make a survey rigid -- pairs metres apart matched
        # 0-2 features upright and 500-1900 once rotated. Retrying is data-driven
        # rather than trusting a GNSS heading, which proved unreliable at strip
        # turns and under gimbal stabilisation.
        # Only learned descriptors need this. SIFT and ORB are rotation
        # invariant by construction, so retrying rotations for them buys nothing
        # and actively harms: it appends near-duplicate features that fragment
        # tracks. Enabling it for SIFT took this dataset from 13 registered
        # cameras to zero.
        # Skip the per-pair retry when frames already carry a canonical
        # orientation: appending a second set here would re-introduce the exact
        # track fragmentation the canonical assignment exists to prevent.
        if (rotation_robust and rotation_sensitive and not canonical_orientation
                and (best is None or best[1] < 40)):
            for deg in (90, 180, 270):
                kp_r, d_r = _rotated_features(j, deg)
                if d_r is None or not len(kp_r):
                    continue
                cand = _verify(i, j, kpts[i], descs[i], kp_r, d_r)
                if cand is not None and (best is None or cand[1] > best[1]):
                    best, best_kp_j, best_deg = cand, kp_r, deg
            if best_deg:
                n_rot_rescued += 1
        if best is None:
            progress("matching", (k + 1) / len(pairs))
            continue
        inl, cnt = best
        if best_deg and (j, best_deg) not in appended:
            # Rotated keypoints are already mapped back into the original image
            # frame, but they are a *different index set*. They must be APPENDED,
            # never substituted: union-find nodes are (frame, keypoint index), so
            # replacing the list would silently re-point every track built from
            # this frame in an earlier pair at the wrong features.
            #
            # Each (frame, rotation) is appended at most once. Without that guard
            # a frame rescued by several pairs accumulates duplicate feature sets,
            # and the learned matcher's O(N^2) attention runs the GPU out of
            # memory -- which is exactly how this first failed.
            appended.add((j, best_deg))
            appended_keys.add((j, best_deg))
            base = len(kpts[j])
            kp_r, d_r = rot_cache[(j, best_deg)]
            kpts[j] = list(kpts[j]) + list(kp_r)
            descs[j] = (d_r if descs[j] is None else
                        np.vstack([np.asarray(descs[j]), np.asarray(d_r)]))
            inl = [(a, base + b) for a, b in inl]
        elif best_deg:
            # This rotation was already merged into frame j by an earlier pair;
            # re-verify against the extended set so indices stay consistent.
            re_best = _verify(i, j, kpts[i], descs[i], kpts[j], descs[j])
            if re_best is None:
                progress("matching", (k + 1) / len(pairs))
                continue
            inl, cnt = re_best
        pair_inliers[(i, j)] = (inl, cnt)
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

    # 4) Two-view initialisation, chosen for the geometry it can deliver
    init_pair, init_info = _select_init_pair(pair_inliers, kpts, K, min_tri_angle,
                                             e_ransac_px=e_ransac_px)
    if init_pair is None:
        # Nothing had usable parallax.  Fall back to the old rule so a weak
        # capture still produces something, but record why.
        best = 0
        for (i, j), (inl, cnt) in pair_inliers.items():
            if j == i + 1 and cnt > best:
                best, init_pair = cnt, (i, j)
        if init_pair is None:
            init_pair = (min(pair_inliers, key=lambda p: p[0])
                         if pair_inliers else (0, 1))
        init_info = {"fallback": "no pair met the parallax/cheirality criteria"}
    i0, j0 = init_pair
    progress("initialize", 0.2)
    inl0, _ = pair_inliers[init_pair]
    pi = np.float32([kpts[i0][a].pt for a, _ in inl0])
    pj = np.float32([kpts[j0][b].pt for _, b in inl0])
    E, mask = cv2.findEssentialMat(pi, pj, K, cv2.RANSAC, 0.999, e_ransac_px)
    _, Rrel, trel, _ = cv2.recoverPose(E, pi, pj, K, mask=mask)

    cams: dict = {}
    cams[i0] = Camera(i0, np.eye(3), np.zeros(3))
    cams[j0] = Camera(j0, Rrel, trel.ravel())

    # 5) Triangulate + incrementally register remaining frames by PnP
    point_of_track: dict = {}     # track root -> (X, reproj, angle, obs_count)
    retry_later: set = set()      # frames parked for a second attempt
    # frame -> [track roots it observes that currently have a 3D point].
    # Without this, finding a frame's 2D-3D correspondences means scanning every
    # reconstructed point, once per candidate frame, once per registration step.
    obs_index: dict = {}

    def _rebuild_obs_index():
        obs_index.clear()
        for root in point_of_track:
            for f in tracks[root]:
                obs_index.setdefault(f, []).append(root)

    def _retriangulate():
        # Hoisted: the camera table is identical for every track in this pass,
        # and rebuilding it per track costs O(tracks x cameras) for nothing.
        cam_list = list(cams.values())
        idx = {c.frame_index: k for k, c in enumerate(cam_list)}
        for root, obs in tracks.items():
            reg_obs = [(f, kpts[f][a].pt) for f, a in obs.items() if f in cams]
            if len(reg_obs) < 2:
                # Not enough registered views to support a point any more.
                point_of_track.pop(root, None)
                continue
            packed = [(idx[f], pt) for f, pt in reg_obs]
            out = _triangulate_track(packed, cam_list, K)
            if out is None:
                # Cheirality failed against the *current* cameras.
                point_of_track.pop(root, None)
                continue
            X, reproj, ang = out
            if reproj > max_reproj or ang < min_tri_angle:
                # Drop it rather than `continue`: leaving the previous pass's
                # value in place would ship a point that fails its own quality
                # gate, carrying statistics measured against older poses.
                point_of_track.pop(root, None)
                continue
            point_of_track[root] = (X, reproj, ang, len(reg_obs))
        _rebuild_obs_index()

    ba_log: list = []

    def _run_ba(tag: str, *, max_nfev: int, focal: bool, distortion: bool):
        """Bundle adjust in place; returns the BAResult or None if not run."""
        nonlocal K
        if not do_ba or len(cams) < 3 or len(point_of_track) < 20:
            return None
        prob = _ba_problem(tracks, point_of_track, cams, kpts)
        if prob is None:
            return None
        cam_frames, roots, rvecs, tvecs, pts, ci, pi, uv = prob
        try:
            res = bundle.bundle_adjust(
                rvecs, tvecs, pts, ci, pi, uv, K,
                refine_focal=focal, refine_distortion=distortion,
                max_nfev=max_nfev)
        except Exception as exc:            # a failed refinement must not lose
            ba_log.append({"stage": tag, "error": str(exc)})   # the reconstruction
            return None
        if not res.stats.get("accepted"):
            ba_log.append({"stage": tag, **res.to_dict()})
            return res
        for i, f in enumerate(cam_frames):
            R, _ = cv2.Rodrigues(res.rvecs[i])
            cams[f] = Camera(f, R, res.tvecs[i])
        cam_list = list(cams.values())
        idx = {c.frame_index: k for k, c in enumerate(cam_list)}
        for i, root in enumerate(roots):
            X = res.points[i]
            obs = [(idx[f], kpts[f][a].pt)
                   for f, a in tracks[root].items() if f in cams]
            st = _point_stats(X, obs, cam_list, K)
            if st is None:
                point_of_track.pop(root, None)
                continue
            reproj, ang = st
            if reproj > max_reproj or ang < min_tri_angle:
                point_of_track.pop(root, None)
                continue
            point_of_track[root] = (X, reproj, ang, len(obs))
        if focal:
            K = res.K
        ba_log.append({"stage": tag, **res.to_dict()})
        return res

    _retriangulate()
    # An early solve on the seed pair keeps the two-view initialisation from
    # biasing every camera registered against it.
    _run_ba("init", max_nfev=60, focal=False, distortion=False)

    retri_every = 4  # amortise the O(tracks) retriangulation pass
    n_since_ba = 0

    def _support(f):
        """2D-3D correspondences frame ``f`` currently has against the model.

        Walks only the tracks frame ``f`` actually observes, via ``obs_index``,
        instead of every point in the reconstruction.
        """
        obj_pts, img_pts = [], []
        for root in obs_index.get(f, ()):
            entry = point_of_track.get(root)
            if entry is None:
                continue                      # dropped by a later filter pass
            a = tracks[root].get(f)
            if a is not None:
                obj_pts.append(entry[0])
                img_pts.append(kpts[f][a].pt)
        return obj_pts, img_pts

    pending = set(range(n)) - {i0, j0}
    failed_once: set = set()          # tried and failed; retried as the model grows
    step = 0
    attempts = 0
    total = len(pending)
    while pending:
        # Next best view: the unregistered frame with the most 2D-3D support.
        # Registering the best-supported frame first means every later frame is
        # solved against a larger, better-constrained model -- and a frame that
        # cannot be solved yet simply waits instead of being consumed.
        scored = []
        for f in pending:
            obj_pts, img_pts = _support(f)
            if len(obj_pts) >= 6:
                scored.append((len(obj_pts), f, obj_pts, img_pts))
        if not scored:
            break                      # no frontier left: nothing can be added
        # Sort on (support, frame index) so an equal-support tie resolves the
        # same way every run rather than by set iteration order.
        scored.sort(key=lambda t: (-t[0], t[1]))
        _, f, obj_pts, img_pts = scored[0]

        obj = np.asarray(obj_pts, float)
        img = np.asarray(img_pts, float)
        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj, img, K, None, reprojectionError=4.0,
            confidence=0.999, iterationsCount=200, flags=cv2.SOLVEPNP_EPNP)
        registered = bool(ok and inliers is not None and len(inliers) >= 6)
        if registered:
            R, _ = cv2.Rodrigues(rvec)
            cams[f] = Camera(f, R, tvec.ravel())
            pending.discard(f)
            failed_once.discard(f)
            n_since_ba += 1
            step += 1
            if step % retri_every == 0:
                _retriangulate()
            # Intermediate solves are capped: their job is to stop drift
            # accumulating, not to reach the optimum, which the final global
            # solve does once over the complete problem.
            if do_ba and n_since_ba >= ba_every:
                _retriangulate()
                _run_ba(f"incremental@{step}", max_nfev=40,
                        focal=False, distortion=False)
                n_since_ba = 0
        else:
            # Do not discard it permanently: more points may appear later and
            # make it solvable.  Park it, and retry once the model has grown.
            if f in failed_once:
                pending.discard(f)     # already had a second chance
            else:
                failed_once.add(f)
                pending.discard(f)
                retry_later.add(f)
        if not pending and retry_later:
            _retriangulate()
            pending, retry_later = retry_later, set()
        # Count attempts, not just successes: a capture where several frames
        # cannot be registered must still show the stage completing.
        attempts += 1
        progress("registering", min(1.0, attempts / max(1, total)))
    _retriangulate()  # final pass over all registered cameras
    # Final global solve over every camera and point, where intrinsic refinement
    # (if requested) has the most constraints available to stay identifiable.
    ba_final = _run_ba("final", max_nfev=200, focal=refine_focal,
                       distortion=refine_distortion)

    # 6a) Propagated per-point uncertainty, from the same observations and the
    #     final camera geometry.  Computed before assembly so every shipped point
    #     carries a covariance derived from the poses it was actually solved with.
    cov_of_root: dict = {}
    _sig_px = None
    try:
        from . import uncertainty as _unc
        prob = _ba_problem(tracks, point_of_track, cams, kpts)
        if prob is not None:
            _cf, _roots, _rv, _tv, _pts, _ci, _pi, _uv = prob
            # Estimate the image-measurement noise from the residuals this
            # reconstruction actually produced, rather than assuming a fixed
            # value.  Assuming 0.5 px on imagery whose residuals are 0.05 px
            # inflates every interval ~10x and makes the requirement gate
            # useless; assuming it on noisy real imagery would understate them.
            _res = bundle.reprojection_errors(_rv, _tv, _pts, _ci, _pi, _uv, K)
            _res = _res[np.isfinite(_res)]
            if len(_res) >= 20:
                # Robust scale (normalised MAD): RANSAC and the reprojection
                # filter leave a heavy tail that would inflate a plain RMS.
                _mad = float(np.median(np.abs(_res - np.median(_res))))
                _sig_px = max(1.4826 * _mad, 0.05)
            else:
                _sig_px = _unc.DEFAULT_SIGMA_PX
            pu = _unc.point_covariances(_pts, _ci, _pi, _uv, _rv, _tv, K,
                                        sigma_px=_sig_px)
            for k, root in enumerate(_roots):
                cov_of_root[root] = (pu.cov[k], pu.sigma[k], pu.sigma_major[k],
                                     bool(pu.observable[k]))
    except Exception as exc:          # uncertainty is additive, never fatal
        cov_of_root = {}
        ba_log.append({"stage": "uncertainty", "error": str(exc)})

    # 6) Assemble point cloud with colour + confidence
    progress("fusion", 0.0)
    pts, cols, conf, oc, rep, ang = [], [], [], [], [], []
    pcov, psig, psig_major, pobs = [], [], [], []
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
        cv_, sg_, sgm_, ob_ = cov_of_root.get(
            root, (np.full((3, 3), np.nan), np.inf, np.inf, False))
        pcov.append(cv_)
        psig.append(sg_)
        psig_major.append(sgm_)
        pobs.append(ob_)

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
        point_cov=np.array(pcov) if pcov else np.zeros((0, 3, 3)),
        point_sigma=np.array(psig) if psig else np.zeros(0),
        point_sigma_major=np.array(psig_major) if psig_major else np.zeros(0),
        point_observable=np.array(pobs, bool) if pobs else np.zeros(0, bool),
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
        "matcher": backend_info,
        "heading_normalised": bool(orientations is not None),
        "rotation_rescued_pairs": n_rot_rescued,
        "canonical_orientation": canonical_orientation,
        "orientation": orient_diag,
        "init_pair": {"frames": [int(i0), int(j0)], **(init_info or {})},
        "uncertainty": {
            "sigma_px_estimated": float(_sig_px) if cov_of_root else None,
            "n_with_covariance": len(cov_of_root),
            "n_observable": int(np.sum(pobs)) if pobs else 0,
            "median_sigma_recon_frame": (float(np.median(np.asarray(psig)[np.isfinite(psig)]))
                                         if psig and np.any(np.isfinite(psig)) else None),
        },
        "bundle_adjustment": {
            "enabled": bool(do_ba),
            "n_solves": len(ba_log),
            "final": ba_final.to_dict() if ba_final is not None else None,
            "history": ba_log,
        },
    }
    progress("fusion", 1.0)
    return result
