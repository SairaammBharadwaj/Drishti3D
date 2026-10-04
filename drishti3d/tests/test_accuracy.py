"""GCP correction, checkpoints and leave-one-out: independence is labelled."""
import numpy as np
import pytest

from drishti_recon import accuracy as A
from drishti_recon.geo import ENUFrame

FRAME = ENUFrame(47.3769, 8.5417, 430.0)


def _rot_z(deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def survey(n=12, seed=0, noise=0.02, n_gcp=5):
    """Truth on a 200 m site; the model is a rotated, scaled, shifted copy."""
    rng = np.random.default_rng(seed)
    truth = np.c_[rng.uniform(-100, 100, (n, 2)), rng.uniform(0, 15, n)]
    # model = s R truth + t, so truth = correction(model) recovers it.
    R, s, t = _rot_z(0.8), 1.004, np.array([1.2, -0.7, 0.45])
    measured = s * truth @ R.T + t + rng.normal(0, noise, (n, 3))
    roles = [A.GCP] * n_gcp + [A.CHECK] * (n - n_gcp)
    return [A.SurveyPoint(f"P{i}", truth[i], measured[i], roles[i]) for i in range(n)]


def test_error_stats_conventions():
    err = np.array([[3.0, 4.0, 1.0], [-3.0, -4.0, -1.0]])
    s = A.error_stats(err)
    assert s["rmse_m"]["horizontal"] == pytest.approx(5.0)
    assert s["rmse_m"]["u"] == pytest.approx(1.0)
    assert s["rmse_m"]["3d"] == pytest.approx(np.sqrt(26))
    assert s["ce90_m"] == pytest.approx(1.5175 * 5.0)
    assert s["le90_m"] == pytest.approx(1.6449)
    assert "ce90_empirical_m" not in s          # too few points


def test_similarity_correction_recovers_the_truth():
    pts = survey(noise=0.0)
    rep = A.evaluate(pts)
    assert rep["correction"]["kind"] == "similarity"
    assert rep["raw"]["stats"]["rmse_m"]["horizontal"] > 1.0
    assert rep["checkpoints"]["stats"]["rmse_m"]["3d"] < 1e-6
    assert rep["correction"]["rotation_deg"] == pytest.approx(0.8, abs=1e-6)


def test_independence_labels():
    rep = A.evaluate(survey())
    assert rep["raw"]["independent"] is True
    assert rep["checkpoints"]["independent"] is True
    assert rep["fit_residuals"]["independent"] is False
    assert "NOT independent" in rep["fit_residuals"]["label"]
    assert rep["leave_one_out"]["independent"] is False
    assert rep["headline"]["block"] == "checkpoints"
    # Fit residuals flatter the model relative to independent checkpoints.
    assert (rep["fit_residuals"]["stats"]["rmse_m"]["3d"]
            <= rep["leave_one_out"]["stats"]["rmse_m"]["3d"])


def test_all_gcps_gives_no_independent_corrected_figure():
    rep = A.evaluate(survey(n=6, n_gcp=6))
    assert "checkpoints" not in rep
    assert rep["headline"]["block"] == "raw"
    assert "no independent accuracy" in rep["headline"]["warning"]


def test_one_or_two_gcps_translate_only():
    pts = survey(n=8, n_gcp=2)
    rep = A.evaluate(pts)
    assert rep["correction"]["kind"] == "translation"
    assert rep["leave_one_out"]["correction_kinds"] == ["translation"]
    one = A.evaluate(survey(n=8, n_gcp=1))
    assert one["correction"]["kind"] == "translation"
    assert "leave_one_out" not in one


def test_collinear_gcps_fall_back_to_translation():
    pts = survey(n=8, n_gcp=4)
    for i, p in enumerate(pts[:4]):          # GCPs along one road
        p.truth[:2] = [i * 30.0, i * 30.0]
        p.measured[:2] = [i * 30.0 + 1, i * 30.0 - 1]
    rep = A.evaluate(pts)
    assert rep["correction"]["kind"] == "translation"
    assert "collinear" in rep["correction"]["note"]


def test_asprs_minimum_is_flagged():
    rep = A.evaluate(survey(n=12, n_gcp=5))
    assert rep["asprs"]["sample_sufficient"] is False
    assert "below the 30" in rep["asprs"]["note"]
    rep = A.evaluate(survey(n=40, n_gcp=5))
    assert rep["asprs"]["sample_sufficient"] is True
    assert "ce90_empirical_m" in rep["checkpoints"]["stats"]


def test_rows_in_lat_lon_utm_and_enu_agree():
    truth_enu = np.array([25.0, -40.0, 3.0])
    lat, lon, h = FRAME.enu_to_geodetic(truth_enu)[0]
    from pyproj import Transformer
    E, N = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True).transform(lon, lat)
    m = {"model_e": 25.5, "model_n": -40.2, "model_u": 3.1}
    rows = [{"id": "a", "role": "check", "lat": lat, "lon": lon, "h": h, **m},
            {"id": "b", "role": "check", "easting": E, "northing": N, "h": h,
             "epsg": 32632, **m},
            {"id": "c", "role": "check", "e": 25.0, "n": -40.0, "u": 3.0, **m}]
    pts = A.points_from_rows(rows, FRAME)
    for p in pts:
        assert np.allclose(p.truth, truth_enu, atol=2e-3)


def test_csv_input_and_errors():
    text = ("id,role,e,n,u,model_e,model_n,model_u\n"
            "g1,gcp,0,0,0,0.1,0,0\nc1,checkpoint,10,0,0,10.1,0,0\n")
    pts = A.read_csv(text, None)
    assert [p.role for p in pts] == ["gcp", "check"]
    with pytest.raises(ValueError, match="model_e"):
        A.points_from_rows([{"id": "x", "e": 0, "n": 0, "u": 0}], None)
    with pytest.raises(ValueError, match="not georeferenced"):
        A.points_from_rows([{"id": "x", "lat": 1, "lon": 2, "h": 3, "model_e": 0,
                             "model_n": 0, "model_u": 0}], None)
    with pytest.raises(ValueError, match="role"):
        A.SurveyPoint("x", [0, 0, 0], [0, 0, 0], "maybe")
    with pytest.raises(ValueError, match="unique"):
        A.evaluate([A.SurveyPoint("x", [0, 0, 0], [0, 0, 0]),
                    A.SurveyPoint("x", [1, 0, 0], [1, 0, 0])])


def test_mismatched_datums_are_refused():
    row = {"id": "x", "lat": 47.3769, "lon": 8.5417, "h": 3, "model_e": 0,
           "model_n": 0, "model_u": 0}
    with pytest.raises(ValueError, match="cannot be compared"):
        A.points_from_rows([row], FRAME, truth_datum="msl", mission_datum="unknown")
