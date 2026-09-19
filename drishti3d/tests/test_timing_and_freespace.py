"""Regressions for two silent-wrongness bugs fixed on 2026-09-19.

Both are cases where the system produced a confident answer from evidence it
did not have: a timestamp it never read, and free space it never verified.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon.pipeline import _adopt_pts
from drishti_recon import coverage as cov


# --------------------------------------------------------------------------- #
# 1) container PTS: which side of read() the backend reports
# --------------------------------------------------------------------------- #
def _frames(n, fps=30.0, stride=1):
    """(frame_index, nominal_timestamp, image) tuples as the decode loop builds them.

    ``stride`` is the decimation the pipeline applies: frame indices advance by
    ``stride`` while the sampled frames are consecutive entries in the list, so
    the nominal span the sanity check compares against is ``n*stride/fps``.
    """
    return [(i * stride, i * stride / fps, None) for i in range(n)]


def test_post_read_pts_adopted_when_pre_read_lags():
    """OpenCV 5.0 reports POS_MSEC for the frame just returned.

    Sampling before ``read()`` then yields a series that starts with a duplicate
    and lags the truth by one frame. Previously that series failed the
    strictly-increasing check and the pipeline silently fell back to
    frame_index/fps -- correct for constant-rate video, and a full second per
    frame wrong for the variable-rate missions built from AGZ.
    """
    # A one-second frame spacing: a 30 Hz capture decimated by 30, which is
    # exactly what build_agz_mission.py produces from an AGZ stride subsample.
    truth = [0.0, 1.003, 2.032, 3.002, 3.998]
    pre = [0.0] + truth[:-1]
    frames = _frames(5, fps=30.0, stride=30)
    source, note = _adopt_pts(frames, pre, 30.0, pts_post=truth)
    assert source == "container_pts"
    assert "after decode" in note
    assert [round(f[1], 3) for f in frames] == truth


def test_pre_read_pts_wins_when_both_are_usable():
    """A backend reporting the frame about to be decoded must not be overridden."""
    truth = [0.0, 1.003, 2.032, 3.002, 3.998]
    frames = _frames(5, fps=1.0)
    source, _ = _adopt_pts(frames, truth, 1.0,
                           pts_post=[t + 1.0 for t in truth])
    assert source == "container_pts"
    assert [round(f[1], 3) for f in frames] == truth


def test_all_zero_pts_still_falls_back_to_nominal():
    frames = _frames(5, fps=30.0, stride=30)
    before = [f[1] for f in frames]
    source, _ = _adopt_pts(frames, [0.0] * 5, 30.0, pts_post=[0.0] * 5)
    assert source == "nominal_fps"
    assert [f[1] for f in frames] == before


# --------------------------------------------------------------------------- #
# 2) free space requires a finite depth return
# --------------------------------------------------------------------------- #
class _Cam:
    def __init__(self, centre, R=None):
        self.center = np.asarray(centre, float)
        self.R = np.eye(3) if R is None else np.asarray(R, float)
        self.t = -self.R @ self.center


def _K(f=400.0, w=320, h=240):
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]], float)


def test_no_depth_return_is_not_verified_free_space():
    """A cloud occupying a sliver of the frustum must not clear the whole view.

    The camera looks down +z at a small patch of points. Cells beside that patch
    are crossed by rays that hit nothing at all. Those rays establish nothing;
    before the fix the infinite z-buffer value read as "nothing in the way" and
    the volume was published as EMPTY -- verified free space.
    """
    rng = np.random.default_rng(0)
    # a 1 m x 1 m patch of surface 20 m in front of the camera
    patch = np.column_stack([rng.uniform(-0.5, 0.5, 400),
                             rng.uniform(-0.5, 0.5, 400),
                             np.full(400, 20.0)])
    grid = cov.build(patch, [_Cam([0, 0, 0])], _K(), (320, 240),
                     voxel=1.0, margin=6.0)
    counts = grid.counts()
    assert counts["OBSERVED"] + counts["WEAK"] > 0, "the patch itself is surface"

    # Every cell called EMPTY must have a ray that reached a finite depth.
    empty = grid.status == int(cov.Coverage.EMPTY)
    assert grid.free_count is not None
    assert np.all(grid.free_count[empty] > 0)

    # And free space must lie in front of the patch, never behind it. The
    # surface sits at z = 20 m; nothing past it was ever seen through.
    if empty.any():
        idx = np.argwhere(empty)
        z_centres = grid.origin[2] + (idx[:, 2] + 0.5) * grid.voxel
        assert z_centres.max() < 20.0


def test_free_space_stops_short_of_the_surface():
    """The slack that forgives sparse occlusion must not also clear the surface.

    ``occlusion_tol`` widens what counts as visible; applying the same slack with
    the same sign to free space would declare the last metre before a wall
    empty. It is subtracted there instead.
    """
    rng = np.random.default_rng(1)
    wall = np.column_stack([rng.uniform(-3, 3, 2000),
                            rng.uniform(-3, 3, 2000),
                            np.full(2000, 20.0)])
    grid = cov.build(wall, [_Cam([0, 0, 0])], _K(), (320, 240),
                     voxel=1.0, margin=4.0, occlusion_tol=1.5)
    empty = grid.status == int(cov.Coverage.EMPTY)
    idx = np.argwhere(empty)
    if len(idx):
        z_centres = grid.origin[2] + (idx[:, 2] + 0.5) * grid.voxel
        assert z_centres.max() <= 20.0 - 1.5 + grid.voxel


def test_free_count_survives_the_npz_round_trip(tmp_path):
    rng = np.random.default_rng(2)
    pts = np.column_stack([rng.uniform(-2, 2, 500), rng.uniform(-2, 2, 500),
                           np.full(500, 15.0)])
    grid = cov.build(pts, [_Cam([0, 0, 0])], _K(), (320, 240), voxel=1.0)
    path = grid.to_npz(tmp_path / "coverage.npz")
    d = np.load(path)
    assert "free_count" in d.files
    assert np.array_equal(d["free_count"], grid.free_count)
