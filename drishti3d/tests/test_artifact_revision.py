"""C07: cached geometry must not survive a change to the artifacts.

The review's counterexample: replace `cloud.npz` after a cached load and the
loader still returns the previous points, so the manifest describes one
reconstruction while measurements come from another.
"""
import numpy as np
import pytest

from app import storage
from app.routers import measurements as meas
from app.config import PROJECTS_DIR

PID = "a" * 32


def _write_cloud(n, value):
    art = storage.artifacts_dir(PID)
    art.mkdir(parents=True, exist_ok=True)
    np.savez(art / "cloud.npz",
             points=np.full((n, 3), float(value)),
             colors=np.full((n, 3), 200, np.uint8),
             confidence=np.full(n, 0.9),
             provenance=np.zeros(n, np.int32),
             sigma=np.full(n, 0.01),
             sigma_major=np.full(n, 0.02))
    return art


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path, raising=False)
    import app.config as cfg
    monkeypatch.setattr(cfg, "PROJECTS_DIR", tmp_path, raising=False)
    monkeypatch.setattr(storage, "project_dir",
                        lambda pid: tmp_path / pid)
    meas._cache.clear()
    yield tmp_path
    meas._cache.clear()


def test_replacing_the_cloud_changes_what_is_measured(project):
    _write_cloud(5, 1.0)
    first = meas.load_cloud(PID)
    assert float(first.points[0][0]) == 1.0

    import time
    time.sleep(0.01)
    _write_cloud(5, 7.0)
    second = meas.load_cloud(PID)
    assert float(second.points[0][0]) == 7.0, (
        "load_cloud returned superseded geometry after the artifacts changed")


def test_revision_token_changes_with_the_artifacts(project):
    _write_cloud(5, 1.0)
    before = storage.artifact_revision(PID)
    import time
    time.sleep(0.01)
    _write_cloud(5, 2.0)
    assert storage.artifact_revision(PID) != before


def test_revision_is_stable_when_nothing_changes(project):
    _write_cloud(5, 1.0)
    assert storage.artifact_revision(PID) == storage.artifact_revision(PID)


def test_unchanged_artifacts_are_served_from_cache(project):
    _write_cloud(5, 1.0)
    a = meas.load_cloud(PID)
    b = meas.load_cloud(PID)
    assert a is b


def test_superseded_entries_do_not_accumulate(project):
    import time
    for v in (1.0, 2.0, 3.0):
        _write_cloud(5, v)
        meas.load_cloud(PID)
        time.sleep(0.01)
    assert len([k for k in meas._cache if k[0] == PID]) == 1


def test_missing_artifacts_are_a_404_not_a_stale_hit(project):
    from fastapi import HTTPException
    _write_cloud(5, 1.0)
    meas.load_cloud(PID)
    (storage.artifacts_dir(PID) / "cloud.npz").unlink()
    with pytest.raises(HTTPException):
        meas.load_cloud(PID)


# --------------------------------------------------------------------------- #
# A stored answer belongs to the artifacts that produced it
# --------------------------------------------------------------------------- #
def test_superseded_is_flagged_when_the_reconstruction_was_rebuilt():
    from app.routers.questions import _out

    class Row:
        id = "q1"; project_id = PID; kind = "distance"; label = "d"
        points_enu = [[0, 0, 0], [1, 0, 0]]; tolerance_m = 0.2
        interval_level = 95; threshold_m = None
        threshold_direction = "at_least"; allow_inferred = False; notes = ""
        created_at = updated_at = None

    class Res:
        id = "m1"; value = 1.0; unit = "m"; sigma = 0.01
        interval_half_width = 0.02; interval_level = 95
        interval_basis = "uncalibrated_sensitivity"; status = "estimated_only"
        status_reasons = []; dominant_limitation = None; threshold_result = None
        evidence = {}; warnings = []; created_at = None
        artifact_version = "old@1"

    stale = _out(Row(), Res(), "new@2")["result"]
    assert stale["superseded"] is True

    current = _out(Row(), Res(), "old@1")["result"]
    assert current["superseded"] is False


def test_unknown_current_version_is_not_reported_as_superseded():
    """Absence of information is not evidence the answer is stale."""
    from app.routers.questions import _out

    class Row:
        id = "q1"; project_id = PID; kind = "distance"; label = "d"
        points_enu = [[0, 0, 0], [1, 0, 0]]; tolerance_m = 0.2
        interval_level = 95; threshold_m = None
        threshold_direction = "at_least"; allow_inferred = False; notes = ""
        created_at = updated_at = None

    class Res:
        id = "m1"; value = 1.0; unit = "m"; sigma = 0.01
        interval_half_width = 0.02; interval_level = 95
        interval_basis = "uncalibrated_sensitivity"; status = "estimated_only"
        status_reasons = []; dominant_limitation = None; threshold_result = None
        evidence = {}; warnings = []; created_at = None
        artifact_version = "old@1"

    assert _out(Row(), Res(), None)["result"]["superseded"] is False
