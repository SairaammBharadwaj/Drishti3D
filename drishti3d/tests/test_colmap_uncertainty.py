"""Per-point uncertainty on the COLMAP path (DEC-011).

COLMAP returns geometry but no covariance. Without this pass every endpoint on
a COLMAP reconstruction snapped to an infinite sigma and `questions.evaluate`
refused the measurement as `not_observable` -- so the faster, more accurate
engine was the one that could not be measured on.

These tests exercise the helper directly with synthetic geometry, so they run
whether or not PyCOLMAP is installed.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon.colmap_adapter import _point_uncertainty
from drishti_recon.sfm import Camera


def _K(f=900.0, w=1280, h=720):
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]], float)


def _cameras(centres, target=(0.0, 0.0, 0.0), start_frame=0, step=1):
    """Cameras at given centres, all looking at ``target``."""
    cams, t = [], np.asarray(target, float)
    for k, C in enumerate(centres):
        C = np.asarray(C, float)
        fwd = t - C
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        R = np.stack([right, down, fwd])
        cams.append(Camera(start_frame + k * step, R, -R @ C))
    return cams


def _observe(cams, points, K):
    """Project every point into every camera it falls in front of."""
    obs_point, obs_frame, obs_uv = [], [], []
    for c in cams:
        for i, p in enumerate(points):
            v = np.asarray(c.R, float) @ np.asarray(p, float) + np.asarray(c.t,
                                                                           float)
            if v[2] <= 1e-6:
                continue
            obs_point.append(i)
            obs_frame.append(int(c.frame_index))
            obs_uv.append([K[0, 0] * v[0] / v[2] + K[0, 2],
                           K[1, 1] * v[1] / v[2] + K[1, 2]])
    return obs_point, obs_frame, np.asarray(obs_uv, np.float32)


def _arc(n=5, radius=20.0, spread=1.2, height=5.0):
    return [[radius * np.sin(a), -radius * np.cos(a), height]
            for a in np.linspace(-spread / 2, spread / 2, n)]


def test_a_well_observed_point_gets_a_finite_sigma():
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.5, 0.2]])
    cams = _cameras(_arc(5))
    op, of, uv = _observe(cams, pts, K)
    pu, sigma_px, err = _point_uncertainty(pts, cams, K, op, of, uv)
    assert err is None
    assert pu is not None
    assert np.all(np.isfinite(pu.sigma))
    assert np.all(pu.sigma > 0)
    assert np.all(pu.observable)
    assert sigma_px is not None and sigma_px > 0


def test_sigma_major_is_the_worst_axis_not_the_best():
    """Measurements use the worst-constrained direction, so it must be larger."""
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0]])
    cams = _cameras(_arc(5))
    pu, _, _ = _point_uncertainty(pts, cams, K, *_observe(cams, pts, K))
    assert pu.sigma_major[0] >= pu.sigma[0]


def test_a_narrow_arc_is_more_uncertain_than_a_wide_one():
    """Parallax, not view count: both have five cameras."""
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0]])
    wide = _cameras(_arc(5, spread=1.2))
    narrow = _cameras(_arc(5, spread=0.02))
    pu_w, _, _ = _point_uncertainty(pts, wide, K, *_observe(wide, pts, K))
    pu_n, _, _ = _point_uncertainty(pts, narrow, K, *_observe(narrow, pts, K))
    assert pu_n.sigma_major[0] > pu_w.sigma_major[0] * 5


def test_a_point_with_one_observation_is_not_observable():
    """One ray cannot fix a position; the answer is infinity, not a guess.

    The realistic shape: a reconstruction where most points are well observed
    and a few are seen once. The well-observed ones must not be dragged down,
    and the single-observation one must not be given a number.
    """
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0], [0.5, 0.3, 0.1]])
    cams = _cameras(_arc(4))
    op, of, uv = _observe(cams, pts, K)
    # Drop every observation of point 1 but the first.
    keep = [i for i, pi in enumerate(op)
            if pi == 0 or of[i] == cams[0].frame_index]
    op = [op[i] for i in keep]
    of = [of[i] for i in keep]
    uv = uv[keep]
    assert sum(1 for x in op if x == 1) == 1

    pu, _, err = _point_uncertainty(pts, cams, K, op, of, uv)
    assert err is None and pu is not None
    assert np.isfinite(pu.sigma[0]) and pu.observable[0]
    assert not np.isfinite(pu.sigma[1])
    assert not pu.observable[1]


def test_observations_are_matched_to_cameras_by_frame_index():
    """Camera frame indices are not row indices, and confusing them is silent.

    The cameras here carry frame indices 0, 7, 14, 21, 28 while occupying rows
    0..4. Treating an observation's frame index as a row would select the wrong
    pose -- or run off the end of the array.
    """
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0]])
    cams = _cameras(_arc(5), start_frame=0, step=7)
    assert [c.frame_index for c in cams] == [0, 7, 14, 21, 28]
    pu, _, _ = _point_uncertainty(pts, cams, K, *_observe(cams, pts, K))
    assert pu is not None and np.isfinite(pu.sigma[0])

    # Compare against the same geometry numbered 0..4: identical uncertainty.
    cams2 = _cameras(_arc(5), start_frame=0, step=1)
    pu2, _, _ = _point_uncertainty(pts, cams2, K, *_observe(cams2, pts, K))
    assert pu.sigma_major[0] == pytest.approx(pu2.sigma_major[0], rel=1e-9)


def test_observations_of_unregistered_frames_are_dropped_not_misindexed():
    K = _K()
    pts = np.array([[0.0, 0.0, 0.0]])
    cams = _cameras(_arc(5))
    op, of, uv = _observe(cams, pts, K)
    # Append an observation from a frame that has no camera.
    op = list(op) + [0]
    of = list(of) + [999]
    uv = np.vstack([uv, np.float32([[10.0, 10.0]])])
    pu, _, _ = _point_uncertainty(pts, cams, K, op, of, uv)
    assert pu is not None and np.isfinite(pu.sigma[0])


def test_empty_inputs_report_why_rather_than_raising_or_going_silent():
    """A bare None hid a NameError in this very function until it said why."""
    K = _K()
    pu, sig, err = _point_uncertainty(np.zeros((0, 3)), [], K, [], [], [])
    assert pu is None and sig is None and err
    cams = _cameras(_arc(3))
    pu, sig, err = _point_uncertainty(np.zeros((0, 3)), cams, K, [], [], [])
    assert pu is None and err


def test_sigma_px_is_estimated_from_this_reconstruction_not_assumed():
    """A fixed 0.5 px would inflate a clean reconstruction's intervals ~10x."""
    K = _K()
    rng = np.random.default_rng(0)
    pts = rng.uniform(-3, 3, (40, 3))
    cams = _cameras(_arc(6))
    op, of, uv = _observe(cams, pts, K)
    _pu, clean, _ = _point_uncertainty(pts, cams, K, op, of, uv)
    assert clean == pytest.approx(0.05), "exact projections floor at 0.05 px"

    noisy_uv = uv + rng.normal(0, 2.0, uv.shape).astype(np.float32)
    _pu2, noisy, _ = _point_uncertainty(pts, cams, K, op, of, noisy_uv)
    assert noisy > clean * 5
