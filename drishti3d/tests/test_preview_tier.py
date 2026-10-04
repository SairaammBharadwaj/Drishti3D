"""The preview preset: a real, smaller reconstruction that chains to the full run."""
from drishti_recon import keyframes, pipeline
from drishti_recon.pipeline import PipelineParams, apply_preset


def test_preview_overrides_and_never_raises_budgets():
    p = apply_preset(PipelineParams(preset="preview", densify="mvs", do_mesh=True,
                                    proc_max_width=640, max_analyze_frames=2400))
    assert p.densify == "none" and not p.do_mesh and not p.fill_holes
    assert p.proc_max_width == 640                # asked for less: keep it
    assert p.max_analyze_frames == pipeline.PREVIEW_OVERRIDES["max_analyze_frames"]
    assert keyframes.PRESETS["preview"].target_max == 40


def test_other_presets_unchanged():
    p = PipelineParams(preset="balanced", densify="mvs")
    assert apply_preset(p) is p


def test_job_params_carry_the_preset():
    from app import jobs
    assert jobs.pipeline_params({"preset": "preview", "then_full": True})["preset"] == "preview"


def test_finished_preview_queues_the_full_run(monkeypatch):
    from app import jobs
    from app.db import SessionLocal, init_db
    from app.models import Job, Project
    init_db()
    submitted = []
    monkeypatch.setattr(jobs, "submit", lambda jid, pid, params: submitted.append((jid, pid, params)))
    db = SessionLocal()
    try:
        p = Project(name="chain")
        db.add(p); db.commit(); db.refresh(p)
        nid = jobs._queue_full_run(db, p.id, {"preset": "preview", "then_full": True,
                                              "engine": "colmap", "densify": "mvs"})
        assert db.get(Job, nid).status == "queued"
    finally:
        db.close()
    (jid, pid, params), = submitted
    assert jid == nid and params["preset"] == "balanced" and params["then_full"] is False
    assert params["densify"] == "mvs"             # the full run keeps the request
