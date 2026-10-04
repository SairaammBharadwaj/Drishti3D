"""The read-only showcase: what it refuses, where visitors' writes go, and
that an exported bundle's stored answers survive being uploaded.

Uses the isolated DRISHTI_DATA_DIR set in conftest.py.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import config, sandbox, showcase, storage
from app.db import SessionLocal
from app.models import Measurement, Project


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def project(client):
    """A finished project with a small observed cloud and camera trajectory."""
    pid = client.post("/api/projects", json={"name": "showcase-test"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    n = 600
    pts = np.column_stack([rng.uniform(0, 6, n), np.full(n, 12.0),
                           rng.uniform(0, 4, n)])
    np.savez_compressed(art / "cloud.npz", points=pts,
                        colors=np.full((n, 3), 200, np.uint8),
                        confidence=np.full(n, 0.9),
                        provenance=np.zeros(n, int), sigma=np.full(n, 0.02))
    cams = []
    for k, x in enumerate(np.linspace(-8, 14, 9)):
        C = np.array([x, -6.0, 2.0])
        fwd = (np.array([3.0, 12.0, 2.0]) - C) / np.linalg.norm(
            np.array([3.0, 12.0, 2.0]) - C)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        cams.append({"frame_index": k, "C": C.tolist(),
                     "R": np.stack([right, np.cross(fwd, right), fwd]).tolist()})
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[900.0, 0, 960.0], [0, 900.0, 540.0], [0, 0, 1.0]],
        "image_size": [1920, 1080], "cameras_enu": cams,
        "gps_track_wgs84": [], "cameras_wgs84": []}))
    (art / "manifest.json").write_text(json.dumps({
        "created": 1_700_000_000.0, "video_sha256": "b" * 64,
        "alignment": {"scale_source": "gps", "scale_sigma": 0.004}}))
    with SessionLocal() as db:
        db.get(Project, pid).status = "done"
        db.commit()
    return pid


@pytest.fixture()
def read_only(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "READ_ONLY", True)
    monkeypatch.setattr(config, "SANDBOX_DIR", tmp_path / "sandboxes")
    sandbox.reset()
    yield
    sandbox.reset()


SPAN = [[0.5, 12.0, 1.0], [5.5, 12.0, 1.0]]


def _as(visitor: str | None) -> dict:
    return {sandbox.HEADER: visitor} if visitor else {}


def test_refuses_everything_but_measuring_and_asking(client, project, read_only):
    assert client.post("/api/projects", json={"name": "x"}).status_code == 403
    assert client.delete(f"/api/projects/{project}").status_code == 403
    assert client.post(f"/api/projects/{project}/process",
                       json={}).status_code == 403
    assert client.post(f"/api/projects/{project}/questions/{'0' * 32}/refine",
                       json={"budget_frames": 4}).status_code == 403
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/deployment").json()["read_only"] is True


def test_visitor_writes_stay_with_that_visitor(client, project, read_only):
    a, b = secrets.token_hex(16), secrets.token_hex(16)
    r = client.post(f"/api/projects/{project}/measurements", headers=_as(a),
                    json={"kind": "distance", "points": SPAN,
                          "allow_inferred": False})
    assert r.status_code == 200, r.text
    assert r.json()["artifact_version"]       # the full contract, not a bare number

    def seen(visitor):
        return len(client.get(f"/api/projects/{project}/measurements",
                              headers=_as(visitor)).json())
    assert (seen(a), seen(b), seen(None)) == (1, 0, 0)
    with SessionLocal() as db:
        assert db.query(Measurement).filter_by(project_id=project).count() == 0

    # A question needs its row to exist across requests: tolerance, evidence.
    q = client.post(f"/api/projects/{project}/questions", headers=_as(a),
                    json={"kind": "distance", "points": SPAN,
                          "tolerance_m": 0.5}).json()
    base = f"/api/projects/{project}/questions/{q['id']}"
    assert client.patch(base, headers=_as(a),
                        json={"tolerance_m": 1.0}).json()["tolerance_m"] == 1.0
    assert client.get(f"{base}/evidence", headers=_as(a)).status_code == 200
    assert client.get(f"{base}/evidence", headers=_as(b)).status_code == 404


def test_least_recently_used_copy_is_discarded(client, read_only, monkeypatch):
    monkeypatch.setattr(config, "SANDBOX_MAX", 2)
    ids = [secrets.token_hex(16) for _ in range(3)]
    for sid in ids:
        sandbox.session(sid, write=True).close()
    kept = sorted(p.stem for p in config.SANDBOX_DIR.iterdir())
    assert kept == sorted(ids[1:])


def test_normal_mode_is_unaffected(client, project):
    assert client.get("/api/deployment").json() == {"read_only": False,
                                                    "credits": []}
    r = client.post(f"/api/projects/{project}/measurements",
                    json={"kind": "distance", "points": SPAN,
                          "allow_inferred": False})
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(Measurement).filter_by(project_id=project).count() == 1


def test_exported_answers_stay_current_after_upload(client, project, tmp_path,
                                                    monkeypatch):
    """Upload resets file times; the revision stored answers carry must survive."""
    from scripts import export_showcase as ex

    q = client.post(f"/api/projects/{project}/questions",
                    json={"kind": "distance", "points": SPAN,
                          "tolerance_m": 0.5}).json()
    version = q["result"]["artifact_version"]
    art = storage.artifacts_dir(project)
    (art / "viewer.json").write_text("{}")
    (art / "quality_report.json").write_text(
        json.dumps({"source": str(ex.WORKSPACE / "datasets" / "video.mp4")}))

    out = tmp_path / "bundle"
    monkeypatch.setattr(sys, "argv", [
        "export_showcase", "--data", str(config.DATA_DIR), "--out", str(out),
        "--project", f"{project}:agz"])
    ex.main()

    con = sqlite3.connect(out / "drishti3d.db")
    assert con.execute("select id from projects").fetchall() == [(project,)]
    con.close()
    exported = out / "projects" / project / "artifacts"
    assert "<workspace>/datasets" in (exported / "quality_report.json").read_text()
    assert showcase.credits(out) == [ex.CREDITS["agz"]]

    from app import results
    monkeypatch.setattr(storage, "PROJECTS_DIR", out / "projects")
    assert results.artifact_version(project) == version
    for f in exported.iterdir():                 # what an upload does
        os.utime(f, ns=(1, 1))
    assert results.artifact_version(project) != version
    assert showcase.restore_times(out) > 0
    assert results.artifact_version(project) == version


def test_space_folder_is_publishable(tmp_path, monkeypatch):
    """Everything in it goes public: credits in, uncredited assets out."""
    from pathlib import Path
    from scripts import build_space as bs

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / showcase.MANIFEST).write_text(json.dumps({
        "format": showcase.FORMAT, "exported_at": "t", "code_version": "v",
        "credits": {"agz": "AGZ credit line"},
        "projects": {"a" * 32: {"name": "n", "dataset": "agz", "files": {}}}}))
    out = tmp_path / "space"
    monkeypatch.setattr(sys, "argv", ["build_space", "--bundle", str(bundle),
                                      "--out", str(out)])
    bs.main()

    for rel in bs.UNCREDITED:
        assert not (out / "frontend" / rel).exists()
    assert "- AGZ credit line" in (out / "README.md").read_text()
    local = str(Path.home())
    assert not [p for p in out.rglob("*") if p.is_file()
                and local in p.read_text(errors="ignore")]

    stranger = tmp_path / "elsewhere"
    stranger.mkdir()
    (stranger / "keep.txt").write_text("not a space folder")
    monkeypatch.setattr(sys, "argv", ["build_space", "--bundle", str(bundle),
                                      "--out", str(stranger), "--replace"])
    with pytest.raises(SystemExit):
        bs.main()
    assert (stranger / "keep.txt").exists()


def test_json_is_compressed_but_the_point_cloud_is_not(client, project):
    gz = {"Accept-Encoding": "gzip"}
    r = client.get(f"/api/projects/{project}/trajectory", headers=gz)
    assert r.headers.get("content-encoding") == "gzip"
    r = client.get(f"/api/projects/{project}/model.bin", headers=gz)
    assert r.status_code == 200
    assert "content-encoding" not in r.headers        # the progress bar reads it
    assert int(r.headers["content-length"]) == len(r.content)


def test_only_unchanging_data_is_cacheable(client, project, read_only):
    r = client.get(f"/api/projects/{project}/trajectory")
    assert r.headers["cache-control"].startswith("public")
    r = client.get(f"/api/projects/{project}/measurements")
    assert "public" not in r.headers.get("cache-control", "")


def test_page_visits_on_the_stable_address_go_to_the_fast_one(client, monkeypatch):
    from app import tunnel
    monkeypatch.setattr(config, "QUICKTUNNEL_METRICS", "http://tunnel:20241/quicktunnel")
    monkeypatch.setattr(config, "REDIRECT_HOSTS", (".ts.net",))
    fast = {"host": "fast-name.trycloudflare.com"}
    monkeypatch.setattr(tunnel, "quick_tunnel_host", lambda: fast["host"])
    page = {"host": "drishti3d.tailnet.ts.net", "accept": "text/html"}

    r = client.get("/missions?x=1", headers=page, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://fast-name.trycloudflare.com/missions?x=1"
    # Data requests are answered where they arrive, never sent cross-origin.
    assert client.get("/api/projects", headers=page, follow_redirects=False).status_code == 200
    # Nor are visits on any other address, or when there is no fast one.
    other = {"host": "127.0.0.1:7860", "accept": "text/html"}
    assert client.get("/missions", headers=other, follow_redirects=False).status_code != 307
    fast["host"] = None
    assert client.get("/missions", headers=page, follow_redirects=False).status_code != 307


def test_raster_summary_and_previews_are_served(client, project, tmp_path):
    import json as _json
    art = storage.artifacts_dir(project)
    # Minimal products, as rasters.build_products leaves them.
    (art / "rasters.json").write_text(_json.dumps({"cell_size_m": 0.5}))
    (art / "ortho_preview.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    r = client.get(f"/api/projects/{project}/rasters")
    assert r.status_code == 200
    assert r.json() == {"summary": {"cell_size_m": 0.5}, "previews": ["ortho"]}
    img = client.get(f"/api/projects/{project}/rasters/ortho.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    # only the fixed preview names, never a path from the URL
    assert client.get(f"/api/projects/{project}/rasters/secret.png").status_code == 404
    assert client.get(f"/api/projects/{project}/rasters/..%2Fcloud.png").status_code == 404


def test_point_info_gives_coordinates_and_says_what_placed_them(client, project):
    import json as _json
    art = storage.artifacts_dir(project)
    (art / "georeference.json").write_text(_json.dumps(
        {"georeferenced": True, "scale_source": "gps"}))
    r = client.get(f"/api/projects/{project}/point_info", params={"e": 0, "n": 0, "u": 0})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["georeferenced"] and abs(d["lat"] - 47.0) < 1e-6        # the fixture's frame
    assert d["utm"]["epsg"] == 32632
    assert d["placement_source"] == "gps" and "unverified" in d["placement_note"]
    # A sidecar from before the datum was recorded: no height, and why (DEC-047).
    assert d["vertical_datum"] == "unknown"
    assert d["h_msl_m"] is None and d["h_ellipsoidal_m"] is None and d["height_note"]
    (art / "georeference.json").write_text(_json.dumps(
        {"georeferenced": True, "scale_source": "rtk", "vertical_datum": "ellipsoidal",
         "vertical_datum_basis": "altitude_reference ELLIPSOIDAL"}))
    d = client.get(f"/api/projects/{project}/point_info", params={"e": 0, "n": 0, "u": 0}).json()
    assert d["vertical_datum"] == "ellipsoidal" and d["h_ellipsoidal_m"] is not None
    assert d["vertical_datum_basis"] == "altitude_reference ELLIPSOIDAL"
    assert (d["h_msl_m"] is None) == ("height_note" in d)             # a height or a reason
    (art / "georeference.json").write_text(_json.dumps(
        {"georeferenced": False, "scale_source": "relative"}))
    d = client.get(f"/api/projects/{project}/point_info", params={"e": 0, "n": 0, "u": 0}).json()
    assert d == {"georeferenced": False,
                 "note": "relative scale: this reconstruction has no position on the earth"}
