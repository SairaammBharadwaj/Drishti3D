"""Dense multi-view stereo: observed geometry, and the line it must not cross.

The point of these tests is the distinction the viewer makes easy to lose: a
dense cloud produced by stereo is *measured*, one produced by a depth model is
*inferred*, and only the first may be measured against.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon import mvs
from drishti_recon.pipeline import PipelineParams


def test_available_reports_why_dense_cannot_run():
    """A bare `None` here sent someone hunting; the reason is the useful part."""
    info = mvs.available()["colmap"]
    assert set(info) >= {"executable", "available", "detail", "setup"}
    assert info["detail"]
    if not info["available"]:
        assert "CUDA" in info["setup"]


def test_run_colmap_without_an_executable_says_how_to_get_one(tmp_path,
                                                              monkeypatch):
    monkeypatch.setattr(mvs, "colmap_executable", lambda: None)
    with pytest.raises(RuntimeError, match="CUDA"):
        mvs.run_colmap(tmp_path)


def test_run_colmap_refuses_a_directory_that_is_not_a_workspace(tmp_path,
                                                                monkeypatch):
    monkeypatch.setattr(mvs, "colmap_executable", lambda: "/usr/bin/true")
    with pytest.raises(RuntimeError, match="not a COLMAP workspace"):
        mvs.run_colmap(tmp_path)


def test_dense_uncertainty_grows_with_range():
    """A stereo point 40 m out is less certain than one 10 m out."""
    centres = np.array([[0.0, 0.0, 0.0]])
    near = np.array([[0.0, 10.0, 0.0]])
    far = np.array([[0.0, 40.0, 0.0]])
    s_near = mvs.depth_uncertainty(near, centres, np.array([4]),
                                   sigma_px=1.0, focal=900.0)[0]
    s_far = mvs.depth_uncertainty(far, centres, np.array([4]),
                                  sigma_px=1.0, focal=900.0)[0]
    assert s_far == pytest.approx(4 * s_near, rel=1e-6)


def test_dense_uncertainty_shrinks_with_agreeing_views_up_to_the_cap():
    """More views help, but only while they are still independent looks.

    Two to four halves the error. Past MAX_INDEPENDENT_VIEWS it stops, because
    fusion's extra supporting images are consecutive frames of the same pass
    seeing the same surface from nearly the same place.
    """
    centres = np.array([[0.0, 0.0, 0.0]])
    p = np.array([[0.0, 20.0, 0.0]])
    two = mvs.depth_uncertainty(p, centres, np.array([2]), sigma_px=1.0,
                                focal=900.0)[0]
    four = mvs.depth_uncertainty(p, centres, np.array([4]), sigma_px=1.0,
                                 focal=900.0)[0]
    assert four < two
    assert four == pytest.approx(two / np.sqrt(2.0), rel=1e-6)


def test_dense_uncertainty_never_assumes_fewer_than_two_views():
    """A fused point rests on at least two images by construction."""
    centres = np.array([[0.0, 0.0, 0.0]])
    p = np.array([[0.0, 20.0, 0.0]])
    one = mvs.depth_uncertainty(p, centres, np.array([1]), sigma_px=1.0,
                                focal=900.0)[0]
    two = mvs.depth_uncertainty(p, centres, np.array([2]), sigma_px=1.0,
                                focal=900.0)[0]
    assert one == pytest.approx(two)


def test_dense_uncertainty_handles_an_empty_cloud():
    assert len(mvs.depth_uncertainty(np.zeros((0, 3)), np.zeros((1, 3)), None,
                                     sigma_px=1.0, focal=900.0)) == 0


def test_the_two_densify_paths_are_distinct_options():
    """`mvs` is observed and measurable; `depth` is inferred and is not."""
    assert PipelineParams().densify == "none"
    assert PipelineParams(densify="mvs").densify == "mvs"
    assert PipelineParams(densify="depth").densify == "depth"


def test_ascii_ply_round_trip(tmp_path):
    path = tmp_path / "fused.ply"
    path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 2\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n1 2 3 10 20 30\n4 5 6 40 50 60\n")
    xyz, rgb = mvs._read_ply(path)
    assert xyz.shape == (2, 3) and rgb.shape == (2, 3)
    assert np.allclose(xyz[1], [4, 5, 6])
    assert tuple(rgb[0]) == (10, 20, 30)


def test_missing_visibility_sidecar_is_not_an_error(tmp_path):
    counts, images = mvs._read_visibility(tmp_path / "nope.vis", 10)
    assert counts is None and images is None


def test_visibility_round_trip_keeps_which_images_saw_each_point(tmp_path):
    """The image list, not just the count, is what gives a dense point lineage."""
    import struct
    path = tmp_path / "fused.ply.vis"
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", 2))
        fh.write(struct.pack("<I", 3) + struct.pack("<3I", 4, 7, 9))
        fh.write(struct.pack("<I", 2) + struct.pack("<2I", 1, 4))
    counts, images = mvs._read_visibility(path, 2)
    assert list(counts) == [3, 2]
    assert list(images[0]) == [4, 7, 9]
    assert list(images[1]) == [1, 4]


def test_visibility_is_rejected_when_it_does_not_match_the_cloud(tmp_path):
    """A sidecar for a different fusion would attribute points to wrong images."""
    import struct
    path = tmp_path / "fused.ply.vis"
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", 5))
    counts, images = mvs._read_visibility(path, 2)
    assert counts is None and images is None


# --- the floor: a dense point cannot beat the model it rides on ------------ #
def test_the_floor_dominates_when_stereo_looks_implausibly_good():
    """Measured: without it, dense points came out 7x better than the sparse
    geometry they were triangulated from.

    The stereo term alone reported a 5 mm median on a model good to 36 mm.
    Cameras are known only to the bundle adjustment's accuracy, so nothing
    triangulated from them can be better known than that.
    """
    centres = np.array([[0.0, 0.0, 0.0]])
    p = np.array([[0.0, 20.0, 0.0]])
    bare = mvs.depth_uncertainty(p, centres, np.array([5]),
                                 sigma_px=1.0, focal=1536.0)[0]
    floored = mvs.depth_uncertainty(p, centres, np.array([5]),
                                    sigma_px=1.0, focal=1536.0,
                                    floor=0.0364)[0]
    assert bare < 0.01, "the stereo term alone is millimetres"
    assert floored >= 0.0364
    assert floored == pytest.approx(np.hypot(bare, 0.0364))


def test_views_stop_helping_once_they_stop_being_independent():
    """Fusion's supporting images are consecutive frames of one pass."""
    centres = np.array([[0.0, 0.0, 0.0]])
    p = np.array([[0.0, 20.0, 0.0]])
    four = mvs.depth_uncertainty(p, centres, np.array([4]), sigma_px=1.0,
                                 focal=1536.0)[0]
    twenty = mvs.depth_uncertainty(p, centres, np.array([20]), sigma_px=1.0,
                                   focal=1536.0)[0]
    assert twenty == pytest.approx(four), "beyond the cap, more views buy nothing"


def test_dense_pixel_sigma_is_not_the_sparse_reprojection_residual():
    """Patch-match matches a window; SIFT localises a corner. Different things."""
    assert mvs.DENSE_PIXEL_SIGMA >= 1.0
