"""The performance rewrites must compute exactly what they replaced.

Each vectorised function is checked against a straightforward per-point
reference written here in the form the production code used to take. Checked
separately on DJI_1003's 2.63 M dense points: parallax identical to 1e-12 deg,
visibility and dense observations identical (docs: TESTS_AND_RESULTS.md).
"""
from types import SimpleNamespace

import numpy as np
import pytest

from drishti_recon import mvs, pipeline


def _ragged(rng, n, n_img, max_len=9, bad=True):
    out = []
    for _ in range(n):
        k = int(rng.integers(0, max_len))
        v = rng.integers(0, n_img, k)
        if bad and k and rng.random() < 0.1:
            v[0] = n_img + 3                      # out of range
        out.append(v.astype(np.int32))
    return out


def _parallax_reference(points, centres, view_indices):
    out = np.full(len(points), np.nan)
    for i, idx in enumerate(view_indices):
        idx = np.asarray(idx, int).ravel()
        idx = idx[(idx >= 0) & (idx < len(centres))]
        if len(idx) < 2:
            continue
        d = centres[idx] - points[i]
        n = np.linalg.norm(d, axis=1)
        ok = n > 1e-9
        if ok.sum() < 2:
            continue
        u = d[ok] / n[ok, None]
        out[i] = np.degrees(np.arccos(np.clip(u @ u.T, -1, 1).min()))
    return out


def test_parallax_matches_per_point_reference():
    rng = np.random.default_rng(1)
    centres = rng.normal(0, 30, (12, 3)) + [0, 0, 80]
    pts = rng.normal(0, 20, (3000, 3))
    views = _ragged(rng, len(pts), len(centres))
    pts[5] = centres[views[5][0]] if len(views[5]) else pts[5]   # a zero ray
    ref = _parallax_reference(pts, centres, views)
    got = mvs.contributing_parallax_deg(pts, centres, views)
    assert np.array_equal(np.isnan(ref), np.isnan(got))
    ok = np.isfinite(ref)
    # arccos is ill-conditioned at 1: a track that lists the same camera twice
    # gives 8.5e-7 deg by matmul and exactly 0 by einsum. Both mean "no angle".
    assert np.allclose(ref[ok], got[ok], atol=1e-5)
    # CSR input gives the same answer as ragged input.
    got2 = mvs.contributing_parallax_deg(pts, centres, csr=mvs.ragged_to_csr(views))
    assert np.array_equal(np.isnan(got), np.isnan(got2))
    assert np.allclose(got[ok], got2[ok])


def test_parallax_chunks_do_not_change_the_answer(monkeypatch):
    rng = np.random.default_rng(2)
    centres = rng.normal(0, 30, (8, 3)) + [0, 0, 80]
    pts = rng.normal(0, 20, (500, 3))
    views = _ragged(rng, len(pts), len(centres), bad=False)
    whole = mvs.contributing_parallax_deg(pts, centres, views)
    monkeypatch.setattr(mvs, "_PARALLAX_CHUNK_BYTES", 1)     # one row a chunk
    tiny = mvs.contributing_parallax_deg(pts, centres, views)
    assert np.array_equal(np.isnan(whole), np.isnan(tiny))
    ok = np.isfinite(whole)
    assert np.allclose(whole[ok], tiny[ok])


def test_visibility_reader_round_trip(tmp_path):
    rng = np.random.default_rng(3)
    views = _ragged(rng, 400, 50, bad=False)
    path = tmp_path / "fused.ply.vis"
    with open(path, "wb") as fh:
        fh.write(np.uint64(len(views)).tobytes())
        for v in views:
            fh.write(np.uint32(len(v)).tobytes())
            fh.write(v.astype("<u4").tobytes())
    counts, flat, offsets = mvs._read_visibility_csr(path, len(views))
    assert list(counts) == [len(v) for v in views]
    assert all(np.array_equal(a, b) for a, b in zip(mvs.csr_rows(flat, offsets), views))
    # Wrong point count or a truncated file: refuse rather than misattribute.
    assert mvs._read_visibility_csr(path, len(views) + 1)[0] is None
    path.write_bytes(path.read_bytes()[:-4])
    assert mvs._read_visibility_csr(path, len(views))[0] is None


