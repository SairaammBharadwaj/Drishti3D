"""The web job path: request validation, the worker process, and its cap.

Jobs used to run the pipeline on a thread inside the API with no memory cap.
They now run in a child process (``app.worker``) inside ``run_capped.sh``'s
scope when systemd is available. These tests pin the request contract, the
command that is launched, the worker's line protocol, and a real round trip
through the API.
"""
import json
import time

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import app.main as main
    with TestClient(main.app) as c:
        yield c


def _project_with_video(client) -> str:
    pid = client.post("/api/projects", json={"name": "job runner"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/video",
                    files={"file": ("clip.mp4", b"not a real video", "video/mp4")})
    assert r.status_code == 200
    return pid


# -- parameters --------------------------------------------------------------

def test_pipeline_params_keep_pipeline_defaults_when_omitted():
    from app.jobs import pipeline_params
    from drishti_recon.pipeline import PipelineParams
    p = pipeline_params({"engine": "colmap", "densify": "mvs",
                         "max_analyze_frames": None, "proc_max_width": None})
    assert "max_analyze_frames" not in p and "proc_max_width" not in p
    built = PipelineParams(**p)
    assert built.max_analyze_frames == PipelineParams().max_analyze_frames
    assert built.engine == "colmap" and built.densify == "mvs"


def test_pipeline_params_pass_supplied_values():
    from app.jobs import pipeline_params
    p = pipeline_params({"max_analyze_frames": 2400, "proc_max_width": 1600})
    assert p["max_analyze_frames"] == 2400 and p["proc_max_width"] == 1600


# -- the launched command ----------------------------------------------------

def test_job_command_uncapped_when_disabled(monkeypatch, tmp_path):
    import sys
    from app import jobs
    monkeypatch.setenv(jobs.JOB_MEM_ENV, "off")
    cmd, mem = jobs.job_command(tmp_path / "spec.json")
    assert mem is None
    assert cmd == [sys.executable, "-m", "app.worker", str(tmp_path / "spec.json")]


def test_job_command_capped_when_systemd_available(monkeypatch, tmp_path):
    from app import jobs
    monkeypatch.setenv(jobs.JOB_MEM_ENV, "5G")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setattr(jobs.shutil, "which", lambda name: "/usr/bin/" + name)
    cmd, mem = jobs.job_command(tmp_path / "spec.json")
    assert mem == "5G"
    assert cmd[1].endswith("scripts/run_capped.sh")
    assert cmd[2:5] == ["--mem", "5G", "--"]
    assert cmd[-3:] == ["-m", "app.worker", str(tmp_path / "spec.json")]


def test_job_command_falls_back_without_systemd(monkeypatch, tmp_path):
    from app import jobs
    monkeypatch.setenv(jobs.JOB_MEM_ENV, "6G")
    monkeypatch.setattr(jobs.shutil, "which", lambda name: None)
    _, mem = jobs.job_command(tmp_path / "spec.json")
    assert mem is None


# -- the worker's protocol ---------------------------------------------------

def _events(out: str) -> list[dict]:
    from app.worker import PREFIX
    return [json.loads(line[len(PREFIX):]) for line in out.splitlines()
            if line.startswith(PREFIX)]


def test_worker_reports_invalid_params(tmp_path, capsys):
    from app import worker
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"project_dir": str(tmp_path), "video": "x.mp4",
                                "telemetry": None, "params": {"no_such": 1}}))
    assert worker.main([str(spec)]) == 1
    ev = _events(capsys.readouterr().out)
    assert ev[-1]["event"] == "error" and "invalid job" in ev[-1]["error"]


def test_worker_reports_pipeline_failure(tmp_path, capsys):
    from app import worker
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"project_dir": str(tmp_path / "p"),
                                "video": str(tmp_path / "missing.mp4"),
                                "telemetry": None, "params": {}}))
    assert worker.main([str(spec)]) == 1
    ev = _events(capsys.readouterr().out)
    assert ev[-1]["event"] == "error"
    assert "traceback" in ev[-1]


# -- the API -----------------------------------------------------------------

def test_dense_stereo_requires_colmap(client):
    pid = _project_with_video(client)
    r = client.post(f"/api/projects/{pid}/process",
                    json={"engine": "opencv", "densify": "mvs"})
    assert r.status_code == 400
    assert "COLMAP" in r.json()["detail"]


@pytest.mark.parametrize("body", [{"engine": "vggt"}, {"densify": "nerf"},
                                  {"max_analyze_frames": 1},
                                  {"proc_max_width": 100000}])
def test_process_rejects_invalid_values(client, body):
    pid = _project_with_video(client)
    assert client.post(f"/api/projects/{pid}/process", json=body).status_code == 422


def test_process_passes_new_fields_to_the_job(client, monkeypatch):
    from app import jobs
    seen = {}
    monkeypatch.setattr(jobs, "submit",
                        lambda job_id, project_id, params: seen.update(params))
    pid = _project_with_video(client)
    r = client.post(f"/api/projects/{pid}/process", json={
        "engine": "colmap", "densify": "mvs",
        "max_analyze_frames": 2400, "proc_max_width": 1600})
    assert r.status_code == 200
    assert seen["engine"] == "colmap" and seen["densify"] == "mvs"
    assert seen["max_analyze_frames"] == 2400 and seen["proc_max_width"] == 1600


def test_failed_worker_marks_job_failed(client, monkeypatch):
    """A real round trip: the API launches the worker process, which fails on
    a file that is not a video, and the failure reaches the job record."""
    from app import jobs
    monkeypatch.setenv(jobs.JOB_MEM_ENV, "off")
    pid = _project_with_video(client)
    job = client.post(f"/api/projects/{pid}/process", json={}).json()
    deadline = time.time() + 120
    state = job
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert state["status"] == "failed", state
    assert state["error"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "failed"


def test_quality_reports_end_to_end_time(client):
    from app import storage
    pid = client.post("/api/projects", json={"name": "timing"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)
    (art / "quality_report.json").write_text(json.dumps({
        "performance": {"processing_time_s": 653.6, "video_duration_s": 677.9,
                        "processing_to_video_ratio": 0.964}}))
    q = client.get(f"/api/projects/{pid}/quality").json()
    assert "end_to_end_s" not in q["performance"]
    (art / "timing.json").write_text(json.dumps({"wall_s": 733.73,
                                                 "wall_over_video": 1.082}))
    q = client.get(f"/api/projects/{pid}/quality").json()
    assert q["performance"]["end_to_end_s"] == 733.73
    assert q["performance"]["end_to_end_ratio"] == 1.082
    assert q["performance"]["processing_time_s"] == 653.6
