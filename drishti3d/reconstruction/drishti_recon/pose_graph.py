"""Pose graph optimization for single-pass trajectories.

Intelligence Edition §7: long linear drone flights accumulate small pose errors
that a free reconstruction cannot correct — on the AGZ surveyed segment the
residual is a low-frequency bow (26.7 m at the ends, 3.2 m mid-sequence) with
sound local geometry. This module fuses relative-pose constraints (sequential
plus skip pairs) with absolute position priors (GPS) in one robust non-linear
solve, which is the mechanism that removes such a bow.

Implemented on scipy rather than GTSAM/g2o — see decision D-030: GTSAM pins
numpy<2 (our benchmarked base is 2.5.2) and g2o-python does not build here.
Graphs in this project are small (<= a few hundred nodes), well inside scipy's
sparse trust-region solver's comfort zone.

Conventions: a node pose is world-from-camera (R_wc, c) with c the camera
centre in world coordinates. A relative constraint measures, for edge (i, j),
the pose of j expressed in i's camera frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial.transform import Rotation


@dataclass
class Edge:
    i: int
    j: int
    R_ij: np.ndarray          # rotation of j in i's camera frame (3,3)
    t_ij: np.ndarray          # position of j's centre in i's camera frame (3,)
    weight: float = 1.0       # relative confidence of this edge


@dataclass
class PoseGraph:
    n: int                                    # number of nodes
    edges: list = field(default_factory=list)
    # absolute position priors: node index -> (xyz, sigma_m)
    priors: dict = field(default_factory=dict)

    def add_edge(self, i, j, R_ij, t_ij, weight=1.0):
        self.edges.append(Edge(int(i), int(j),
                               np.asarray(R_ij, float),
                               np.asarray(t_ij, float), float(weight)))

    def add_prior(self, i, xyz, sigma_m):
        self.priors[int(i)] = (np.asarray(xyz, float), float(sigma_m))


def _pack(Rs, cs):
    rv = Rotation.from_matrix(np.asarray(Rs)).as_rotvec()
    return np.concatenate([rv.ravel(), np.asarray(cs, float).ravel()])


def _unpack(x, n):
    rv = x[: 3 * n].reshape(n, 3)
    cs = x[3 * n:].reshape(n, 3)
    return Rotation.from_rotvec(rv).as_matrix(), cs


def _rotation_average(edges, Rs0, n, *, rot_sigma_rad, irls_iters=3,
                      max_nfev=100):
    """Stage A: solve rotations alone.

    The rotation-only graph is small (3n params) and nearly linear in the
    rotation vectors for the error magnitudes seen here, so it converges in a
    handful of trust-region steps where the joint problem crawls. IRLS with a
    Cauchy weight absorbs gross outlier edges.
    """
    rv0 = Rotation.from_matrix(np.asarray(Rs0)).as_rotvec().ravel()
    R_init = np.asarray(Rs0)
    r0 = np.array([np.linalg.norm(Rotation.from_matrix(
        e.R_ij.T @ (R_init[e.i].T @ R_init[e.j])).as_rotvec())
        for e in edges]) / rot_sigma_rad
    c0_ = 3.0 * max(np.median(r0), 1e-6)
    w_edge = 1.0 / (1.0 + (r0 / c0_) ** 2)

    sp = lil_matrix((len(edges) * 3, 3 * n), dtype=np.uint8)
    for k, e in enumerate(edges):
        sp[3 * k:3 * k + 3, 3 * e.i:3 * e.i + 3] = 1
        sp[3 * k:3 * k + 3, 3 * e.j:3 * e.j + 3] = 1
    sp = sp.tocsr()

    def residuals(x):
        R = Rotation.from_rotvec(x.reshape(n, 3)).as_matrix()
        out = np.empty(len(edges) * 3)
        for k, e in enumerate(edges):
            dr = Rotation.from_matrix(e.R_ij.T @ (R[e.i].T @ R[e.j])).as_rotvec()
            out[3 * k:3 * k + 3] = np.sqrt(e.weight * w_edge[k]) * dr / rot_sigma_rad
        return out

    x = rv0
    for _ in range(irls_iters):
        res = least_squares(residuals, x, jac_sparsity=sp, max_nfev=max_nfev,
                            x_scale="jac")
        x = res.x
        r = residuals(x).reshape(-1, 3)
        mag = np.linalg.norm(r, axis=1)
        c = 3.0 * max(np.median(mag), 1e-6)
        w_edge = 1.0 / (1.0 + (mag / c) ** 2)          # Cauchy weight
    return Rotation.from_rotvec(x.reshape(n, 3)).as_matrix()


def _linear_centres(edges, priors, Rs, cs0, n, *, trans_sigma_m, irls_iters=3):
    """Stage B: with rotations fixed, centres are exactly linear.

    Each edge row is Ri^T (c_j - c_i) = t_ij and each prior row is c_i = xyz,
    so the centres come from one sparse linear solve — no iteration budget, no
    local minima, no valley to crawl. IRLS reweights outlier edges and GPS
    spikes.
    """
    from scipy.sparse import lil_matrix as _lil
    from scipy.sparse.linalg import lsqr

    prior_items = sorted(priors.items())
    m = len(edges) * 3 + len(prior_items) * 3
    # Pre-weight from residuals at the initialization instead of starting all
    # weights at 1: a gross outlier edge (25 m on a 0.1 m sigma) otherwise
    # dominates the first linear solve and ruptures the trajectory locally
    # before IRLS can react (measured: max error 14.9 m with, 2.1 m without).
    cs_init = np.asarray(cs0, float)
    re0 = np.array([np.linalg.norm(Rs[e.i].T @ (cs_init[e.j] - cs_init[e.i])
                                   - e.t_ij) for e in edges]) / trans_sigma_m
    c0_ = 3.0 * max(np.median(re0), 1e-6)
    w_edge = 1.0 / (1.0 + (re0 / c0_) ** 2)
    w_pri = np.ones(len(prior_items))

    for _ in range(irls_iters):
        A = _lil((m, 3 * n)); b = np.zeros(m); k = 0
        for kk, e in enumerate(edges):
            w = np.sqrt(e.weight * w_edge[kk]) / trans_sigma_m
            RiT = Rs[e.i].T
            A[k:k + 3, 3 * e.j:3 * e.j + 3] = w * RiT
            A[k:k + 3, 3 * e.i:3 * e.i + 3] = -w * RiT
            b[k:k + 3] = w * e.t_ij
            k += 3
        for kk, (i, (xyz, sig)) in enumerate(prior_items):
            w = np.sqrt(w_pri[kk]) / sig
            A[k:k + 3, 3 * i:3 * i + 3] = w * np.eye(3)
            b[k:k + 3] = w * xyz
            k += 3
        sol = lsqr(A.tocsr(), b, x0=np.asarray(cs0, float).ravel(),
                   atol=1e-10, btol=1e-10, iter_lim=8000)
        cs = sol[0].reshape(n, 3)
        # reweight
        re = np.array([np.linalg.norm(Rs[e.i].T @ (cs[e.j] - cs[e.i]) - e.t_ij)
                       for e in edges]) / trans_sigma_m
        ce = 3.0 * max(np.median(re), 1e-6)
        w_edge = 1.0 / (1.0 + (re / ce) ** 2)
        rp = np.array([np.linalg.norm(cs[i] - xyz) / sig
                       for i, (xyz, sig) in prior_items])
        cp = 3.0 * max(np.median(rp), 1e-6)
        w_pri = 1.0 / (1.0 + (rp / cp) ** 2)
        cs0 = cs
    return cs


def optimize(graph: PoseGraph, Rs0, cs0, *,
             rot_sigma_rad: float = 0.003,
             trans_sigma_m: float = 0.10,
             joint_polish: bool = False,
             loss: str = "cauchy",
             f_scale: float = 10.0,
             max_nfev: int = 60):
    """Optimize node poses. Returns (Rs, cs, info).

    Decomposed as global SfM does: rotation averaging, then a linear centre
    solve, then an optional joint polish. A monolithic 6n-parameter robust
    solve was measured to stall in a narrow valley on exactly the bow scenario
    this module exists to fix (200 iterations, no visible progress); the
    decomposition removes the valley because each stage is small or exactly
    linear.

    ``rot_sigma_rad``/``trans_sigma_m`` must reflect the *actual* noise of the
    relative-pose edges, not a comfortable margin. Loose sigmas let the graph
    bend toward individual GPS samples and fit their noise; stiff edges force
    averaging over many priors — that averaging is the mechanism by which PGO
    beats raw GPS.

    Gauge: with >= 2 position priors the graph is anchored; otherwise node 0
    is clamped by a tight internal prior.
    """
    n = graph.n
    Rs0 = np.asarray(Rs0, float); cs0 = np.asarray(cs0, float)
    edges = graph.edges
    priors = dict(graph.priors)
    anchored = len(priors) >= 2
    if not anchored:
        priors.setdefault(0, (cs0[0].copy(), 1e-4))

    Rs = _rotation_average(edges, Rs0, n, rot_sigma_rad=rot_sigma_rad)
    cs = _linear_centres(edges, priors, Rs, cs0, n, trans_sigma_m=trans_sigma_m)

    # Gauge correction. Rotation averaging determines orientations only up to
    # one global rotation (measured: an identical 6.7 deg offset at every node
    # — half the integrated bend). With rotations fixed, the stiff centre
    # solve follows that tilted direction and priors can translate but not
    # rotate it back. So: align solved centres to the priors, rotate the whole
    # pose set, re-solve centres, iterate to convergence.
    #
    # The alignment estimates ONLY the rotation components the priors actually
    # constrain. A plain Kabsch is wrong twice over here: on a collinear prior
    # set (a single pass!) its completion is arbitrary, and even at singular
    # value ratios like 0.27 its second axis is fitted to prior NOISE — the
    # roll about the flight axis is position-invariant for a line, and Kabsch
    # returned a 164 deg roll that mirrored the small cross-track structure.
    # Axis 1 (principal) is aligned always; axis 2 only when its extent
    # clearly exceeds the prior noise floor.
    prior_nodes = sorted(priors.keys())
    if len(prior_nodes) >= 3:
        P = np.array([priors[i][0] for i in prior_nodes])
        w = np.array([1.0 / priors[i][1] ** 2 for i in prior_nodes])

        def _minimal_rotation(u, v):
            u = u / (np.linalg.norm(u) + 1e-12)
            v = v / (np.linalg.norm(v) + 1e-12)
            ax = np.cross(u, v); s_ = np.linalg.norm(ax); c_ = float(u @ v)
            if s_ < 1e-12:
                return np.eye(3)
            return Rotation.from_rotvec(ax / s_ * np.arctan2(s_, c_)).as_matrix()

        # Noise floor of the weighted prior spread: each weighted row carries
        # unit-variance noise, so a spurious axis contributes ~sqrt(N).
        noise_sv = np.sqrt(len(prior_nodes))

        for _ in range(4):
            C = cs[prior_nodes]
            mc = np.average(C, 0, w); mp = np.average(P, 0, w)
            Xc = (C - mc) * np.sqrt(w[:, None]); Xp = (P - mp) * np.sqrt(w[:, None])
            Up, svp, Vtp = np.linalg.svd(Xp, full_matrices=False)
            Uc, svc, Vtc = np.linalg.svd(Xc, full_matrices=False)
            if svp[0] < 1e-9:
                break
            # axis 1: sign from first-to-last so a pass cannot flip end-to-end
            a1p = Vtp[0] * np.sign(Vtp[0] @ (P[-1] - P[0]))
            a1c = Vtc[0] * np.sign(Vtc[0] @ (C[-1] - C[0]))
            G = _minimal_rotation(a1c, a1p)
            if svp[1] > 3.0 * noise_sv and svc[1] > 3.0 * noise_sv:
                # real second axis on both sides: correct roll about axis 1
                a2c = G @ (Vtc[1] * np.sign(Vtc[1] @ Vtp[1]))
                a2p = Vtp[1]
                # project both onto the plane normal to a1p, rotate about a1p
                pr = lambda v: v - (v @ a1p) * a1p
                G = _minimal_rotation(pr(a2c), pr(a2p)) @ G
            ang = np.linalg.norm(Rotation.from_matrix(G).as_rotvec())
            if ang < 1e-4:
                break
            # Accept/reject on the objective: the prior axis is itself noisy,
            # and re-aligning an already well-aligned solution onto it makes
            # things worse (measured on the outlier-edge scenario: 0.5 m
            # degraded to 1.1 m). Keep the rotation only if the weighted
            # prior misfit actually drops after the re-solve.
            def _prior_cost(c):
                return float(sum(np.sum(((c[i] - xyz) / sig) ** 2)
                                 for i, (xyz, sig) in priors.items()))
            cost_before = _prior_cost(cs)
            cs_try = (G @ (cs - mc).T).T + mp
            Rs_try = np.einsum("ab,nbc->nac", G, Rs)
            cs_try = _linear_centres(edges, priors, Rs_try, cs_try, n,
                                     trans_sigma_m=trans_sigma_m)
            if _prior_cost(cs_try) < cost_before:
                cs, Rs = cs_try, Rs_try
            else:
                break

    info = dict(n_edges=len(edges), n_priors=len(priors), anchored=anchored,
                polished=bool(joint_polish))

    if joint_polish:
        prior_items = sorted(priors.items())
        m = len(edges) * 6 + len(prior_items) * 3

        def residuals(x):
            R, c = _unpack(x, n)
            out = np.empty(m); k = 0
            for e in edges:
                R_pred = R[e.i].T @ R[e.j]
                t_pred = R[e.i].T @ (c[e.j] - c[e.i])
                dr = Rotation.from_matrix(e.R_ij.T @ R_pred).as_rotvec()
                w = np.sqrt(e.weight)
                out[k:k + 3] = w * dr / rot_sigma_rad
                out[k + 3:k + 6] = w * (t_pred - e.t_ij) / trans_sigma_m
                k += 6
            for i, (xyz, sig) in prior_items:
                out[k:k + 3] = (c[i] - xyz) / sig
                k += 3
            return out

        sp = lil_matrix((m, 6 * n), dtype=np.uint8); k = 0
        for e in edges:
            for node in (e.i, e.j):
                sp[k:k + 6, 3 * node:3 * node + 3] = 1
                sp[k:k + 6, 3 * n + 3 * node:3 * n + 3 * node + 3] = 1
            k += 6
        for i, _ in prior_items:
            sp[k:k + 3, 3 * n + 3 * i:3 * n + 3 * i + 3] = 1
            k += 3

        res = least_squares(residuals, _pack(Rs, cs), jac_sparsity=sp.tocsr(),
                            loss=loss, f_scale=f_scale, max_nfev=max_nfev,
                            x_scale="jac")
        Rs, cs = _unpack(res.x, n)
        info.update(polish_cost=float(res.cost), polish_nfev=int(res.nfev))

    return Rs, cs, info


def chain_initialization(edges, n, *, c0=None, R0=None):
    """Compose sequential edges into an initial trajectory.

    Uses only (i, i+1) edges; missing links repeat the previous motion. This is
    deliberately crude — it exists to give ``optimize`` a topologically correct
    starting point when no SfM initialization is available.
    """
    seq = {(e.i, e.j): e for e in edges if e.j == e.i + 1}
    Rs = [np.eye(3) if R0 is None else np.asarray(R0, float)]
    cs = [np.zeros(3) if c0 is None else np.asarray(c0, float)]
    last = None
    for i in range(n - 1):
        e = seq.get((i, i + 1), last)
        if e is None:
            Rs.append(Rs[-1].copy()); cs.append(cs[-1].copy()); continue
        last = e
        Rs.append(Rs[-1] @ e.R_ij)
        cs.append(cs[-1] + Rs[-2] @ e.t_ij)
    return np.array(Rs), np.array(cs)
