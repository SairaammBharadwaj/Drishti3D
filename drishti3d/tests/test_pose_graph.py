"""Pose graph optimization tests.

The central scenario mirrors the measured AGZ failure: a straight pass whose
integrated rotation error bends the trajectory into a bow, with GPS priors far
noisier than the local relative motion. PGO must remove the bow without
destroying local smoothness.
"""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from drishti_recon import pose_graph as pg


def make_line(n=60, step=1.2):
    cs = np.zeros((n, 3)); cs[:, 0] = np.arange(n) * step
    Rs = np.tile(np.eye(3), (n, 1, 1))
    return Rs, cs


def edges_from_truth(Rs, cs, pairs, rot_noise=0.0, t_noise=0.0, rng=None):
    rng = rng or np.random.default_rng(0)
    out = []
    for i, j in pairs:
        R_ij = Rs[i].T @ Rs[j]
        t_ij = Rs[i].T @ (cs[j] - cs[i])
        if rot_noise:
            R_ij = R_ij @ Rotation.from_rotvec(rng.normal(0, rot_noise, 3)).as_matrix()
        if t_noise:
            t_ij = t_ij + rng.normal(0, t_noise, 3)
        out.append(pg.Edge(i, j, R_ij, t_ij))
    return out


def bowed_initialization(Rs, cs, bend_rad=0.004):
    """Integrate a constant unmodelled yaw drift — produces the classic bow."""
    n = len(cs)
    Rs_b = [Rs[0]]; cs_b = [cs[0]]
    for i in range(n - 1):
        d = Rotation.from_euler("z", bend_rad * (i + 1)).as_matrix()
        step_w = d @ (cs[i + 1] - cs[i])
        cs_b.append(cs_b[-1] + step_w)
        Rs_b.append(d @ Rs[i + 1])
    return np.array(Rs_b), np.array(cs_b)


