"""Pointmap -> 3D Gaussian initialisation (the SuGaR handshake).

The failure mode this guards is silent: 3DGS applies exp() to scale and
sigmoid() to opacity on load, so storing post-activation values produces a
file that loads fine, holds plausible-looking numbers, and renders as fog or
nothing at all.
"""
import numpy as np
import pytest

from drishti_recon import gaussians as G


def plane(n=1500, seed=0, z=0.0):
    rng = np.random.default_rng(seed)
    p = np.c_[rng.uniform(-5, 5, n), rng.uniform(-5, 5, n), np.full(n, z)]
    c = rng.integers(0, 256, (n, 3), dtype=np.uint8)
    return p, c


class TestColour:
    def test_round_trips_through_sh(self):
        _, c = plane()
        back = G.sh_dc_to_rgb(G.rgb_to_sh_dc(c))
        assert np.abs(back.astype(int) - c.astype(int)).max() <= 1

    def test_mid_grey_maps_near_zero(self):
        dc = G.rgb_to_sh_dc(np.array([[128, 128, 128]], np.uint8))
        assert np.abs(dc).max() < 0.02

    def test_higher_bands_are_zero(self):
        p, c = plane()
        g = G.from_pointmap(p, c)
        assert g["f_rest"].shape[1] == 3 * ((3 + 1) ** 2 - 1) == 45
        assert not g["f_rest"].any()


class TestPreActivation:
    def test_scale_is_stored_as_log(self):
        p, c = plane()
        g = G.from_pointmap(p, c)
        # exp() of the stored value must be a plausible metric size
        s = np.exp(g["scaling"])
        assert s.min() > 0
        assert 0.01 < np.median(s[:, 0]) < 2.0     # near neighbour spacing
        # and a raw (post-activation) store would have been positive-only;
        # log of sub-metre spacing is negative, which is the tell
        assert g["scaling"][:, 0].mean() < 0

    def test_opacity_is_stored_as_logit(self):
        p, c = plane()
        conf = np.linspace(0, 1, len(p))
        g = G.from_pointmap(p, c, conf=conf)
        op = 1.0 / (1.0 + np.exp(-g["opacity"]))
        assert 0.05 < op.min() < 0.2                # floor, not zero
        assert op.max() < 1.0
        assert np.all(np.diff(op.ravel()) >= -1e-9)  # monotone in confidence

    def test_low_confidence_never_initialises_invisible(self):
        """Opacity 0 gets no gradient, so a low-confidence point could never
        recover. The floor exists to prevent that."""
        p, c = plane()
        g = G.from_pointmap(p, c, conf=np.zeros(len(p)))
        op = 1.0 / (1.0 + np.exp(-g["opacity"]))
        assert op.min() > 0.05


class TestGeometry:
    def test_normals_follow_a_plane(self):
        p, c = plane()
        g = G.from_pointmap(p, c)
        assert np.median(np.abs(g["normals"][:, 2])) > 0.99

    def test_gaussians_are_flattened_along_the_normal(self):
        p, c = plane()
        g = G.from_pointmap(p, c, flatten=0.1)
        s = np.exp(g["scaling"])
        assert np.median(s[:, 2]) < 0.2 * np.median(s[:, 0])

    def test_scale_tracks_point_spacing(self):
        sparse, c1 = plane(n=400)
        dense, c2 = plane(n=4000, seed=1)
        s_sparse = np.exp(G.from_pointmap(sparse, c1)["scaling"])[:, 0]
        s_dense = np.exp(G.from_pointmap(dense, c2)["scaling"])[:, 0]
        assert np.median(s_sparse) > 2.0 * np.median(s_dense)

    def test_rotation_is_unit_quaternion(self):
        rng = np.random.default_rng(3)
        p = rng.normal(size=(800, 3)); c = rng.integers(0, 256, (800, 3), np.uint8)
        q = G.from_pointmap(p, c)["rotation"]
        assert np.allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-6)

    def test_quaternion_actually_rotates_z_onto_the_normal(self):
        n = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
        q = G.quat_from_normal(n)
        for qi, ni in zip(q, n):
            w, x, y, z = qi
            R = np.array([
                [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
                [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
                [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)]])
            assert np.allclose(R @ [0, 0, 1], ni, atol=1e-6)

    def test_duplicate_points_do_not_produce_infinite_scale(self):
        p = np.zeros((50, 3)); c = np.full((50, 3), 128, np.uint8)
        g = G.from_pointmap(p, c)
        assert np.isfinite(g["scaling"]).all()


class TestPly:
    def test_written_file_has_the_3dgs_layout(self, tmp_path):
        p, c = plane(n=300)
        g = G.from_pointmap(p, c)
        path = G.write_ply(tmp_path / "pc.ply", g)
        raw = open(path, "rb").read()
        head = raw[:raw.index(b"end_header")].decode()
        assert "format binary_little_endian" in head
        assert "element vertex 300" in head
        for nm in ("x", "f_dc_0", "f_rest_44", "opacity", "scale_2", "rot_3"):
            assert f"property float {nm}\n" in head
        n_props = head.count("property float")
        assert n_props == 3 + 3 + 3 + 45 + 1 + 3 + 4 == 62

    def test_payload_size_matches_the_header(self, tmp_path):
        p, c = plane(n=300)
        path = G.write_ply(tmp_path / "pc.ply", G.from_pointmap(p, c))
        raw = open(path, "rb").read()
        body = raw[raw.index(b"end_header") + len(b"end_header\n"):]
        assert len(body) == 300 * 62 * 4

    def test_values_survive_the_round_trip(self, tmp_path):
        p, c = plane(n=200)
        g = G.from_pointmap(p, c)
        path = G.write_ply(tmp_path / "pc.ply", g)
        raw = open(path, "rb").read()
        body = raw[raw.index(b"end_header") + len(b"end_header\n"):]
        arr = np.frombuffer(body, np.float32).reshape(200, 62)
        # layout: xyz 0-2, normals 3-5, f_dc 6-8, f_rest 9-53,
        # opacity 54, scale 55-57, rot 58-61
        assert np.allclose(arr[:, :3], g["xyz"], atol=1e-4)
        assert np.allclose(arr[:, 54], g["opacity"][:, 0], atol=1e-5)
        assert np.allclose(arr[:, 55:58], g["scaling"], atol=1e-5)
        assert np.allclose(arr[:, 58:62], g["rotation"], atol=1e-5)
