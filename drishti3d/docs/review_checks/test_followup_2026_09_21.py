"""Independent review checks; run separately from the normal test suite.

These assert intended behaviour, so failures are review findings, not xfails.
All writes go to a fresh temporary directory. No saved user mission is changed.
Run from drishti3d: .venv/bin/python -m pytest docs/review_checks/test_followup_2026_09_21.py -q
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(APP / "backend"), str(APP / "reconstruction")]
os.environ["DRISHTI_DATA_DIR"] = tempfile.mkdtemp(prefix="drishti_followup_")

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import storage, results
from app.db import SessionLocal
from app.models import Measurement
from app.routers.measurements import load_cloud
from app.schemas import ProcessRequest
from drishti_recon import exports, measure, mvs, pipeline, questions as qmod
from drishti_recon import refinement as rf
from drishti_recon.fusion import PointCloud
from drishti_recon.geo import ENUFrame


def cloud(points=None):
    if points is None:
        points = [[0., 0, 0], [5., 0, 0], [10., 0, 0]]
    p = np.asarray(points, float)
    n = len(p)
    return PointCloud(p, np.full((n, 3), 180, np.uint8), np.ones(n),
                      np.zeros(n, int), sigma=np.zeros(n), sigma_major=np.zeros(n))


def write_cloud(path, c):
    np.savez(path, points=c.points, colors=c.colors, confidence=c.confidence,
             provenance=c.provenance, sigma=c.sigma, sigma_major=c.sigma_major)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def project(client, metric=True):
    pid = client.post("/api/projects", json={"name": "isolated review"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True)
    c = cloud()
    c.sigma[:] = c.sigma_major[:] = 0.02
    write_cloud(art / "cloud.npz", c)
    cams = []
    for k, x in enumerate([-5., 0., 5., 10., 15.]):
        cams.append({"frame_index": k, "C": [x, 0., -20.], "R": np.eye(3).tolist()})
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47., "lon0": 8., "alt0": 400.},
        "K": [[100., 0, 500.], [0, 100., 500.], [0, 0, 1.]],
        "image_size": [1000, 1000], "cameras_enu": cams}))
    (art / "manifest.json").write_text(json.dumps({
        "created": 1700000000., "video_sha256": "a" * 64,
        "alignment": {"scale_source": "gps", "scale": 1., "scale_sigma": .01}
                     if metric else None}))
    return pid, art


def ask(client, pid):
    r = client.post(f"/api/projects/{pid}/questions", json={
        "kind": "distance", "points": [[0, 0, 0], [10, 0, 0]], "tolerance_m": 5.})
    assert r.status_code == 200, r.text
    return r.json()


def test_original_polyline_counterexample_fixed():
    c = cloud()
    a = measure.measure_distance(c, c.points[[0, 2]], scale_sigma_rel=.1)
    b = measure.measure_distance(c, c.points, scale_sigma_rel=.1)
    assert a.value == b.value == 10.
    assert a.sigma == b.sigma == 1.


def test_original_remote_snap_counterexample_fixed():
    sn = measure.snap(cloud(), [1000, 0, 0], False)
    assert not sn.resolved
    assert sn.displacement_m == 990.


def test_single_point_cloud_must_also_refuse_remote_snap():
    sn = measure.snap(cloud([[0, 0, 0]]), [1000, 0, 0], False)
    assert not sn.resolved, sn.to_dict()


def test_original_las_crs_and_sigma_counterexample_fixed(tmp_path):
    import laspy
    frame = ENUFrame(47.3769, 8.5417, 430.)
    path = exports.export_las(tmp_path / "review.las", cloud(), frame)
    las = laspy.read(path)
    assert las.header.parse_crs().to_epsg() == 32632
    assert {"sigma", "provenance", "confidence"} <= set(las.point_format.dimension_names)


def test_original_cache_counterexample_fixed(client):
    pid, art = project(client)
    before = load_cloud(pid).points.copy()
    write_cloud(art / "cloud.npz", cloud(before + 100))
    assert np.array_equal(load_cloud(pid).points, before + 100)


def test_original_global_offset_counterexample_fixed():
    spec = importlib.util.spec_from_file_location("review_run_mission", APP / "scripts/run_mission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = np.array([[0., 0, 0], [1., 0, 0], [0., 1, 0], [1., 1, 1]])
    scored = mod._rigid_and_similarity_error(p + [100, 200, 30], p)
    assert scored["as_georeferenced"]["median_m"] == pytest.approx(np.linalg.norm([100, 200, 30]))


def test_original_distortion_field_counterexample_fixed():
    r = ProcessRequest(intrinsics={"fx": 1000, "fy": 1000, "cx": 500, "cy": 500,
                                   "distortion": [.1, 0, 0, 0, 0]})
    assert r.intrinsics.model_dump()["distortion"] == [.1, 0, 0, 0, 0]


def test_both_routes_use_nonmetric_units_without_scale(client):
    pid, _ = project(client, metric=False)
    m = client.post(f"/api/projects/{pid}/measurements", json={
        "kind": "distance", "points": [[0, 0, 0], [10, 0, 0]]}).json()
    q = ask(client, pid)["result"]
    assert m["unit"] == q["unit"] == "reconstruction units", (m["unit"], q["unit"])


def test_invalid_patch_level_is_rejected_without_persisting(client):
    pid, _ = project(client)
    q = ask(client, pid)
    r = client.patch(f"/api/projects/{pid}/questions/{q['id']}", json={"interval_level": 97})
    listed = client.get(f"/api/projects/{pid}/questions").json()[0]
    assert r.status_code in (400, 422) and listed["interval_level"] == 95, {
        "http_status": r.status_code, "stored_level": listed["interval_level"], "response": r.text}


def test_refined_result_metadata_does_not_break_tolerance_changes(client):
    # This is the exact extra key the real refinement API persists. Seed it
    # directly to isolate the downstream PATCH contract from frame recovery.
    pid, _ = project(client)
    q = ask(client, pid)
    with SessionLocal() as db:
        row = db.get(Measurement, q["result"]["id"])
        row.evidence = {**row.evidence, "endpoints_moved_m": [0.1, 0.]}
        db.commit()
    r = client.patch(f"/api/projects/{pid}/questions/{q['id']}", json={"tolerance_m": .5})
    assert r.status_code == 200, r.text


def test_video_only_artifact_export_completes(tmp_path):
    art = tmp_path / "artifacts"
    art.mkdir()
    # build_report emits alignment=None for a relative-scale reconstruction.
    pipeline._write_artifacts(art, cloud(), [], ENUFrame(0., 0., 0.),
                              {"alignment": None}, [], None, [], [])
    assert (art / "viewer.json").exists()


def test_cloud_replacement_marks_stored_question_superseded(client):
    pid, art = project(client)
    ask(client, pid)
    write_cloud(art / "cloud.npz", cloud([[0., 0, 0], [10., 0, 0], [20., 0, 0]]))
    listed = client.get(f"/api/projects/{pid}/questions").json()[0]
    assert listed["result"]["superseded"], listed["result"]["artifact_version"]


def test_dense_depth_sigma_is_positive_for_obtuse_view_angle():
    points = np.array([[0., 0, 50.]])
    half_baseline = 50. * np.sqrt(3.)
    centres = np.array([[-half_baseline, 0, 0], [half_baseline, 0, 0]])
    angle = mvs.contributing_parallax_deg(points, centres, [[0, 1]])
    assert angle[0] == pytest.approx(120.)
    sigma = mvs.depth_uncertainty(points, centres,
                                  [2], sigma_px=1., focal=1000., parallax_deg=angle)
    assert sigma[0] > 0, sigma


def test_dense_near_parallel_geometry_is_not_reported_finitely_constrained():
    sigma = mvs.depth_uncertainty([[0, 0, 50]], [[0, 0, 0], [0, 0, 0]],
                                  [2], sigma_px=1., focal=1000., parallax_deg=[0.])
    assert not np.isfinite(sigma[0]), sigma


def test_successful_frame_recovery_finishes_real_refinement_method(tmp_path, monkeypatch):
    # Exercise real refine() through its post-recovery branch. Only image I/O,
    # PnP/location and local fitting are controlled; no video/GPU is required.
    def evidence(*args, **kwargs):
        return qmod.Evidence(n_supporting_views=2, max_ray_separation_deg=10.,
                             view_support_basis="triangulated_observations",
                             endpoints_observed=True, endpoints_within_coverage=True,
                             scale_source="gps", scale_sigma_rel=.01)
    ev = SimpleNamespace(K=np.eye(3), rotations=np.stack([np.eye(3)] * 2),
                         centres=np.array([[-1., 0, -10], [1., 0, -10]]),
                         frame_indices=[0, 2], _camera_of_frame={0: 0, 2: 1},
                         has_lineage=True, for_points=evidence,
                         measured_ray_separation_deg=lambda p: 10.,
                         within_coverage=lambda p: True,
                         observations_of=lambda p: {"frame_index": np.array([0, 2]),
                                                    "uv": np.array([[.1, 0], [-.1, 0]])})
    eng = rf.RefinementEngine(ev, tmp_path)
    monkeypatch.setattr(eng, "candidates", lambda p: [rf.Candidate(1, 1.)])
    monkeypatch.setattr(eng, "_endpoint_anchors", lambda p: [(0, 0, [0, 0])])
    monkeypatch.setattr(eng, "_pnp_anchors", lambda f: [])
    monkeypatch.setattr(eng, "_register", lambda *a: (
        np.eye(3), np.array([5., 0, -10]), 30, 1., None, None, np.array([0]), np.array([[0, 0]])))
    monkeypatch.setattr(eng, "_locate", lambda *a, **kw: np.array([-.5, 0]))
    monkeypatch.setattr(eng, "_local_bundle", lambda *a: {
        "point": np.array([.1, 0, 0]), "sigma": .02, "n_cameras": 3,
        "n_points": 10, "n_observations": 30, "rmse_before": 1., "rmse_after": .5})
    run = eng.refine(qmod.MeasurementQuestion("distance", tolerance_m=.5),
                     [[0, 0, 0], [5, 0, 0]],
                     value_fn=rf.measurement_value_fn("distance", [.05, .05]),
                     budget_frames=1, max_decode=1, provenances=[0, 0])
    assert len(run.added_frames) == 1
    assert run.after["value"] == pytest.approx(4.9)