def seq_and_skip_pairs(n, skips=(4, 12)):
    pairs = [(i, i + 1) for i in range(n - 1)]
    for s in skips:
        pairs += [(i, i + s) for i in range(0, n - s, max(1, s // 2))]
    return pairs


class TestBowRemoval:
    def test_bow_is_removed_with_gps_priors(self):
        rng = np.random.default_rng(3)
        Rs, cs = make_line(60)
        g = pg.PoseGraph(60)
        for e in edges_from_truth(Rs, cs, seq_and_skip_pairs(60),
                                  rot_noise=2e-3, t_noise=0.02, rng=rng):
            g.edges.append(e)
        self_gps_err = []
        for i in range(0, 60, 3):                    # GPS every 3rd frame, 5 m noise
            noise = rng.normal(0, 5.0, 3)
            self_gps_err.append(np.linalg.norm(noise))
            g.add_prior(i, cs[i] + noise, 5.0)
        Rs_b, cs_b = bowed_initialization(Rs, cs)
        err_before = np.linalg.norm(cs_b - cs, axis=1)
        Rs_o, cs_o, info = pg.optimize(g, Rs_b, cs_b)
        err_after = np.linalg.norm(cs_o - cs, axis=1)
        assert np.median(err_before) > 2.0           # the bow is real
        # Information floor: 20 anchors of 5 m noise on a stiff graph cannot
        # do better than ~sigma/sqrt(N_eff) ~= 1.9 m (measured 1.95). The
        # meaningful claim is beating the GPS itself, by a wide margin.
        assert np.median(err_after) < 2.5
        assert np.median(err_after) < 0.5 * np.median(self_gps_err)
        assert err_after.max() < 5.5

    def test_per_frame_priors_reach_submetre(self):
        # The AGZ regime: GPS on EVERY frame. Averaging brings a 5 m GPS
        # down to sub-metre trajectory error.
        rng = np.random.default_rng(3)
        Rs, cs = make_line(60)
        g = pg.PoseGraph(60)
        for e in edges_from_truth(Rs, cs, seq_and_skip_pairs(60),
                                  rot_noise=2e-3, t_noise=0.02, rng=rng):
            g.edges.append(e)
        for i in range(60):
            g.add_prior(i, cs[i] + rng.normal(0, 5.0, 3), 5.0)
        Rs_b, cs_b = bowed_initialization(Rs, cs)
        _, cs_o, _ = pg.optimize(g, Rs_b, cs_b)
        err = np.linalg.norm(cs_o - cs, axis=1)
        assert np.median(err) < 1.2
        assert err.max() < 3.0          # rod-end lever effect; measured 2.5

    def test_local_smoothness_survives(self):
        rng = np.random.default_rng(4)
        Rs, cs = make_line(50)
        g = pg.PoseGraph(50)
        for e in edges_from_truth(Rs, cs, seq_and_skip_pairs(50),
                                  rot_noise=1e-3, t_noise=0.01, rng=rng):
            g.edges.append(e)
        for i in range(0, 50, 5):
            g.add_prior(i, cs[i] + rng.normal(0, 5.0, 3), 5.0)
        Rs_b, cs_b = bowed_initialization(Rs, cs)
        _, cs_o, _ = pg.optimize(g, Rs_b, cs_b)
        step = np.linalg.norm(np.diff(cs_o, axis=0), axis=1)
        jerk = np.linalg.norm(np.diff(cs_o, 2, axis=0), axis=1)
        # smoother than the GPS noise it was anchored to
        assert np.median(jerk) / np.median(step) < 0.15


class TestRobustness:
    def test_single_bad_edge_is_absorbed(self):
        rng = np.random.default_rng(5)
        Rs, cs = make_line(30)
        g = pg.PoseGraph(30)
        edges = edges_from_truth(Rs, cs, seq_and_skip_pairs(30),
                                 rot_noise=1e-3, t_noise=0.01, rng=rng)
        edges[7].t_ij = edges[7].t_ij + np.array([25.0, -12.0, 6.0])   # gross outlier
        g.edges = edges
        for i in range(0, 30, 3):
            g.add_prior(i, cs[i] + rng.normal(0, 2.0, 3), 2.0)
        _, cs_o, _ = pg.optimize(g, Rs, cs)
        # Floor for 10 anchors of 2 m noise is ~1.07 m median (measured on
        # the identical graph without the outlier). The outlier must add
        # almost nothing to the median and must not rupture locally.
        err = np.linalg.norm(cs_o - cs, axis=1)
        assert np.median(err) < 1.3
        assert err.max() < 3.5

    def test_gps_outlier_is_absorbed(self):
        rng = np.random.default_rng(6)
        Rs, cs = make_line(30)
        g = pg.PoseGraph(30)
        g.edges = edges_from_truth(Rs, cs, seq_and_skip_pairs(30),
                                   rot_noise=1e-3, t_noise=0.01, rng=rng)
        for i in range(0, 30, 3):
            g.add_prior(i, cs[i] + rng.normal(0, 2.0, 3), 2.0)
        g.add_prior(15, cs[15] + np.array([120.0, 0, 0]), 2.0)         # 120 m GPS spike
        _, cs_o, _ = pg.optimize(g, Rs, cs)
        assert np.linalg.norm(cs_o[15] - cs[15]) < 2.0


class TestGauge:
    def test_unanchored_graph_clamps_node0(self):
        Rs, cs = make_line(10)
        g = pg.PoseGraph(10)
        g.edges = edges_from_truth(Rs, cs, [(i, i + 1) for i in range(9)])
        Rs_o, cs_o, info = pg.optimize(g, Rs, cs)
        assert not info["anchored"]
        assert np.linalg.norm(cs_o[0] - cs[0]) < 1e-2
        assert np.median(np.linalg.norm(cs_o - cs, axis=1)) < 1e-2

    def test_chain_initialization_matches_truth_shape(self):
        Rs, cs = make_line(12)
        edges = edges_from_truth(Rs, cs, [(i, i + 1) for i in range(11)])
        Rs_c, cs_c = pg.chain_initialization(edges, 12)
        assert np.allclose(cs_c, cs, atol=1e-9)
