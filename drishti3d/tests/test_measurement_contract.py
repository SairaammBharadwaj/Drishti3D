"""Regression tests for the measurement trust contract.

Each test here corresponds to a counterexample from the 2026-09-21 critical
review (docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md). They are
kept together because they share one theme: a measurement must not look more
certain, or more deliberate, than the evidence behind it.
"""
import numpy as np
import pytest

from drishti_recon import measure, uncertainty as unc
from drishti_recon.provenance import Provenance
from drishti_recon.fusion import PointCloud


def _cloud(pts, prov=None, sigma_major=None):
    pts = np.asarray(pts, float)
    n = len(pts)
    return PointCloud(
        pts,
        np.full((n, 3), 200, np.uint8),
        np.full(n, 0.9),
        np.full(n, int(Provenance.OBSERVED_HIGH_CONFIDENCE)) if prov is None else np.asarray(prov),
        None,
        None,
        np.zeros(n) if sigma_major is None else np.asarray(sigma_major, float),
    )


def _grid(n=40, extent=10.0):
    xs, ys = np.meshgrid(np.linspace(0, extent, n), np.linspace(0, extent, n))
    return _cloud(np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], 1))


# --------------------------------------------------------------------------- #
# C02 -- shared scale across a polyline
# --------------------------------------------------------------------------- #
def test_subdividing_a_straight_line_does_not_change_scale_uncertainty():
    """The review's counterexample: 1.000 m became 0.707 m on adding a vertex."""
    c = _grid()
    two = measure.measure_distance(c, [[0, 0, 0], [10, 0, 0]], scale_sigma_rel=0.10)
    three = measure.measure_distance(
        c, [[0, 0, 0], [5, 0, 0], [10, 0, 0]], scale_sigma_rel=0.10)
    five = measure.measure_distance(
        c, [[0, 0, 0], [2.5, 0, 0], [5, 0, 0], [7.5, 0, 0], [10, 0, 0]],
        scale_sigma_rel=0.10)
    assert two.value == pytest.approx(10.0, abs=1e-6)
    assert two.sigma == pytest.approx(1.0, abs=1e-9)
    assert three.sigma == pytest.approx(two.sigma, abs=1e-9)
    assert five.sigma == pytest.approx(two.sigma, abs=1e-9)


def test_scale_uncertainty_is_proportional_to_total_length():
    """With zero endpoint noise, sigma/length is exactly the scale sigma.

    Compared as a ratio rather than by doubling a length: picks snap to grid
    points, so a request for 5 m resolves to 5.128 m and an absolute doubling
    test would fail on the quantisation rather than on the physics.
    """
    c = _grid()
    short = measure.measure_distance(c, [[0, 0, 0], [5, 0, 0]], scale_sigma_rel=0.10)
    long = measure.measure_distance(c, [[0, 0, 0], [10, 0, 0]], scale_sigma_rel=0.10)
    assert short.sigma / short.value == pytest.approx(0.10, rel=1e-9)
    assert long.sigma / long.value == pytest.approx(0.10, rel=1e-9)


def test_collinear_vertex_contributes_no_endpoint_variance():
    """dL/dp vanishes for a vertex straight between its neighbours."""
    covs = [np.eye(3) * 0.04] * 3
    _, s_mid = unc.polyline_length_uncertainty(
        [[0, 0, 0], [5, 0, 0], [10, 0, 0]], covs)
    _, s_two = unc.polyline_length_uncertainty(
        [[0, 0, 0], [10, 0, 0]], covs[:2])
    assert s_mid == pytest.approx(s_two, abs=1e-12)


def test_corner_vertex_does_contribute():
    """A bend is not a straight line: the shared vertex must count."""
    covs = [np.eye(3) * 0.04] * 3
    _, s_bend = unc.polyline_length_uncertainty(
        [[0, 0, 0], [5, 0, 0], [5, 5, 0]], covs)
    _, s_straight = unc.polyline_length_uncertainty(
        [[0, 0, 0], [5, 0, 0], [10, 0, 0]], covs)
    assert s_bend > s_straight


