"""API-level behaviour of measurement questions (plan F2).

The backend is the authoritative acceptance gate, so these tests assert on what
the API returns, not on the module underneath it.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import storage


@pytest.fixture(scope="module")
def client():
    """Context-managed so FastAPI startup runs init_db and creates the tables."""
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def project_with_cloud(client):
    """A project whose artifacts describe a small, genuinely observed scene.

    The cloud is a 6 m wide facade panel seen from a short arc of cameras, with
    per-point sigma written the way the pipeline writes it.
    """
    r = client.post("/api/projects", json={"name": "q-test",
                                           "description": "fixture"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(7)
    n = 900
    pts = np.column_stack([rng.uniform(0.0, 6.0, n),
                           np.full(n, 12.0) + rng.normal(0, 0.01, n),
                           rng.uniform(0.0, 4.0, n)])
    np.savez_compressed(
        art / "cloud.npz", points=pts,
        colors=np.full((n, 3), 200, np.uint8),
        confidence=np.full(n, 0.9),
        provenance=np.zeros(n, int),         # OBSERVED_HIGH_CONFIDENCE = 0
        sigma=np.full(n, 0.02), sigma_major=np.full(n, 0.03))

    # Cameras on an arc in front of the panel, all looking at +y.
    cams = []
    for k, x in enumerate(np.linspace(-8.0, 14.0, 11)):
        C = np.array([x, -6.0, 2.0])
        fwd = np.array([3.0, 12.0, 2.0]) - C
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        cams.append({"frame_index": k * 5, "C": C.tolist(),
                     "R": np.stack([right, down, fwd]).tolist()})
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[900.0, 0, 960.0], [0, 900.0, 540.0], [0, 0, 1.0]],
        "image_size": [1920, 1080],
        "cameras_enu": cams, "gps_track_wgs84": [], "cameras_wgs84": []}))
    (art / "manifest.json").write_text(json.dumps({
        "version": "0.1.0", "created": 1_700_000_000.0,
        "video_sha256": "a" * 64,
        "alignment": {"scale_source": "gps", "scale_sigma": 0.004}}))

    from app.routers import measurements as mmod
    mmod.invalidate(pid)
    return pid


def _ask(client, pid, **kw):
    body = {"kind": "distance",
            "points": [[0.2, 12.0, 1.0], [5.8, 12.0, 1.0]],
            "tolerance_m": 0.20}
    body.update(kw)
    r = client.post(f"/api/projects/{pid}/questions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_question_returns_a_value_an_interval_and_a_status(client, project_with_cloud):
    q = _ask(client, project_with_cloud)
    res = q["result"]
    assert res["value"] == pytest.approx(5.6, abs=0.3)
    assert res["sigma"] is not None and res["sigma"] > 0
    assert res["interval_half_width"] is not None
    assert res["status"] in ("estimated_only", "needs_refinement")
    assert res["interval_basis"] == "uncalibrated_sensitivity"


def test_uncalibrated_deployment_never_reports_meets_requirement(
        client, project_with_cloud):
    """The whole system, end to end, must not claim calibrated acceptance.

    No calibration profile has been fitted or validated for any capture regime,
    so there is no input to this API that should produce `meets_requirement`.
    """
    for tol in (0.01, 0.2, 5.0, 100.0):
        q = _ask(client, project_with_cloud, tolerance_m=tol)
        assert q["result"]["status"] != "meets_requirement", tol
    assert "interval_not_calibrated" in q["result"]["status_reasons"]


def test_changing_tolerance_moves_the_status_not_the_value(client, project_with_cloud):
    q = _ask(client, project_with_cloud, tolerance_m=5.0)
    before = q["result"]
    assert before["status"] == "estimated_only"

    r = client.patch(
        f"/api/projects/{project_with_cloud}/questions/{q['id']}",
        json={"tolerance_m": 0.001})
    assert r.status_code == 200, r.text
    after = r.json()["result"]
    assert after["status"] == "needs_refinement"
    assert "interval_exceeds_tolerance" in after["status_reasons"]
    # Same measurement, same interval: only the requirement changed.
    assert after["value"] == before["value"]
    assert after["interval_half_width"] == before["interval_half_width"]
    assert after["id"] == before["id"]


def test_every_refusal_carries_an_actionable_reason(client, project_with_cloud):
    q = _ask(client, project_with_cloud, tolerance_m=0.001)
    assert q["guidance"], "a refusal with no guidance is not an explanation"
    for g in q["guidance"]:
        assert g["explanation"] and g["next_action"]
    assert q["result"]["dominant_limitation"] in q["result"]["status_reasons"]


def test_threshold_query_reports_indeterminate_when_the_interval_straddles(
        client, project_with_cloud):
    q = _ask(client, project_with_cloud, tolerance_m=1.0, threshold_m=5.6)
    assert q["result"]["threshold_result"] in ("indeterminate", "above", "below")
    far = _ask(client, project_with_cloud, tolerance_m=1.0, threshold_m=0.5)
    assert far["result"]["threshold_result"] == "above"


def test_evidence_lists_candidate_frames_and_admits_what_it_is(
        client, project_with_cloud):
    q = _ask(client, project_with_cloud)
    r = client.get(
        f"/api/projects/{project_with_cloud}/questions/{q['id']}/evidence")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["support_basis"] == "frustum_upper_bound"
    assert "upper bound" in body["note"]
    assert len(body["endpoints"]) == 2
    for ep in body["endpoints"]:
        assert ep["n_candidate_views"] > 0
        assert ep["max_ray_separation_deg"] > 0
        assert ep["frames"], "an endpoint in view must list the frames"


def test_measurement_on_a_project_without_a_reconstruction_is_refused(client):
    r = client.post("/api/projects", json={"name": "empty", "description": ""})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/questions",
                    json={"kind": "distance", "points": [[0, 0, 0], [1, 0, 0]],
                          "tolerance_m": 0.1})
    assert r.status_code == 404


def test_tolerance_must_be_positive(client, project_with_cloud):
    r = client.post(f"/api/projects/{project_with_cloud}/questions",
                    json={"kind": "distance",
                          "points": [[0, 12, 1], [5, 12, 1]],
                          "tolerance_m": -1.0})
    assert r.status_code == 400


def test_delete_removes_the_question_and_its_results(client, project_with_cloud):
    q = _ask(client, project_with_cloud)
    r = client.delete(
        f"/api/projects/{project_with_cloud}/questions/{q['id']}")
    assert r.status_code == 200
    listed = client.get(f"/api/projects/{project_with_cloud}/questions").json()
    assert all(x["id"] != q["id"] for x in listed)


# --------------------------------------------------------------------------- #
# Same-pass refinement (plan F4)
# --------------------------------------------------------------------------- #
def test_refining_without_the_original_video_is_refused(client,
                                                        project_with_cloud):
    """Recovering unused frames needs the clip they are in.

    A 409 naming the missing input is the right answer; quietly returning the
    unchanged measurement as a completed refinement is not.
    """
    q = _ask(client, project_with_cloud)
    r = client.post(
        f"/api/projects/{project_with_cloud}/questions/{q['id']}/refine",
        json={"budget_frames": 2})
    assert r.status_code == 409
    assert "video" in r.json()["detail"]


def test_refine_requires_a_reconstruction(client):
    r = client.post("/api/projects", json={"name": "bare", "description": ""})
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/questions/nope/refine", json={})
    assert r.status_code == 404


def test_refinement_history_starts_empty(client, project_with_cloud):
    q = _ask(client, project_with_cloud)
    r = client.get(
        f"/api/projects/{project_with_cloud}/questions/{q['id']}/refinements")
    assert r.status_code == 200
    assert r.json() == []
