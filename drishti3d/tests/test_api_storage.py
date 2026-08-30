"""API validation and path-sanitization / security tests.

Uses the isolated DRISHTI_DATA_DIR set in conftest.py.  The TestClient is used
as a context manager so FastAPI startup (init_db) runs and creates the tables.
"""
import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import app.main as main
    with TestClient(main.app) as c:
        yield c


def test_sanitize_filename():
    import app.storage as storage
    assert storage.sanitize_filename("../../etc/passwd") == "etc_passwd" or \
        "/" not in storage.sanitize_filename("../../etc/passwd")
    assert "\\" not in storage.sanitize_filename("..\\..\\win.mp4")
    assert storage.sanitize_filename("....//evil") not in ("", ".", "..")


def test_project_id_validation_blocks_traversal():
    import app.storage as storage
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        storage.project_dir("../../etc")


def test_health_and_capabilities(client):
    assert client.get("/api/health").json()["status"] == "ok"
    caps = client.get("/api/capabilities").json()
    assert caps["engines"]["opencv_sfm"] is True


def test_create_and_list_project(client):
    r = client.post("/api/projects", json={"name": "T", "description": "d"})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert client.get(f"/api/projects/{pid}").json()["name"] == "T"
    assert any(p["id"] == pid for p in client.get("/api/projects").json())


def test_process_requires_uploads(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/process", json={"preset": "balanced"})
    assert r.status_code == 400  # no video/telemetry yet


def test_reject_bad_video_extension(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/video",
                    files={"file": ("evil.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400


def test_missing_project_404(client):
    assert client.get("/api/projects/" + "0" * 32).status_code == 404
