"""API contracts: /accuracy, /terrain/*, /api/system/geoid."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("rasterio")

import app.main as main
from app import storage
from drishti_recon import rasters as R
from drishti_recon.exports import enu_to_utm
from drishti_recon.geo import ENUFrame
from drishti_recon.provenance import Provenance

FRAME = ENUFrame(12.9716, 77.5946, 920.0)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _mission(client, georeferenced=True):
    pid = client.post("/api/projects", json={"name": "analysis"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)
    res = 0.5
    g = np.arange(-30, 30, res / 2) + res / 4
    X, Y = np.meshgrid(g, g)
    Z = np.clip(3 * (1 - np.hypot(X, Y) / 5), 0, None)       # cone at the origin
    Z[(X > 15) & (X < 16)] += 10                               # a wall
    enu = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    n = len(enu)
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": FRAME.lat0, "lon0": FRAME.lon0, "alt0": FRAME.alt0},
        "cameras_enu": []}))
    (art / "georeference.json").write_text(json.dumps({
        "georeferenced": georeferenced, "scale_source": "rtk",
        "vertical_datum": "ellipsoidal"}))
    utm, epsg = enu_to_utm(FRAME, enu)
    R.build_products(utm, np.full((n, 3), 120), np.full(n, 0.03),
                     np.full(n, int(Provenance.OBSERVED_HIGH_CONFIDENCE)), epsg, art,
                     res=res, vertical_datum="ellipsoidal")
    return pid


def test_volume_profile_slope_los(client):
    pid = _mission(client)
    sq = [[-8, -8, 0], [8, -8, 0], [8, 8, 0], [-8, 8, 0]]
    v = client.post(f"/api/projects/{pid}/terrain/volume", json={"polygon": sq}).json()
    assert v["status"] == "ok"
    assert v["net_m3"] == pytest.approx(np.pi * 25, rel=0.05)
    assert v["crs"] == "EPSG:32643" and v["vertical_datum"] == "ellipsoidal"
    fx = client.post(f"/api/projects/{pid}/terrain/volume",
                     json={"polygon": sq, "base": "fixed", "base_z": 0.0}).json()
    assert fx["net_m3"] == pytest.approx(np.pi * 25, rel=0.05)

    p = client.post(f"/api/projects/{pid}/terrain/profile",
                    json={"a": [-10, 0, 0], "b": [10, 0, 0]}).json()
    assert p["status"] == "ok"
    assert p["max_z"] - p["min_z"] == pytest.approx(3, abs=0.3)

    s = client.post(f"/api/projects/{pid}/terrain/slope",
                    json={"polygon": [[20, -5, 0], [25, -5, 0], [25, 5, 0], [20, 5, 0]]}).json()
    assert s["status"] == "ok" and s["mean_deg"] < 1

    los = client.post(f"/api/projects/{pid}/terrain/los",
                      json={"observer": [10, -20, 0], "target": [25, -20, 0]}).json()
    assert los["result"] == "blocked"
    vis = client.post(f"/api/projects/{pid}/terrain/los",
                      json={"observer": [-25, -20, 0], "target": [-10, -20, 0]}).json()
    assert vis["result"] == "visible"


def test_volume_outside_the_survey_refuses(client):
    pid = _mission(client)
    far = [[40, 40, 0], [60, 40, 0], [60, 60, 0], [40, 60, 0]]
    out = client.post(f"/api/projects/{pid}/terrain/volume", json={"polygon": far}).json()
    assert out["status"] == "refused"


def test_terrain_needs_georeferencing(client):
    pid = _mission(client, georeferenced=False)
    r = client.post(f"/api/projects/{pid}/terrain/profile",
                    json={"a": [0, 0, 0], "b": [1, 0, 0]})
    assert r.status_code == 409


def test_accuracy_round_trip_and_labels(client):
    pid = _mission(client)
    rng = np.random.default_rng(4)
    rows = []
    for i in range(10):
        e, n, u = rng.uniform(-25, 25), rng.uniform(-25, 25), rng.uniform(0, 3)
        lat, lon, h = FRAME.enu_to_geodetic([e, n, u])[0]
        rows.append({"id": f"P{i}", "role": "gcp" if i < 4 else "check",
                     "lat": lat, "lon": lon, "h": h,
                     "model_e": e + 0.5, "model_n": n - 0.3, "model_u": u + 0.2})
    r = client.post(f"/api/projects/{pid}/accuracy",
                    json={"points": rows, "truth_source": "synthetic survey"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["raw"]["stats"]["rmse_m"]["horizontal"] == pytest.approx(np.hypot(0.5, 0.3), abs=1e-3)
    assert rep["checkpoints"]["stats"]["rmse_m"]["3d"] < 1e-3
    assert rep["fit_residuals"]["independent"] is False
    assert rep["asprs"]["sample_sufficient"] is False
    got = client.get(f"/api/projects/{pid}/accuracy").json()
    assert got["stale"] is False and got["n_check"] == 6
    assert "accuracy_json" in client.get(f"/api/projects/{pid}/exports").json()["available"]


def test_accuracy_csv_and_bad_rows(client):
    pid = _mission(client)
    csv = "id,role,e,n,u,model_e,model_n,model_u\nA,gcp,0,0,0,0.1,0,0\nB,check,5,5,0,5.1,5,0\n"
    r = client.post(f"/api/projects/{pid}/accuracy/csv",
                    files={"file": ("cp.csv", csv, "text/csv")},
                    data={"truth_source": "tape"})
    assert r.status_code == 200, r.text
    assert r.json()["correction"]["kind"] == "translation"
    bad = client.post(f"/api/projects/{pid}/accuracy",
                      json={"points": [{"id": "x", "model_e": 0, "model_n": 0, "model_u": 0}],
                            "truth_source": "x"})
    assert bad.status_code == 422


def test_geoid_status_is_explicit(client, monkeypatch):
    from drishti_recon import position
    def missing(*a, **k):
        raise position.GeoidUnavailable("geoid grid not installed (us_nga_egm08_25.tif)")
    monkeypatch.setattr(position, "orthometric_height", missing)
    out = client.get("/api/system/geoid").json()
    assert out["available"] is False and "not installed" in out["detail"]


def test_point_info_refuses_sea_level_without_the_grid(client, monkeypatch):
    from drishti_recon import position
    def missing(*a, **k):
        raise position.GeoidUnavailable("geoid grid not installed (us_nga_egm08_25.tif)")
    monkeypatch.setattr(position, "orthometric_height", missing)
    pid = _mission(client)
    out = client.get(f"/api/projects/{pid}/point_info",
                     params={"e": 1, "n": 2, "u": 3}).json()
    assert out["h_ellipsoidal_m"] == pytest.approx(923.0, abs=0.01)
    assert out["h_msl_m"] is None                      # refused, not h copied
    assert "not installed" in out["height_note"]
