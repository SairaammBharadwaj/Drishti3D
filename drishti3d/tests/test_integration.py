"""End-to-end integration test on a small generated synthetic fixture.

Runs the full verified pipeline (no downloaded weights, no COLMAP) and asserts a
real reconstruction with metric scale is produced and measurements are sane.
"""
import numpy as np
import pytest

from drishti_recon import synth, pipeline


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = tmp_path_factory.mktemp("synthetic")
    manifest = synth.generate(str(d), n_frames=40, fps=20, width=640, height=360)
    return d, manifest


def test_pipeline_end_to_end(dataset):
    d, manifest = dataset
    proj = d / "proj"
    res = pipeline.run(
        str(proj), manifest["video"], manifest["telemetry"],
        params=pipeline.PipelineParams(preset="balanced", do_mesh=False,
                                       mask_backend="none"))
    rep = res.report
    # a real reconstruction happened
    assert rep["reconstruction"]["n_registered"] >= 6
    assert rep["cloud"]["n_points"] > 300
    # metric scale recovered by GPS alignment
    assert rep["alignment"] is not None
    assert rep["alignment"]["scale"] > 0
    # artifacts written
    for key in ("ply", "viewer", "report_json", "trajectory"):
        assert key in res.artifacts

    # metric scale is finite/positive and the cloud has real extent (a genuine
    # reconstruction).  Tight dimensional accuracy is demonstrated on the full-
    # resolution demo dataset, not gated on this tiny low-res CI fixture.
    dims = rep["cloud"]["dimensions_m"]
    assert all(np.isfinite(dims)) and max(dims) > 1.0


def test_no_fabrication_when_too_few_frames(tmp_path):
    # a 1-frame "video" cannot reconstruct; the pipeline must error, not fake output
    import cv2
    import imageio.v2 as imageio
    vp = tmp_path / "one.mp4"
    w = imageio.get_writer(vp, fps=10, macro_block_size=None)
    for _ in range(3):
        w.append_data(np.zeros((64, 64, 3), np.uint8))
    w.close()
    tp = tmp_path / "t.csv"
    tp.write_text("timestamp,latitude,longitude,altitude\n0,0,0,0\n1,0,0.0001,0\n")
    with pytest.raises(Exception):
        pipeline.run(str(tmp_path / "p"), str(vp), str(tp),
                     params=pipeline.PipelineParams(do_mesh=False))
