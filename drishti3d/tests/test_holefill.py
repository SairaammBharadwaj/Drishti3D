"""Hole fill: water gets a surface at bank height, and it never becomes data.

The fill exists because a reconstruction of a city on a river has a river-shaped
hole through it. These tests pin what it may and may not do: fill a hole the
cameras saw at the height of the ground around it, ignore roofs on the bank,
leave ground no camera saw alone, and stay out of the cloud.
"""
import json

import numpy as np
import pytest

from drishti_recon import holefill
from drishti_recon.provenance import Provenance

W, H = 800, 600
F = 500.0
K = np.array([[F, 0, W / 2], [0, F, H / 2], [0, 0, 1.0]])
# Nadir: camera x -> east, camera y -> south, camera z -> down.
R_NADIR = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]])


def _cams(xs, ys, z=100.0):
    return [{"C": [x, y, z], "R": R_NADIR.tolist()} for x in xs for y in ys]


def _ground(river=(-15, 15), extent=150, step=0.5, z=0.0, seed=0):
    """Flat ground at ``z`` with an east-west river band of no points."""
    g = np.arange(-extent, extent, step)
    X, Y = np.meshgrid(g, g)
    P = np.c_[X.ravel(), Y.ravel(), np.full(X.size, z)]
    P[:, 2] += np.random.default_rng(seed).normal(0, 0.05, len(P))
    return P[~((P[:, 1] > river[0]) & (P[:, 1] < river[1]))]


def test_river_is_filled_level_at_bank_height():
    P = _ground(z=12.0)
    cams = _cams(np.arange(-60, 61, 30), np.arange(-60, 61, 30), z=112.0)
    res = holefill.fill_holes(P, cams, K, (W, H), cell=2.0)
    on_river = (np.abs(res.points[:, 1]) < 13) & (np.abs(res.points[:, 0]) < 60)
    assert on_river.sum() > 500
    assert np.allclose(res.points[on_river, 2], 12.0, atol=0.3)
    big = res.holes[0]
    assert big["rim_ground_spread_m"] < 0.5          # a level shoreline


def test_towers_on_the_bank_do_not_lift_the_water():
    P = _ground()
    # A row of 40 m-wide, 60 m-tall blocks along the north bank; only their
    # roofs are in the cloud, as in DJI_1003's east downtown.
    roofs = P[(P[:, 1] > 15) & (P[:, 1] < 55) & (np.abs(P[:, 0]) < 80)].copy()
    P = P[~((P[:, 1] > 15) & (P[:, 1] < 55) & (np.abs(P[:, 0]) < 80))]
    roofs[:, 2] = 60.0
    P = np.vstack([P, roofs])
    cams = _cams(np.arange(-60, 61, 30), np.arange(-60, 61, 30))
    res = holefill.fill_holes(P, cams, K, (W, H), cell=2.0)
    on_river = (np.abs(res.points[:, 1]) < 13) & (np.abs(res.points[:, 0]) < 40)
    assert on_river.sum() > 200
    assert res.points[on_river, 2].max() < 4.0


def test_ground_no_camera_saw_is_not_filled():
    # The survey covers the west only; the river runs on east, unseen.
    P = _ground()
    cams = _cams(np.arange(-120, -59, 30), np.arange(-60, 61, 30))
    res = holefill.fill_holes(P, cams, K, (W, H), cell=2.0)
    # Footprints at 100 m are 80 m half-wide, so the easternmost camera
    # (x = -60) sees to x = +20; nothing past that may be filled.
    assert len(res.points) > 0
    assert res.points[:, 0].max() <= 20 + 2.0


def test_no_hole_no_fill():
    P = _ground(river=(0, 0))
    cams = _cams(np.arange(-60, 61, 30), np.arange(-60, 61, 30))
    res = holefill.fill_holes(P, cams, K, (W, H), cell=2.0)
    assert res.summary()["filled_fraction"] < 0.01


def test_colorize_takes_the_pixel_under_the_point():
    cams = [{"C": [0, 0, 100.0], "R": R_NADIR.tolist()}]
    img = np.zeros((H, W, 3), np.uint8)
    img[:, : W // 2] = (255, 0, 0)       # BGR blue on the west half
    img[:, W // 2:] = (0, 0, 255)        # BGR red on the east half
    pts = np.array([[-20.0, 0, 0], [20.0, 0, 0], [5000.0, 0, 0]])
    c = holefill.colorize(pts, cams, K, (W, H), lambda i: img)
    assert tuple(c[0]) == (0, 0, 255)    # RGB blue
    assert tuple(c[1]) == (255, 0, 0)    # RGB red
    assert tuple(c[2]) == (90, 110, 125)  # unseen: the default, not a guess


def test_fill_class_is_never_measurable():
    assert not Provenance.INFERRED_FILL.measurable
    assert Provenance.INFERRED_FILL.label


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import app.main as main
    with TestClient(main.app) as c:
        yield c


def test_api_serves_fill_as_its_own_class(client):
    import app.storage as storage
    pid = client.post("/api/projects", json={"name": "fill"}).json()["id"]
    art = storage.artifacts_dir(pid)
    art.mkdir(parents=True, exist_ok=True)
    n = 10
    np.savez_compressed(art / "cloud.npz",
                        points=np.zeros((n, 3), np.float32),
                        colors=np.zeros((n, 3), np.uint8),
                        provenance=np.zeros(n, np.int64))
    (art / "viewer.json").write_text(json.dumps({
        "frame": {}, "points": [[0, 0, 0]] * n, "colors": [[0, 0, 0]] * n,
        "confidence": [1.0] * n, "provenance": [0] * n, "cameras": [], "bbox": {}}))
    np.savez_compressed(art / "fill.npz",
                        points=np.ones((4, 3), np.float32),
                        colors=np.full((4, 3), 7, np.uint8),
                        hole_id=np.zeros(4, np.int32))

    r = client.get(f"/api/projects/{pid}/model.bin")
    assert r.headers["X-Point-Count"] == "14" and r.headers["X-Fill-Count"] == "4"
    body = r.content
    prov = np.frombuffer(body[-14:], np.uint8)
    assert (prov[:n] == 0).all() and (prov[n:] == 6).all()

    r = client.get(f"/api/projects/{pid}/model.bin", params={"fill": "false"})
    assert r.headers["X-Point-Count"] == "10"

    v = client.get(f"/api/projects/{pid}/model").json()
    assert v["fill_count"] == 4 and v["provenance"][-4:] == [6] * 4
    assert v["confidence"][-4:] == [0.0] * 4
    assert "fill_count" not in client.get(
        f"/api/projects/{pid}/model", params={"fill": "false"}).json()


def test_pipeline_writes_fill_beside_the_cloud(tmp_path):
    """Stage 14b runs in a real pipeline run and never alters the cloud."""
    from drishti_recon import synth
    from drishti_recon.pipeline import PipelineParams, run
    m = synth.generate(str(tmp_path / "in"), n_frames=40, fps=20,
                       width=640, height=360)
    res = run(str(tmp_path / "proj"), m["video"], m["telemetry"],
              params=PipelineParams(do_mesh=False))
    art = tmp_path / "proj" / "artifacts"
    assert not any("hole fill skipped" in w for w in res.warnings)
    assert (art / "fill.npz").exists() and (art / "fill.json").exists()
    summary = json.loads((art / "fill.json").read_text())
    assert summary["measurable"] is False
    cloud = np.load(art / "cloud.npz")
    assert not (cloud["provenance"] == int(Provenance.INFERRED_FILL)).any()
