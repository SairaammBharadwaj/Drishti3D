"""Bundle adjustment: does it actually recover known geometry?

These tests are deliberately built around a scene whose answer is known exactly,
so they measure recovery of *geometry* rather than the decrease of the training
residual.  A bundle adjuster that lowers reprojection error while moving the
reconstruction away from truth has failed, and only a ground-truth comparison
can catch that.

Gauge note: reprojection error is invariant to a global similarity, so every
geometric comparison here is made after a Sim(3) fit. The fit is done on the
*points*, which span three dimensions; fitting it on the camera centres of a
straight flight line would leave the rotation about that line undetermined and
make the numbers meaningless.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import bundle                      # noqa: E402
from drishti_recon.geo import umeyama_sim3            # noqa: E402


def _make_problem(n_cams=9, n_pts=250, seed=0, pixel_noise=0.5,
                  rot_noise=0.01, trans_noise=0.05, point_noise=0.3):
    """A known scene viewed from an arc of cameras (non-degenerate gauge)."""
    rng = np.random.default_rng(seed)
    K = np.array([[800.0, 0, 480.0], [0, 800.0, 270.0], [0, 0, 1.0]])
    pts_true = rng.uniform([-10, -10, 20], [10, 10, 40], size=(n_pts, 3))

    rv_true, tv_true = [], []
    for i in range(n_cams):
        # An arc, not a line: a straight camera track leaves the roll about the
        # flight axis unobservable and makes Sim(3)-aligned checks ambiguous.
        a = np.pi * (i / (n_cams - 1) - 0.5) * 0.6
        C = np.array([14 * np.sin(a), -14 * np.cos(a) + 6.0, 3.0 * np.cos(2 * a)])
        target = np.array([0.0, 0.0, 30.0])
        fwd = target - C
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        R = np.stack([right, np.cross(fwd, right), fwd])
        rv_true.append(cv2.Rodrigues(R)[0].ravel())
        tv_true.append((-R @ C).ravel())
    rv_true, tv_true = np.array(rv_true), np.array(tv_true)

    cam_idx, pt_idx, uv = [], [], []
    for c in range(n_cams):
        proj = bundle.project(pts_true, np.tile(rv_true[c], (n_pts, 1)),
                              np.tile(tv_true[c], (n_pts, 1)),
                              np.full(n_pts, K[0, 0]), np.full(n_pts, K[1, 1]),
                              K[0, 2], K[1, 2])
        vis = ((proj[:, 0] > 0) & (proj[:, 0] < 960) &
               (proj[:, 1] > 0) & (proj[:, 1] < 540))
        for p in np.where(vis)[0]:
            cam_idx.append(c)
            pt_idx.append(p)
            uv.append(proj[p])
    cam_idx = np.array(cam_idx)
    pt_idx = np.array(pt_idx)
    uv = np.array(uv) + rng.normal(0, pixel_noise, (len(cam_idx), 2))

    init = {
        "rvecs": rv_true + rng.normal(0, rot_noise, rv_true.shape),
        "tvecs": tv_true + rng.normal(0, trans_noise, tv_true.shape),
        "points": pts_true + rng.normal(0, point_noise, pts_true.shape),
    }
    truth = {"rvecs": rv_true, "tvecs": tv_true, "points": pts_true, "K": K}
    return init, truth, (cam_idx, pt_idx, uv)


def _centers(rvecs, tvecs):
    return np.array([-cv2.Rodrigues(r)[0].T @ t for r, t in zip(rvecs, tvecs)])


def _geometric_error(rvecs, tvecs, points, truth, mask):
    """Camera-centre and point RMSE after a point-based Sim(3) gauge fit."""
    S = umeyama_sim3(points[mask], truth["points"][mask])
    cam_err = np.linalg.norm(
        S.apply(_centers(rvecs, tvecs)) - _centers(truth["rvecs"], truth["tvecs"]),
        axis=1)
    pt_err = np.linalg.norm(S.apply(points[mask]) - truth["points"][mask], axis=1)
    return float(np.sqrt((cam_err ** 2).mean())), float(np.sqrt((pt_err ** 2).mean()))


def test_ba_recovers_known_geometry():
    """BA must improve the *geometry*, not merely the training residual."""
    init, truth, (ci, pi, uv) = _make_problem()
    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv, truth["K"])
    mask = np.bincount(pi, minlength=len(truth["points"])) >= 2

    cam0, pt0 = _geometric_error(init["rvecs"], init["tvecs"], init["points"],
                                 truth, mask)
    cam1, pt1 = _geometric_error(res.rvecs, res.tvecs, res.points, truth, mask)

    # 1) the residual it optimises must reach roughly the measurement noise
    assert res.rmse_after < res.rmse_before
    assert res.rmse_after < 1.0, f"reproj {res.rmse_after:.3f}px above noise floor"
    # 2) and independently, the geometry must get closer to truth
    assert cam1 < cam0 * 0.5, f"camera error {cam0:.4f} -> {cam1:.4f} m"
    assert pt1 < pt0 * 0.5, f"point error {pt0:.4f} -> {pt1:.4f} m"


def test_ba_is_a_no_op_on_an_already_optimal_solution():
    """Feeding BA the exact answer must not degrade it."""
    _, truth, (ci, pi, uv) = _make_problem(pixel_noise=0.0)
    res = bundle.bundle_adjust(truth["rvecs"], truth["tvecs"], truth["points"],
                               ci, pi, uv, truth["K"])
    assert res.rmse_before < 1e-6
    assert res.rmse_after <= max(res.rmse_before, 1e-6) + 1e-9


def test_ba_never_returns_a_worse_reconstruction():
    """A solve that fails to improve must hand back the input untouched."""
    init, truth, (ci, pi, uv) = _make_problem()
    # One iteration is not enough to improve; the guard should reject the step.
    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv, truth["K"], max_nfev=1)
    assert res.rmse_after <= res.rmse_before
    if not res.stats["accepted"]:
        assert np.allclose(res.rvecs, init["rvecs"])
        assert np.allclose(res.points, init["points"])


def test_single_view_points_are_held_fixed():
    """Points with one observation are unobservable and must not be optimised."""
    init, truth, (ci, pi, uv) = _make_problem()
    n_pts = len(truth["points"])
    # Keep only the first observation of point 0 -> it becomes single-view.
    first = np.where(pi == 0)[0][0]
    drop = np.where(pi == 0)[0][1:]
    keep = np.ones(len(pi), bool)
    keep[drop] = False
    ci, pi, uv = ci[keep], pi[keep], uv[keep]
    assert (pi == 0).sum() == 1 and first is not None

    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv, truth["K"])
    assert res.stats["n_fixed_single_view_points"] >= 1
    # the unobservable point came back exactly as supplied
    assert np.allclose(res.points[0], init["points"][0])
    assert len(res.points) == n_pts


def test_ba_recovers_a_wrong_focal_length():
    """With real parallax, focal refinement should pull a biased focal back."""
    init, truth, (ci, pi, uv) = _make_problem()
    K_bad = truth["K"].copy()
    K_bad[0, 0] = K_bad[1, 1] = 880.0          # 10% high
    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv, K_bad, refine_focal=True)
    err_before = abs(880.0 - truth["K"][0, 0])
    err_after = abs(res.K[0, 0] - truth["K"][0, 0])
    assert err_after < err_before * 0.5, f"focal {res.K[0,0]:.1f} vs 800.0"


def test_ba_recovers_radial_distortion():
    """Distortion applied to the measurements should be recovered, not absorbed."""
    init, truth, (ci, pi, uv) = _make_problem(pixel_noise=0.0)
    K = truth["K"]
    true_dist = np.array([-0.12, 0.02, 0.0, 0.0])
    uv_d = bundle.project(truth["points"][pi], truth["rvecs"][ci],
                          truth["tvecs"][ci], np.full(len(ci), K[0, 0]),
                          np.full(len(ci), K[1, 1]), K[0, 2], K[1, 2], true_dist)
    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv_d, K, refine_distortion=True)
    assert res.rmse_after < 0.5, f"undistorted residual {res.rmse_after:.3f}px"
    assert abs(res.dist[0] - true_dist[0]) < 0.03, f"k1={res.dist[0]:.4f}"


def test_rotate_matches_opencv_rodrigues():
    """The vectorised rotation must agree with the reference implementation."""
    rng = np.random.default_rng(3)
    pts = rng.normal(size=(50, 3))
    rvecs = rng.normal(scale=0.7, size=(50, 3))
    got = bundle.rotate(pts, rvecs)
    want = np.array([cv2.Rodrigues(r)[0] @ p for p, r in zip(pts, rvecs)])
    assert np.allclose(got, want, atol=1e-9)


def test_rotate_handles_zero_rotation():
    """A zero Rodrigues vector must not produce NaN through a 0/0."""
    pts = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, 1.0]])
    got = bundle.rotate(pts, np.zeros((2, 3)))
    assert np.allclose(got, pts)


# --------------------------------------------------------------------------- #
# Analytic Jacobian
#
# A hand-derived Jacobian is the classic place for a silent sign or transpose
# error: the solver still converges, just slower and to a slightly different
# place, so nothing looks broken. These tests compare it against SciPy's own
# numerical derivative entry by entry instead of trusting it.
# --------------------------------------------------------------------------- #
def test_rotation_derivative_matches_finite_differences():
    """d(R)/d(rvec), including the small-angle branch."""
    rng = np.random.default_rng(0)
    cases = [rng.normal(scale=0.8, size=3) for _ in range(5)]
    cases += [np.zeros(3), np.array([1e-10, 0.0, 0.0])]   # small-angle branch
    for r in cases:
        analytic = bundle.drotation_drvec(r)
        eps = 1e-6
        for j in range(3):
            d = np.zeros(3)
            d[j] = eps
            Rp = cv2.Rodrigues(r + d)[0]
            Rm = cv2.Rodrigues(r - d)[0]
            numeric = (Rp - Rm) / (2 * eps)
            assert np.allclose(analytic[:, :, j], numeric, atol=1e-5), (
                f"rvec={r}, axis {j}\nanalytic=\n{analytic[:, :, j]}\n"
                f"numeric=\n{numeric}")


def _residual_fn(truth, ci, pi, uv, n_cams, n_pts, refine_focal=False):
    K = truth["K"]
    dist = np.zeros(4)

    def unpack(params):
        return bundle._unpack(params, n_cams, n_pts, K, dist, refine_focal, False)

    def residuals(params):
        rv, tv, pts, fx, fy, d = unpack(params)
        proj = bundle.project(pts[pi], rv[ci], tv[ci],
                              np.full(len(ci), float(fx)),
                              np.full(len(ci), float(fy)),
                              float(K[0, 2]), float(K[1, 2]), d)
        return (proj - uv).ravel()

    return residuals, unpack


def test_analytic_jacobian_matches_finite_differences():
    """Every entry of the analytic Jacobian must match the numerical one."""
    from scipy.optimize._numdiff import approx_derivative

    init, truth, (ci, pi, uv) = _make_problem(n_cams=4, n_pts=25)
    n_cams, n_pts = 4, 25
    keep = (np.bincount(pi, minlength=n_pts) >= 2)[pi]
    ci, pi, uv = ci[keep], pi[keep], uv[keep]

    x0 = np.concatenate([init["rvecs"].ravel(), init["tvecs"].ravel(),
                         init["points"].ravel()])
    residuals, unpack = _residual_fn(truth, ci, pi, uv, n_cams, n_pts)
    builder = bundle._analytic_jacobian(n_cams, n_pts, ci, pi, truth["K"], False)
    analytic = builder(x0, unpack).toarray()
    numeric = approx_derivative(residuals, x0, method="2-point")

    scale = max(1.0, float(np.abs(numeric).max()))
    assert np.allclose(analytic, numeric, atol=1e-4 * scale), (
        f"max abs diff {np.abs(analytic - numeric).max():.3e}")


def test_analytic_jacobian_matches_with_focal_refinement():
    """The shared focal-length column must be right too."""
    from scipy.optimize._numdiff import approx_derivative

    init, truth, (ci, pi, uv) = _make_problem(n_cams=4, n_pts=25)
    n_cams, n_pts = 4, 25
    keep = (np.bincount(pi, minlength=n_pts) >= 2)[pi]
    ci, pi, uv = ci[keep], pi[keep], uv[keep]

    x0 = np.concatenate([init["rvecs"].ravel(), init["tvecs"].ravel(),
                         init["points"].ravel(), [truth["K"][0, 0]]])
    residuals, unpack = _residual_fn(truth, ci, pi, uv, n_cams, n_pts,
                                     refine_focal=True)
    builder = bundle._analytic_jacobian(n_cams, n_pts, ci, pi, truth["K"], True)
    analytic = builder(x0, unpack).toarray()
    numeric = approx_derivative(residuals, x0, method="2-point")

    scale = max(1.0, float(np.abs(numeric).max()))
    assert np.allclose(analytic, numeric, atol=1e-3 * scale), (
        f"max abs diff {np.abs(analytic - numeric).max():.3e}")


def test_analytic_and_numeric_paths_agree_on_the_solution():
    """Switching the derivative must not change where the solve lands."""
    init, truth, (ci, pi, uv) = _make_problem()
    exact = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                                 ci, pi, uv, truth["K"])
    assert exact.stats["jacobian"] == "analytic"

    # Force the finite-difference path by declaring a (zero-effect) distortion
    # refinement, then compare the reprojection optimum reached.
    approx = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                                  ci, pi, uv, truth["K"],
                                  refine_distortion=True)
    assert approx.stats["jacobian"] == "finite_difference"
    assert abs(exact.rmse_after - approx.rmse_after) < 0.15, (
        f"analytic {exact.rmse_after:.3f}px vs numeric {approx.rmse_after:.3f}px")


def test_distortion_refinement_falls_back_to_numeric_jacobian():
    """The uncovered configuration must say so, not use a wrong derivative."""
    init, truth, (ci, pi, uv) = _make_problem()
    res = bundle.bundle_adjust(init["rvecs"], init["tvecs"], init["points"],
                               ci, pi, uv, truth["K"], refine_distortion=True)
    assert res.stats["jacobian"] == "finite_difference"
