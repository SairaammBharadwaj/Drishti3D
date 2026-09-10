"""Metrics 4 and 5 (coverage classification, refusal correctness).

Scene with analytic truth: a vertical wall at y=0 spanning x in [0,20],
z in [0,8], viewed by a line of cameras at y=-15 looking at it. Space in
front of the wall (y<0) is observed or empty; space BEHIND the wall is
occluded; space far outside every frustum is unseen.
"""
import numpy as np
import pytest

from drishti_recon import coverage
from eval.intel_metrics import (coverage_classification_accuracy,
                                probe_pairs_from_truth, refusal_correctness,
                                segment_supported)
from drishti_recon.coverage import Coverage


class Cam:
    def __init__(self, R, C):
        self.R = R
        self.center = np.asarray(C, float)
        self.t = -R @ self.center


def look_at(C, target):
    f = np.asarray(target, float) - C
    f = f / np.linalg.norm(f)
    up = np.array([0.0, 0.0, 1.0])
    r = np.cross(f, up); r /= np.linalg.norm(r)
    d = np.cross(f, r)
    return np.stack([r, d, f])


@pytest.fixture(scope="module")
def scene():
    rng = np.random.default_rng(7)
    # dense wall samples = the reconstructed cloud
    x = rng.uniform(0, 20, 6000); z = rng.uniform(0, 8, 6000)
    wall = np.c_[x, np.zeros(6000), z]
    K = np.array([[400.0, 0, 320], [0, 400.0, 240], [0, 0, 1]])
    cams = [Cam(look_at(np.array([cx, -15.0, 4.0]), np.array([cx, 0.0, 4.0])),
                np.array([cx, -15.0, 4.0])) for cx in np.linspace(2, 18, 9)]
    # occlusion_tol at scene scale: the 1.5 m default is a depth-noise
    # allowance for real clouds; here it would grant a 1.5 m verified-empty
    # shell behind every surface.
    grid = coverage.build(wall, cams, K, (640, 480), voxel=1.0,
                          occlusion_tol=0.5)
    return dict(grid=grid, wall=wall, rng=rng)


class TestCoverageClassification:
    def test_three_class_accuracy(self, scene):
        rng = scene["rng"]
        # analytic truth points
        n = 400
        obs = np.c_[rng.uniform(2, 18, n), np.zeros(n), rng.uniform(1, 7, n)]
        # occluded probes must lie INSIDE the coverage grid (cloud bounds +
        # 2 m margin -> y <= 2): beyond it, out-of-grid space is UNSEEN by
        # definition, which is a different (also correct) answer.
        behind = np.c_[rng.uniform(2, 18, n), rng.uniform(0.9, 1.9, n),
                       rng.uniform(1, 7, n)]                    # occluded
        outside = np.c_[rng.uniform(2, 18, n), rng.uniform(-14, -8, n),
                        rng.uniform(30, 40, n)]                 # above frusta
        pts = np.vstack([obs, behind, outside])
        labels = np.array([int(Coverage.OBSERVED)] * n
                          + [int(Coverage.OCCLUDED)] * n
                          + [int(Coverage.UNSEEN)] * n)
        r = coverage_classification_accuracy(scene["grid"], pts, labels)
        assert r["accuracy"] > 0.80
        assert r["per_class"]["OCCLUDED"] > 0.7   # the safety-relevant class
        assert r["per_class"]["OBSERVED"] > 0.7

    def test_confusion_matrix_shape(self, scene):
        r = coverage_classification_accuracy(
            scene["grid"], scene["wall"][:50],
            [int(Coverage.OBSERVED)] * 50)
        assert np.array(r["confusion"]).shape == (3, 3)


class TestRefusalCorrectness:
    def test_rates(self, scene):
        rng = scene["rng"]
        wall = scene["wall"]
        n = 300
        unseen = np.c_[rng.uniform(2, 18, n), rng.uniform(0.9, 5.0, n),
                       rng.uniform(1, 7, n)]        # behind the wall
        pairs, labels = probe_pairs_from_truth(wall, unseen, rng,
                                               n_valid=150, n_invalid=150,
                                               max_span=8.0)
        r = refusal_correctness(scene["grid"], pairs, labels)
        # FALSE ACCEPT is the safety number
        assert r["FAR"] < 0.05
        assert r["TRR"] > 0.95
        # the gate must still be usable
        assert r["TAR"] > 0.60

    def test_segment_through_occlusion_refused(self, scene):
        a = np.array([5.0, 0.0, 4.0])       # on the wall
        b = np.array([5.0, 5.0, 4.0])       # behind it
        assert not segment_supported(scene["grid"], a, b)

    def test_segment_along_wall_accepted(self, scene):
        a = np.array([5.0, 0.0, 4.0])
        b = np.array([12.0, 0.0, 4.0])
        assert segment_supported(scene["grid"], a, b)