@pytest.mark.parametrize("pts", [
    [[0, 0, 0], [10, 0, 0]],                                  # straight, 2
    [[0, 0, 0], [4, 0, 0], [10, 0, 0]],                       # straight, 3
    [[0, 0, 0], [5, 0, 0], [5, 6, 0]],                        # right angle
    [[0, 0, 0], [3, 1, 0], [6, -2, 1], [9, 2, 2]],            # wandering
])
def test_monte_carlo_matches_predicted_polyline_sigma(pts):
    """One shared scale draw plus independent endpoint noise, 20k trials."""
    P = np.asarray(pts, float)
    sig_pt, sig_scale = 0.05, 0.02
    covs = [np.eye(3) * sig_pt ** 2] * len(P)
    length, predicted = unc.polyline_length_uncertainty(
        P, covs, scale_sigma_rel=sig_scale)

    rng = np.random.default_rng(11)
    n = 20000
    # One scale factor per trial, common to the whole line -- the physical
    # situation the per-segment version got wrong.
    s = rng.normal(1.0, sig_scale, n)[:, None, None]
    noise = rng.normal(0.0, sig_pt, (n,) + P.shape)
    trials = s * P[None] + noise
    seg = np.linalg.norm(np.diff(trials, axis=1), axis=2).sum(axis=1)

    assert seg.mean() == pytest.approx(length, abs=4 * seg.std() / np.sqrt(n))
    # 20k trials gives the sample std about 0.5% precision; allow 5%.
    assert seg.std(ddof=1) == pytest.approx(predicted, rel=0.05)


def test_refinement_value_fn_agrees_with_measure():
    """C02 applies to the refinement path too, which has its own copy."""
    from drishti_recon.refinement import measurement_value_fn
    pts = [[0, 0, 0], [5, 0, 0], [10, 0, 0]]
    fn = measurement_value_fn("distance", [0.0, 0.0, 0.0], scale_sigma_rel=0.10)
    value, sigma = fn(pts)
    c = _grid()
    m = measure.measure_distance(c, pts, scale_sigma_rel=0.10)
    assert value == pytest.approx(m.value, abs=1e-9)
    assert sigma == pytest.approx(m.sigma, abs=1e-9)
    assert sigma == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# C03 -- snapping must not silently relocate a selection
# --------------------------------------------------------------------------- #
def test_selection_in_empty_space_is_refused():
    """The review's counterexample: a 990 m snap with no refusal."""
    c = _cloud([[0, 0, 0], [10, 0, 0]])
    m = measure.measure_point(c, [1000, 0, 0])
    assert m.extra["all_selections_resolved"] is False
    assert m.extra["max_snap_displacement_m"] == pytest.approx(990.0)
    assert not np.isfinite(m.sigma)
    assert any("not on measurable geometry" in w for w in m.warnings)


def test_refused_selection_keeps_the_operators_own_position():
    c = _cloud([[0, 0, 0], [10, 0, 0]])
    m = measure.measure_point(c, [1000, 0, 0])
    assert m.points_enu[0] == pytest.approx([1000.0, 0.0, 0.0])
    sel = m.extra["selection"][0]
    assert sel["requested_enu"] == pytest.approx([1000.0, 0.0, 0.0])


def test_distance_with_one_unreachable_endpoint_is_not_observable():
    c = _grid()
    m = measure.measure_distance(c, [[0, 0, 0], [0, 0, 500]])
    assert not np.isfinite(m.sigma)
    assert m.extra["all_selections_resolved"] is False


def test_ordinary_picks_resolve_with_small_displacement():
    c = _grid()
    m = measure.measure_distance(c, [[0, 0, 0], [10, 0, 0]])
    assert m.extra["all_selections_resolved"] is True
    assert m.extra["max_snap_displacement_m"] < 1e-6
    assert m.value == pytest.approx(10.0, abs=1e-6)
    assert m.warnings == []


def test_background_surface_cannot_be_substituted_by_a_nearer_one():
    """A pick on a far wall must not be answered with the near roof."""
    roof = np.stack(np.meshgrid(np.linspace(0, 4, 20), np.linspace(0, 4, 20)), -1)
    roof = np.c_[roof.reshape(-1, 2), np.full(400, 8.0)]
    wall = np.c_[np.full(400, 30.0), np.linspace(0, 4, 400), np.linspace(0, 8, 400)]
    c = _cloud(np.vstack([roof, wall]))
    # Select a point in the gap: far from both surfaces.
    m = measure.measure_point(c, [16.0, 2.0, 8.0])
    assert m.extra["all_selections_resolved"] is False


def test_snap_tolerance_tracks_cloud_spacing():
    dense = _grid(n=120)     # 10 m / 119 ~= 0.084 m spacing
    sparse = _grid(n=20)     # 10 m / 19  ~= 0.526 m spacing
    assert measure.snap_tolerance(sparse) > measure.snap_tolerance(dense)
    assert measure.snap_tolerance(dense) >= measure.MIN_SNAP_TOLERANCE_M