def test_translate_csr_drops_out_of_range_like_the_ragged_form():
    rng = np.random.default_rng(4)
    views = _ragged(rng, 300, 20)
    table = rng.permutation(20).astype(np.int32) + 100
    ref = [table[v[v < len(table)]] for v in views]
    flat, off = mvs.translate_csr(*mvs.ragged_to_csr(views), table)
    assert all(np.array_equal(a, b) for a, b in zip(mvs.csr_rows(flat, off), ref))


def _dense_obs_reference(recon, cloud, dense_vis, dense_points, voxel,
                         cameras_enu, sel):
    from scipy.spatial import cKDTree
    d, nn = cKDTree(dense_points).query(cloud.points)
    rows = np.flatnonzero(d <= float(voxel) * np.sqrt(3.0))
    sel_arr = np.asarray(sel, np.int32)
    cam_of_frame = {int(c["frame_index"]): c for c in cameras_enu}
    K = np.asarray(recon.K, float)
    pt, fr, uv = [], [], []
    for row in rows:
        p = cloud.points[row]
        for f in dense_vis[int(nn[row])]:
            k = int(f)
            if k >= len(sel_arr):
                continue
            cam = cam_of_frame.get(int(sel_arr[k]))
            if cam is None:
                continue
            c = np.asarray(cam["R"], float) @ (p - np.asarray(cam["C"], float))
            if c[2] <= 1e-6:
                continue
            pt.append(int(row)); fr.append(int(f))
            uv.append((K[0, 0] * c[0] / c[2] + K[0, 2], K[1, 1] * c[1] / c[2] + K[1, 2]))
    return (np.asarray(pt, np.int32), np.asarray(fr, np.int32),
            np.asarray(uv, np.float32))


class _Cloud:
    def __init__(self, p):
        self.points = p

    def __len__(self):
        return len(self.points)


def test_dense_observations_match_per_pair_reference():
    rng = np.random.default_rng(5)
    n_kf = 10
    sel = list(range(0, 10 * n_kf, 10))                 # decoded frame per keyframe
    # Nadir cameras above the scene, one with no registered pose, one looking up.
    cams = []
    for k in range(n_kf):
        if k == 3:
            continue
        R = np.diag([1.0, -1.0, -1.0]) if k != 7 else np.eye(3)
        cams.append({"frame_index": sel[k], "C": [k * 5.0, 0, 60.0], "R": R.tolist()})
    dense = rng.normal(0, 15, (2000, 3)) * [1, 1, 0.1]
    vis = _ragged(rng, len(dense), n_kf)                # includes out-of-range
    cloud = _Cloud(dense[rng.choice(len(dense), 800, replace=False)]
                   + rng.normal(0, 0.02, (800, 3)))
    recon = SimpleNamespace(K=np.array([[500.0, 0, 320], [0, 500.0, 240], [0, 0, 1]]))
    ref = _dense_obs_reference(recon, cloud, vis, dense, 0.15, cams, sel)
    got = pipeline._dense_observations(recon, cloud, 0, mvs.ragged_to_csr(vis),
                                       dense, 0.15, cams, sel)
    assert len(ref[0]) > 100
    assert np.array_equal(ref[0], got[0]) and np.array_equal(ref[1], got[1])
    assert np.allclose(ref[2], got[2])


def test_run_colmap_rejects_unsupported_settings(tmp_path):
    if mvs.colmap_executable() is None:
        pytest.skip("no colmap executable")
    for kw in ({"window_step": 3}, {"num_src_images": 0}, {"num_iterations": 1.5}):
        with pytest.raises(ValueError):
            mvs.run_colmap(tmp_path, **kw)


def test_limit_source_images_rewrites_every_reference(tmp_path):
    st = tmp_path / "stereo"
    st.mkdir()
    (st / "patch-match.cfg").write_text("0001.jpg\n__auto__, 20\n0000.jpg\n__auto__, 20\n")
    mvs._limit_source_images(tmp_path, 12)
    assert (st / "patch-match.cfg").read_text() == \
        "0001.jpg\n__auto__, 12\n0000.jpg\n__auto__, 12\n"


def test_release_gpu_models_drops_the_cached_matcher():
    from drishti_recon import refinement
    refinement.RefinementEngine._xfer = object()
    refinement._DETECT_CACHE["k"] = 1
    refinement.release_gpu_models()
    assert refinement.RefinementEngine._xfer is None
    assert not refinement._DETECT_CACHE
