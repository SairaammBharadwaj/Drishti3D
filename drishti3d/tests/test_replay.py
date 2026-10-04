"""Flight replay: OpenCV -> Three.js poses, interpolation, scrub/pause states."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from drishti_recon import replay as RP


def look_at(C, target):
    """OpenCV world->camera R for a camera at C looking at target, ENU z up."""
    fwd = np.asarray(target, float) - C
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    return np.stack([right, down, fwd])


def test_three_camera_looks_where_the_opencv_camera_does():
    C = np.array([0.0, -50.0, 40.0])
    R = look_at(C, [0, 0, 0])
    M = RP.quaternion_to_matrix(RP.matrix_to_quaternion(RP.opencv_to_three_rotation(R)))
    forward_three = M @ [0, 0, -1]           # Three.js cameras look down -Z
    up_three = M @ [0, 1, 0]
    assert np.allclose(forward_three, R[2], atol=1e-9)
    assert np.allclose(up_three, -R[1], atol=1e-9)
    assert up_three[2] > 0                   # image up is world up-ish, not upside down
    assert np.isclose(np.linalg.det(M), 1.0)


@pytest.mark.parametrize("seed", range(5))
def test_quaternion_round_trip(seed):
    rng = np.random.default_rng(seed)
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    M = RP.quaternion_to_matrix(q)
    q2 = RP.matrix_to_quaternion(M)
    assert np.allclose(RP.quaternion_to_matrix(q2), M, atol=1e-9)


def _track(times=(0.0, 1.0, 2.0, 6.0)):
    cams, kfs = [], []
    for i, t in enumerate(times):
        C = np.array([10.0 * i, 0.0, 50.0])
        cams.append({"frame_index": i * 30, "C": C.tolist(),
                     "R": look_at(C, C + [0, 20, -50]).tolist()})
        kfs.append({"frame_index": i * 30, "timestamp": t})
    cams.append({"frame_index": 999, "C": [0, 0, 0], "R": np.eye(3).tolist()})  # no time
    return RP.build_track(cams, kfs)


def test_track_is_timed_and_sorted():
    tr = _track()
    assert [k["t"] for k in tr] == [0.0, 1.0, 2.0, 6.0]
    assert all(len(k["quaternion"]) == 4 for k in tr)


def test_scrub_interpolates_and_labels():
    tr = _track()
    p = RP.pose_at(tr, 0.5)
    assert p["status"] == "synced"
    assert p["position"] == pytest.approx([5.0, 0.0, 50.0])
    assert p["dt_to_keyframe_s"] == pytest.approx(0.5)
    # Across the 4 s hole between 2 s and 6 s: a guess, and said so.
    g = RP.pose_at(tr, 4.0)
    assert g["status"] == "gap" and g["bracket_s"] == pytest.approx(4.0)
    assert RP.pose_at(tr, -0.1)["status"] == "out_of_range"
    assert RP.pose_at(tr, 6.5)["status"] == "out_of_range"
    end = RP.pose_at(tr, 6.0)
    assert end["status"] == "synced" and end["position"] == pytest.approx([30, 0, 50])


def test_pause_is_stable_and_scrubbing_back_is_deterministic():
    tr = _track()
    a = RP.pose_at(tr, 1.37)
    b = RP.pose_at(tr, 1.37)                 # paused: same time, same pose
    assert a == b
    RP.pose_at(tr, 5.0)                      # scrub forward then back
    assert RP.pose_at(tr, 1.37) == a


def test_slerp_stays_unit_and_takes_the_short_way():
    q0 = np.array([0, 0, 0, 1.0])
    q1 = -np.array([0, 0, np.sin(0.1), np.cos(0.1)])   # same rotation family, flipped sign
    m = RP.slerp(q0, q1, 0.5)
    assert np.linalg.norm(m) == pytest.approx(1.0)
    assert abs(m[3]) > 0.99


def test_replay_endpoint(tmp_path):
    import app.main as main
    from app import storage
    with TestClient(main.app) as client:
        pid = client.post("/api/projects", json={"name": "replay"}).json()["id"]
        art = storage.artifacts_dir(pid)
        art.mkdir(parents=True, exist_ok=True)
        cams = [{"frame_index": 0, "C": [0, 0, 50], "R": look_at(np.array([0, 0, 50.0]), [0, 20, 0]).tolist()},
                {"frame_index": 30, "C": [10, 0, 50], "R": look_at(np.array([10, 0, 50.0]), [10, 20, 0]).tolist()}]
        (art / "trajectory.json").write_text(json.dumps({
            "frame": {"lat0": 1, "lon0": 2, "alt0": 3}, "cameras_enu": cams}))
        (art / "keyframes.json").write_text(json.dumps(
            [{"frame_index": 0, "timestamp": 0.0}, {"frame_index": 30, "timestamp": 1.0}]))
        r = client.get(f"/api/projects/{pid}/replay").json()
        assert len(r["track"]) == 2 and r["max_gap_s"] == RP.MAX_GAP_S
        assert "Three.js" in r["convention"]
        p = client.get(f"/api/projects/{pid}/replay/pose", params={"t": 0.25}).json()
        assert p["status"] == "synced" and p["position"][0] == pytest.approx(2.5)
