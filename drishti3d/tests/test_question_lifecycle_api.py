"""The whole question lifecycle as one sequence, through the API.

The follow-up verification asked for exactly this: "create -> successful
refine -> change tolerance -> reload -> inspect evidence. Do not test only
isolated snapshot dictionaries."

Three of its findings were invisible to unit tests because each step worked
alone and only the *transitions* were broken -- refinement wrote a key that the
next tolerance change could not read, a rejected PATCH left the question
mutated, and a rebuilt cloud left stored answers looking current. A sequence
test is the only shape that catches those.
"""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("DRISHTI_DATA_DIR",
                      tempfile.mkdtemp(prefix="drishti_lifecycle_"))

from fastapi.testclient import TestClient

from app.main import app
from app import storage
from app.db import SessionLocal
from app.models import Measurement
from drishti_recon.fusion import PointCloud


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _cloud(points):
    p = np.asarray(points, float)
    n = len(p)
    return PointCloud(p, np.full((n, 3), 180, np.uint8), np.ones(n),
                      np.zeros(n, int), sigma=np.full(n, 0.02),
                      sigma_major=np.full(n, 0.02))


def _write_cloud(path, c):
    np.savez(path, points=c.points, colors=c.colors, confidence=c.confidence,
             provenance=c.provenance, sigma=c.sigma, sigma_major=c.sigma_major)


def _project(client, created=1700000000.0):
    pid = client.post("/api/projects",
                      json={"name": f"lifecycle {created}"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)
    _write_cloud(art / "cloud.npz",
                 _cloud([[0, 0, 0], [5, 0, 0], [10, 0, 0]]))
    cams = [{"frame_index": k, "C": [x, 0.0, -20.0], "R": np.eye(3).tolist()}
            for k, x in enumerate([-5.0, 0.0, 5.0, 10.0, 15.0])]
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[100.0, 0, 500.0], [0, 100.0, 500.0], [0, 0, 1.0]],
        "image_size": [1000, 1000], "cameras_enu": cams}))
    (art / "manifest.json").write_text(json.dumps({
        "created": created, "video_sha256": "a" * 64,
        "params": {"mask_backend": "none"},
        "alignment": {"scale_source": "gps", "scale": 1.0,
                      "scale_sigma": 0.01}}))
    return pid, art


def _ask(client, pid, tol=5.0):
    r = client.post(f"/api/projects/{pid}/questions", json={
        "kind": "distance", "points": [[0, 0, 0], [10, 0, 0]],
        "tolerance_m": tol, "label": "span"})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_sequence_create_refine_retolerance_reload_evidence(client):
    pid, _ = _project(client)
    q = _ask(client, pid)
    assert q["result"]["value"] == pytest.approx(10.0)
    first_version = q["result"]["artifact_version"]

    # Simulate what a successful refinement persists, including the
    # diagnostics that used to break the next step.
    with SessionLocal() as db:
        row = db.get(Measurement, q["result"]["id"])
        row.evidence = {**(row.evidence or {}),
                        "diagnostics": {"endpoints_moved_m": [0.12, 0.0]}}
        db.commit()

    # Change tolerance: must succeed and re-decide, not re-measure.
    r = client.patch(f"/api/projects/{pid}/questions/{q['id']}",
                     json={"tolerance_m": 0.05})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["status"] in (
        "needs_refinement", "estimated_only", "not_observable")

    # Reload from a fresh listing: the change must have persisted.
    listed = client.get(f"/api/projects/{pid}/questions").json()[0]
    assert listed["tolerance_m"] == pytest.approx(0.05)
    assert listed["result"]["artifact_version"] == first_version
    assert listed["result"]["superseded"] is False

    # Evidence must still assemble for the stored result.
    ev = client.get(f"/api/projects/{pid}/questions/{q['id']}/evidence")
    assert ev.status_code == 200, ev.text
    assert ev.json()["endpoints"]


def test_a_rejected_change_leaves_the_question_untouched(client):
    pid, _ = _project(client, created=1700000001.0)
    q = _ask(client, pid)
    before = client.get(f"/api/projects/{pid}/questions").json()[0]

    bad = client.patch(f"/api/projects/{pid}/questions/{q['id']}",
                       json={"interval_level": 97})
    assert bad.status_code in (400, 422), bad.text

    after = client.get(f"/api/projects/{pid}/questions").json()[0]
    assert after["interval_level"] == before["interval_level"]
    assert after["tolerance_m"] == before["tolerance_m"]
    assert after["result"]["value"] == before["result"]["value"]


def test_a_rebuilt_cloud_supersedes_then_re_asking_clears_it(client):
    pid, art = _project(client, created=1700000002.0)
    q = _ask(client, pid)
    assert q["result"]["superseded"] is False

    # Rebuild: same manifest, different geometry. This is the shape a partial
    # or failed rerun leaves behind.
    import time
    time.sleep(0.01)
    _write_cloud(art / "cloud.npz",
                 _cloud([[0, 0, 0], [5, 0, 0], [12, 0, 0]]))

    listed = client.get(f"/api/projects/{pid}/questions").json()[0]
    assert listed["result"]["superseded"] is True

    again = client.patch(f"/api/projects/{pid}/questions/{q['id']}",
                         json={"tolerance_m": 5.0})
    assert again.status_code == 200, again.text
    assert again.json()["result"]["superseded"] is False
    # Re-measured against the new geometry, not the old value re-decided.
    assert again.json()["result"]["value"] == pytest.approx(12.0, abs=0.2)


def test_both_creation_routes_agree_on_the_same_geometry(client):
    pid, _ = _project(client, created=1700000003.0)
    q = _ask(client, pid)
    m = client.post(f"/api/projects/{pid}/measurements", json={
        "kind": "distance", "points": [[0, 0, 0], [10, 0, 0]]}).json()
    assert m["unit"] == q["result"]["unit"]
    assert m["value"] == pytest.approx(q["result"]["value"])
    assert m["sigma"] == pytest.approx(q["result"]["sigma"])
    assert m["artifact_version"] == q["result"]["artifact_version"]
    assert m["interval_basis"] == q["result"]["interval_basis"]


def test_an_unanswerable_question_is_never_stored(client):
    pid, _ = _project(client, created=1700000004.0)
    before = len(client.get(f"/api/projects/{pid}/questions").json())
    bad = client.post(f"/api/projects/{pid}/questions", json={
        "kind": "area", "points": [[0, 0, 0], [10, 0, 0]], "tolerance_m": 1.0})
    assert bad.status_code in (400, 422), bad.text
    after = len(client.get(f"/api/projects/{pid}/questions").json())
    assert after == before
