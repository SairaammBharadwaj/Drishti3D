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


def test_dense_uncertainty_shrinks_with_agreeing_views():
    centres = np.array([[0.0, 0.0, 0.0]])
    p = np.array([[0.0, 20.0, 0.0]])
    two = mvs.depth_uncertainty(p, centres, np.array([2]), sigma_px=1.0,
                                focal=900.0)[0]
    eight = mvs.depth_uncertainty(p, centres, np.array([8]), sigma_px=1.0,
                                  focal=900.0)[0]
    assert eight < two
    assert eight == pytest.approx(two / 2.0, rel=1e-6)


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
    assert mvs._read_visibility(tmp_path / "nope.vis", 10) is None
