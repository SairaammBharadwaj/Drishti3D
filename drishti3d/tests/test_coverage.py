"""The acceptance experiment for D-003: is unestablished space actually flagged?

Built as a controlled scene with a *deliberately* hidden surface. The bar is not
"the code produces a grid" — it is that the hidden surface is classified as
unestablished and refused for measurement, while the surface the cameras really
did see is accepted.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import coverage                     # noqa: E402
from drishti_recon.coverage import Coverage            # noqa: E402


class _Cam:
    """Minimal stand-in for sfm.Camera."""

    def __init__(self, R, t):
        self.R = np.asarray(R, float)
        self.t = np.asarray(t, float).ravel()

    @property
    def center(self):
        return -self.R.T @ self.t


def _look_at(C, target):
    C = np.asarray(C, float)
    fwd = np.asarray(target, float) - C
    fwd /= np.linalg.norm(fwd)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-8:
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    R = np.stack([right, np.cross(fwd, right), fwd])
    return _Cam(R, -R @ C)


def _grid_points(x_range, y_range, z, step=0.4):
    xs = np.arange(*x_range, step)
    ys = np.arange(*y_range, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    return np.stack([X.ravel(), Y.ravel(), np.full(X.size, z)], 1)


def _wall(x, y_range, z_range, step=0.4):
    ys = np.arange(*y_range, step)
    zs = np.arange(*z_range, step)
    Y, Z = np.meshgrid(ys, zs, indexing="ij")
    return np.stack([np.full(Y.size, x), Y.ravel(), Z.ravel()], 1)


K = np.array([[600.0, 0, 400.0], [0, 600.0, 300.0], [0, 0, 1.0]])
IMG = (800, 600)


def _occluded_scene():
    """A ground plane, a tall south wall, and a second wall hidden behind it.

    Every camera sits south of the near wall and looks north, so the near wall's
    far side and the wall behind it cannot be seen by any of them.
    """
    ground = _grid_points((-12, 12), (-12, 12), 0.0)
    near_wall = _wall(x=0.0, y_range=(-6, 6), z_range=(0, 8))
    far_wall = _wall(x=6.0, y_range=(-6, 6), z_range=(0, 8))
    pts = np.vstack([ground, near_wall, far_wall])

    cams = [_look_at(np.array([-14.0, y, 6.0]), np.array([0.0, y, 3.0]))
            for y in (-4.0, -1.0, 2.0, 5.0)]
    return pts, cams, near_wall, far_wall


def test_hidden_surface_is_not_measurable():
    """The wall behind a wall must be refused, the visible one accepted."""
    pts, cams, near_wall, far_wall = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)

    # Sample the near wall's own surface cells. (Sampling a fixed offset in
    # front of it instead would land in the neighbouring cell at this voxel
    # size, and would be testing the grid's quantisation rather than its
    # visibility reasoning.)
    vis_ok = grid.is_measurable(near_wall).mean()

    # The far wall is behind it from every camera.
    hidden_ok = grid.is_measurable(far_wall).mean()

    assert vis_ok > 0.5, f"visible wall only {vis_ok:.2f} measurable"
    assert hidden_ok < 0.2, f"hidden wall {hidden_ok:.2f} measurable — not refused"
    assert vis_ok > hidden_ok * 3


def test_hidden_surface_is_classified_as_unestablished():
    pts, cams, near_wall, far_wall = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)
    st = grid.status_at(far_wall)
    unestablished = np.isin(st, [int(Coverage.UNSEEN), int(Coverage.OCCLUDED)])
    assert unestablished.mean() > 0.5, grid.counts()


def test_space_the_flight_never_looked_at_is_unseen():
    """Far outside the frustums must be UNSEEN, not silently 'empty'."""
    pts, cams, _, _ = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0, margin=12.0)
    behind = np.array([[0.0, 0.0, -8.0], [0.0, 0.0, -6.0]])   # underground
    st = grid.status_at(behind)
    assert set(np.unique(st)) <= {int(Coverage.UNSEEN), int(Coverage.OCCLUDED)}


def test_free_space_between_camera_and_surface_is_reported_empty():
    """Verified-empty is a positive result and must be distinguished from unseen."""
    pts, cams, _, _ = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)
    midair = np.array([[-7.0, 0.0, 5.0], [-6.0, 1.0, 5.0]])
    st = grid.status_at(midair)
    assert (st == int(Coverage.EMPTY)).any(), grid.counts()


def test_single_view_surface_is_weak_not_observed():
    """One view cannot constrain geometry; it must not be measurable."""
    ground = _grid_points((-6, 6), (-6, 6), 0.0)
    one = [_look_at(np.array([0.0, 0.0, 12.0]), np.array([0.0, 0.0, 0.0]))]
    grid = coverage.build(ground, one, K, IMG, voxel=1.0)
    st = grid.status_at(ground)
    assert (st == int(Coverage.OBSERVED)).mean() < 0.05
    assert (st == int(Coverage.WEAK)).mean() > 0.5
    assert grid.is_measurable(ground).mean() < 0.05


def test_two_views_make_the_same_surface_measurable():
    """The contrast that shows WEAK is about view count, not about the surface."""
    ground = _grid_points((-6, 6), (-6, 6), 0.0)
    cams = [_look_at(np.array([-5.0, 0.0, 12.0]), np.array([0.0, 0.0, 0.0])),
            _look_at(np.array([5.0, 0.0, 12.0]), np.array([0.0, 0.0, 0.0]))]
    grid = coverage.build(ground, cams, K, IMG, voxel=1.0)
    assert grid.is_measurable(ground).mean() > 0.5


def test_summary_and_counts_are_consistent():
    pts, cams, _, _ = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)
    s = grid.summary()
    assert sum(s["counts"].values()) == s["n_cells"]
    assert 0.0 <= s["fraction_unseen"] <= 1.0
    assert 0.0 <= s["fraction_explained"] <= 1.0


def test_points_outside_the_grid_are_unseen_not_an_error():
    pts, cams, _, _ = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)
    far = np.array([[1e4, 1e4, 1e4], [-1e4, 0.0, 0.0]])
    assert (grid.status_at(far) == int(Coverage.UNSEEN)).all()
    assert not grid.is_measurable(far).any()


def test_grid_is_coarsened_rather_than_exploding():
    """A huge extent must degrade resolution, not allocate an enormous array."""
    pts = np.array([[0.0, 0, 0], [500.0, 500.0, 200.0]])
    cams = [_look_at(np.array([-10.0, 0, 5.0]), np.array([0.0, 0, 0])),
            _look_at(np.array([10.0, 0, 5.0]), np.array([0.0, 0, 0]))]
    grid = coverage.build(pts, cams, K, IMG, voxel=0.05, max_cells=200_000)
    assert int(np.prod(grid.shape)) <= 200_000
    assert grid.voxel > 0.05


def test_recapture_hints_point_at_the_gaps():
    pts, cams, _, _ = _occluded_scene()
    grid = coverage.build(pts, cams, K, IMG, voxel=1.0)
    hints = coverage.recapture_hints(grid, top=3)
    assert hints, "a scene with a hidden wall should produce recapture advice"
    assert all(h["unestablished_cells"] > 0 for h in hints)
    # hints must be ordered worst-first so a pilot acts on the biggest gap
    counts = [h["unestablished_cells"] for h in hints]
    assert counts == sorted(counts, reverse=True)


def test_coverage_classes_order_and_measurability():
    assert Coverage.OBSERVED > Coverage.WEAK > Coverage.EMPTY
    assert Coverage.OBSERVED.measurable
    for c in (Coverage.UNSEEN, Coverage.OCCLUDED, Coverage.EMPTY, Coverage.WEAK):
        assert not c.measurable


# --------------------------------------------------------------------------- #
# Dynamic exclusion
#
# Closes the last part of D-003: a masked moving object produces no point, so
# `DYNAMIC_EXCLUDED` could never appear in a point cloud. It is a property of
# space -- the cameras looked, and the evidence was deliberately discarded.
# --------------------------------------------------------------------------- #
def _masked_scene():
    """Ground plane viewed from above, with the +x half of every image masked."""
    ground = _grid_points((-8, 8), (-8, 8), 0.0)
    cams = [_look_at(np.array([dx, dy, 20.0]), np.array([0.0, 0.0, 0.0]))
            for dx, dy in ((-4, -4), (4, -4), (4, 4), (-4, 4))]
    masks = []
    for _ in cams:
        m = np.full((600, 800), 255, np.uint8)
        m[:, 400:] = 0            # right half of the image is "dynamic"
        masks.append(m)
    return ground, cams, masks


def test_masked_region_is_marked_dynamic_not_empty_or_unseen():
    ground, cams, masks = _masked_scene()
    grid = coverage.build(ground, cams, K, IMG, masks=masks, voxel=1.0)
    counts = grid.counts()
    assert counts["DYNAMIC_EXCLUDED"] > 0, counts
    assert grid.meta["masks_supplied"] is True


def test_masking_reduces_measurable_surface():
    """Discarded observations must cost coverage, not be silently ignored."""
    ground, cams, masks = _masked_scene()
    unmasked = coverage.build(ground, cams, K, IMG, voxel=1.0)
    masked = coverage.build(ground, cams, K, IMG, masks=masks, voxel=1.0)
    assert (masked.is_measurable(ground).mean()
            < unmasked.is_measurable(ground).mean())


def test_dynamic_excluded_is_not_measurable():
    assert not Coverage.DYNAMIC_EXCLUDED.measurable
    # ...and it is ordered below verified-empty, because discarded evidence is
    # a weaker statement about space than evidence that was actually collected.
    assert Coverage.DYNAMIC_EXCLUDED < Coverage.EMPTY


def test_no_masks_means_no_dynamic_cells():
    ground, cams, _ = _masked_scene()
    grid = coverage.build(ground, cams, K, IMG, voxel=1.0)
    assert grid.counts()["DYNAMIC_EXCLUDED"] == 0
    assert grid.meta["masks_supplied"] is False
