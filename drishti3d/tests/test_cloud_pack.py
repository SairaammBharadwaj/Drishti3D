"""The packed cloud (model.pack) must carry the same points as model.bin,
within the stated display precision, with each point's colour and provenance."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from app import cloud_pack


def _scene(n=20000, seed=4):
    """A 1.4 km x 1.2 km x 97 m extent, like DJI_1001, with ENU offsets."""
    rng = np.random.default_rng(seed)
    pts = rng.uniform([-700, -600, 30], [717.6, 607.1, 127], size=(n, 3)).astype(np.float32)
    rgb = rng.integers(0, 256, size=(n, 3), dtype=np.uint8)
    prov = rng.choice([0, 1, 2, 6], size=n).astype(np.uint8)
    return pts, rgb, prov


def test_round_trip_keeps_every_point_within_half_a_step():
    pts, rgb, prov = _scene()
    xyz, rgb2, prov2 = cloud_pack.decode(cloud_pack.encode(pts, rgb, prov))
    assert len(xyz) == len(pts)
    step = float((pts.max(0) - pts.min(0)).max()) / 65535
    dist, idx = cKDTree(pts).query(xyz)
    # Each decoded point is its original, moved by at most half a step per
    # axis (plus float32 rounding), and it carries that point's attributes.
    assert dist.max() <= np.sqrt(3) * step / 2 + 1e-3
    assert len(set(idx.tolist())) == len(pts)          # a one-to-one match
    assert (rgb2 == rgb[idx]).all() and (prov2 == prov[idx]).all()
    assert step < 0.022                                 # ~2 cm on this extent


def test_it_is_much_smaller_than_model_bin_on_structured_data():
    # A gently undulating surface, sampled densely: what drone clouds are.
    x, y = np.meshgrid(np.linspace(0, 400, 400), np.linspace(0, 300, 300))
    z = 20 + 3 * np.sin(x / 40) + 2 * np.cos(y / 25)
    pts = np.column_stack([x.ravel(), y.ravel(), z.ravel()]).astype(np.float32)
    n = len(pts)
    rgb = np.column_stack([(z.ravel() * 8) % 256] * 3).astype(np.uint8)
    blob = cloud_pack.encode(pts, rgb, np.zeros(n, np.uint8))
    assert len(blob) < 16 * n / 2.5


def test_empty_and_single_point_clouds():
    for n in (0, 1):
        pts, rgb, prov = _scene(n=n)
        xyz, rgb2, prov2 = cloud_pack.decode(cloud_pack.encode(pts, rgb, prov))
        assert len(xyz) == n and np.allclose(xyz, pts, atol=1e-3)


def test_endpoint_serves_the_pack_uncompressed_in_transit(tmp_path):
    from fastapi.testclient import TestClient
    import app.main as main
    from app import storage

    with TestClient(main.app) as c:
        pid = c.post("/api/projects", json={"name": "pack"}).json()["id"]
        art = storage.artifacts_dir(pid)
        art.mkdir(parents=True, exist_ok=True)
        pts, rgb, prov = _scene(n=5000)
        np.savez_compressed(art / "cloud.npz", points=pts, colors=rgb,
                            confidence=np.ones(len(pts)), provenance=prov)
        r = c.get(f"/api/projects/{pid}/model.pack", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert "content-encoding" not in r.headers     # the browser decodes it
        assert int(r.headers["content-length"]) == len(r.content)
        xyz, _, _ = cloud_pack.decode(r.content)
        assert len(xyz) == len(pts)
