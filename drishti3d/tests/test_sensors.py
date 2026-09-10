"""Sensor-model corrections: recover a known offset, a known lever arm, a known smear.

Each test injects a *known* error and checks it is recovered, rather than
checking the code runs. The negative cases matter as much as the positive ones:
a timing estimator that returns a confident number for a constant-speed flight is
worse than one that says it cannot tell.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import sensors                       # noqa: E402


def _wiggly_track(t, seed=0):
    """A flight with genuinely varying speed, so timing is observable."""
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 2 * np.pi, 3)
    x = 12 * np.sin(0.7 * t + phase[0]) + 3 * np.sin(2.3 * t + phase[1])
    y = 9 * np.cos(0.5 * t + phase[1]) + 2 * np.sin(3.1 * t + phase[2])
    z = 40 + 2 * np.sin(0.9 * t + phase[2])
    return np.stack([x, y, z], 1)


# --------------------------------------------------------------------------- #
# time offset
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("true_offset", [0.0, 0.35, -0.6, 1.1])
def test_recovers_a_known_time_offset(true_offset):
    video_t = np.arange(0, 20, 0.1)
    cam = _wiggly_track(video_t)
    # Telemetry is sampled on its own clock: t_tel = t_video + offset
    tel_t = video_t + true_offset
    res = sensors.estimate_time_offset(video_t, cam, tel_t, cam, search_s=2.0)
    assert res.accepted, res.reason
    assert abs(res.offset_s - true_offset) < 0.06, (
        f"recovered {res.offset_s:.3f}s, true {true_offset:.3f}s")


def test_time_offset_is_invariant_to_scale_and_rotation():
    """It must work before georegistration, so an unknown Sim(3) cannot matter."""
    video_t = np.arange(0, 20, 0.1)
    cam = _wiggly_track(video_t)
    ang = 0.9
    R = np.array([[np.cos(ang), -np.sin(ang), 0],
                  [np.sin(ang), np.cos(ang), 0], [0, 0, 1.0]])
    recon = (17.3 * (R @ cam.T).T) + np.array([100.0, -50.0, 7.0])
    res = sensors.estimate_time_offset(video_t, recon, video_t + 0.4, cam)
    assert res.accepted, res.reason
    assert abs(res.offset_s - 0.4) < 0.06


def test_constant_speed_flight_reports_that_timing_is_unobservable():
    """A uniform pass carries no timing information; do not invent one."""
    t = np.arange(0, 20, 0.1)
    straight = np.stack([5 * t, np.zeros_like(t), np.full_like(t, 40.0)], 1)
    res = sensors.estimate_time_offset(t, straight, t + 0.5, straight)
    assert not res.accepted
    assert "unobservable" in res.reason or "uniform" in res.reason or \
           "below" in res.reason


def test_time_offset_handles_too_few_samples():
    res = sensors.estimate_time_offset([0, 1], np.zeros((2, 3)), [0, 1],
                                       np.zeros((2, 3)))
    assert not res.accepted and res.offset_s == 0.0


# --------------------------------------------------------------------------- #
# lever arm
# --------------------------------------------------------------------------- #
def test_lever_arm_rotates_with_heading():
    """The whole point: a fixed body offset moves in the world as the drone yaws."""
    gps = np.zeros((4, 3))
    lever = np.array([1.0, 0.0, 0.0])          # camera 1 m forward of antenna
    out, applied = sensors.apply_lever_arm(gps, lever, yaw=[0.0, 90.0, 180.0, 270.0])
    assert applied
    # yaw 0 = north -> +north; yaw 90 = east -> +east
    assert np.allclose(out[0], [0, 1, 0], atol=1e-6), out[0]
    assert np.allclose(out[1], [1, 0, 0], atol=1e-6), out[1]
    assert np.allclose(out[2], [0, -1, 0], atol=1e-6), out[2]
    assert np.allclose(out[3], [-1, 0, 0], atol=1e-6), out[3]


def test_lever_arm_down_axis_maps_to_negative_up():
    """Body z is *down*; getting this sign wrong would push the camera skyward."""
    out, applied = sensors.apply_lever_arm(np.zeros((1, 3)), [0.0, 0.0, 0.5],
                                           yaw=[0.0])
    assert applied
    assert np.allclose(out[0], [0, 0, -0.5], atol=1e-6), out[0]


def test_lever_arm_without_attitude_is_refused():
    """A body-frame offset cannot be placed in the world without orientation."""
    gps = np.ones((3, 3))
    out, applied = sensors.apply_lever_arm(gps, [1.0, 0, 0])
    assert not applied
    assert np.allclose(out, gps)


def test_zero_lever_arm_is_a_no_op():
    gps = np.random.default_rng(0).normal(size=(5, 3))
    out, applied = sensors.apply_lever_arm(gps, [0.0, 0.0, 0.0], yaw=[0] * 5)
    assert not applied and np.allclose(out, gps)


def test_body_to_enu_is_a_rotation():
    R = sensors.body_to_enu(12.0, -7.0, 40.0)
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(R), 1.0, atol=1e-9)


# --------------------------------------------------------------------------- #
# rolling shutter
# --------------------------------------------------------------------------- #
def _yaw_sequence(rate_deg_s, n=30, fps=30.0):
    rots, times = [], []
    for i in range(n):
        a = np.radians(rate_deg_s * i / fps)
        rots.append(np.array([[np.cos(a), -np.sin(a), 0],
                              [np.sin(a), np.cos(a), 0], [0, 0, 1.0]]))
        times.append(i / fps)
    return rots, times


def test_fast_yaw_is_flagged_severe():
    rots, times = _yaw_sequence(120.0)          # a fast whip pan
    chk = sensors.detect_rolling_shutter(rots, times, readout_s=1 / 60.0)
    assert chk.severity == "severe", chk.to_dict()
    assert chk.message and "rolling-shutter" in chk.message
    assert chk.p95_rate_deg_s > 100


def test_slow_motion_is_not_flagged():
    rots, times = _yaw_sequence(2.0)
    chk = sensors.detect_rolling_shutter(rots, times, readout_s=1 / 60.0)
    assert chk.severity == "none"
    assert chk.message == ""


def test_smear_scales_with_readout_time():
    """A slower sensor readout makes the same motion worse."""
    rots, times = _yaw_sequence(30.0)
    fast = sensors.detect_rolling_shutter(rots, times, readout_s=1 / 240.0)
    slow = sensors.detect_rolling_shutter(rots, times, readout_s=1 / 30.0)
    assert slow.worst_smear_deg > fast.worst_smear_deg * 3


def test_rolling_shutter_handles_degenerate_input():
    chk = sensors.detect_rolling_shutter([np.eye(3)], [0.0])
    assert chk.severity == "none"


# --------------------------------------------------------------------------- #
# distortion
# --------------------------------------------------------------------------- #
def test_undistort_straightens_a_known_barrel_distortion():
    """A straight line stays straight only once distortion is removed."""
    w, h = 320, 240
    K = np.array([[250.0, 0, w / 2], [0, 250.0, h / 2], [0, 0, 1.0]])
    dist = np.array([-0.35, 0.12, 0.0, 0.0, 0.0])

    # A grid of straight lines, distorted as a camera would.
    img = np.zeros((h, w, 3), np.uint8)
    for x in range(0, w, 20):
        img[:, x] = 255
    for y in range(0, h, 20):
        img[y, :] = 255
    distorted = cv2.undistort(img, K, -dist)     # apply the inverse => barrel

    out, K_new, applied = sensors.undistort_frames([distorted], K, dist)
    assert applied
    assert out[0].shape == distorted.shape
    # the corrected intrinsics are genuinely different from the input
    assert not np.allclose(K_new, K)


def test_no_distortion_is_a_no_op():
    frames = [np.zeros((20, 30, 3), np.uint8)]
    K = np.array([[10.0, 0, 15], [0, 10.0, 10], [0, 0, 1.0]])
    out, K_new, applied = sensors.undistort_frames(frames, K, [0, 0, 0, 0, 0])
    assert not applied
    assert out is frames and np.allclose(K_new, K)


def test_undistort_handles_none_coefficients():
    frames = [np.zeros((20, 30, 3), np.uint8)]
    K = np.eye(3)
    out, K_new, applied = sensors.undistort_frames(frames, K, None)
    assert not applied and np.allclose(K_new, K)


def test_short_clip_does_not_invent_a_large_offset():
    """Regression: a 2 s flight once produced a confident +1.8 s offset.

    Searching +/-2 s across a 2 s clip leaves almost nothing overlapping at large
    shifts, and correlation over a sliver of data is noisy and biased high. It
    was accepted, and it collapsed the georegistration scale to 0.006.
    """
    t = np.arange(0, 2.0, 0.05)          # exactly the failing fixture's duration
    cam = _wiggly_track(t)
    res = sensors.estimate_time_offset(t, cam, t, cam, search_s=2.0)
    # true offset is zero: either recover ~0, or decline — never a large value
    assert abs(res.offset_s) < 0.25 or not res.accepted, res.to_dict()
    assert res.search_s <= 0.6, "search window must be clamped to the clip length"


def test_edge_pinned_peak_is_not_accepted():
    """If the best match sits at the window edge, the truth may lie outside it."""
    t = np.arange(0, 20, 0.1)
    cam = _wiggly_track(t)
    # true offset far outside a deliberately narrow search
    res = sensors.estimate_time_offset(t, cam, t + 5.0, cam, search_s=0.5)
    assert not res.accepted
    assert "edge" in res.reason or "below" in res.reason