def test_explicit_tolerance_overrides_the_derived_one():
    c = _cloud([[0, 0, 0], [10, 0, 0]])
    loose = measure.measure_point(c, [1000, 0, 0], max_snap_m=2000.0)
    assert loose.extra["all_selections_resolved"] is True
    tight = measure.measure_point(c, [0.5, 0, 0], max_snap_m=0.1)
    assert tight.extra["all_selections_resolved"] is False


# --------------------------------------------------------------------------- #
# C09 -- absolute position error must not be fitted away
# --------------------------------------------------------------------------- #
def _scorer():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "_run_mission", Path(__file__).resolve().parents[1] / "scripts/run_mission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._rigid_and_similarity_error


def test_a_global_offset_shows_up_as_absolute_error():
    """The review's counterexample: a [100,200,30] m shift scored zero."""
    err = _scorer()
    rng = np.random.default_rng(3)
    ref = rng.normal(0, 40, (60, 3))
    offset = np.array([100.0, 200.0, 30.0])
    out = err(ref + offset, ref)
    assert out["as_georeferenced"]["median_m"] == pytest.approx(
        float(np.linalg.norm(offset)), rel=1e-9)
    assert out["as_georeferenced"]["rmse_m"] > 200.0


def test_translation_fit_removes_the_offset_and_reports_it():
    err = _scorer()
    rng = np.random.default_rng(4)
    ref = rng.normal(0, 40, (60, 3))
    offset = np.array([100.0, 200.0, 30.0])
    out = err(ref + offset, ref)["after_translation_fit"]
    assert out["median_m"] == pytest.approx(0.0, abs=1e-9)
    assert out["removed_translation_m"] == pytest.approx(list(offset), rel=1e-9)
    assert out["removed_translation_norm_m"] == pytest.approx(
        float(np.linalg.norm(offset)), rel=1e-9)


def test_perfect_agreement_is_zero_at_every_level():
    err = _scorer()
    rng = np.random.default_rng(5)
    ref = rng.normal(0, 40, (60, 3))
    out = err(ref.copy(), ref)
    for level in ("as_georeferenced", "after_translation_fit",
                  "after_similarity_fit"):
        assert out[level]["rmse_m"] == pytest.approx(0.0, abs=1e-6)


def test_similarity_fit_absorbs_a_scale_error_the_others_expose():
    err = _scorer()
    rng = np.random.default_rng(6)
    ref = rng.normal(0, 40, (60, 3))
    out = err(ref * 1.05, ref)
    assert out["as_georeferenced"]["rmse_m"] > 1.0
    assert out["after_translation_fit"]["rmse_m"] > 1.0
    assert out["after_similarity_fit"]["rmse_m"] == pytest.approx(0.0, abs=1e-6)
    # fitted_scale is applied to the estimate to bring it onto the reference,
    # so a reconstruction 5% too large fits at 1/1.05, not 1.05.
    assert out["after_similarity_fit"]["fitted_scale"] == pytest.approx(
        1 / 1.05, rel=1e-6)


def test_uncertain_points_are_not_high_confidence():
    """A point's predicted uncertainty, not only its view count, gates HIGH.

    Dense confidence depends on view count alone and fusion already requires
    four views, so without this nearly every dense point was HIGH (DEC-043).
    """
    import numpy as np
    from drishti_recon import fusion
    from drishti_recon.provenance import Provenance
    rng = np.random.default_rng(0)
    pts = rng.uniform(0, 50, (400, 3))
    conf = np.full(400, 0.85)                        # all "high" by view count
    sig_major = np.where(np.arange(400) < 200, 0.05, 0.30)
    base = fusion.fuse(pts, np.zeros((400, 3), np.uint8), conf, voxel=0,
                       remove_outliers=False, compute_normals=False,
                       sigma_major=sig_major)
    assert (base.provenance == int(Provenance.OBSERVED_HIGH_CONFIDENCE)).all()
    gated = fusion.fuse(pts, np.zeros((400, 3), np.uint8), conf, voxel=0,
                        remove_outliers=False, compute_normals=False,
                        sigma_major=sig_major, max_sigma_major_m=0.12)
    high = gated.provenance == int(Provenance.OBSERVED_HIGH_CONFIDENCE)
    assert high.sum() == 200
    assert (gated.sigma_major[high] <= 0.12).all()
    # A low-confidence point is never promoted by a small sigma.
    low = fusion.fuse(pts, np.zeros((400, 3), np.uint8), np.full(400, 0.3), voxel=0,
                      remove_outliers=False, compute_normals=False,
                      sigma_major=np.full(400, 0.01), max_sigma_major_m=0.12)
    assert not (low.provenance == int(Provenance.OBSERVED_HIGH_CONFIDENCE)).any()
