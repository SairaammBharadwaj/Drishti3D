"""Residual distortion refinement recovers a known small lens error (DEC-044).

A calibration that misses ~1 px of radial distortion bent MARS-LVIG surfaces
into a bowl. The refinement must recover such a residual with focal length and
principal point untouched, and must leave non-pinhole cameras alone.
"""
from __future__ import annotations

import numpy as np
import pytest

pycolmap = pytest.importorskip("pycolmap")

from drishti_recon import colmap_adapter                 # noqa: E402

TRUE = [-0.003, 0.004, 0.0002, -0.0003]                  # k1, k2, p1, p2


def _scene(model="OPENCV"):
    o = pycolmap.SyntheticDatasetOptions()
    o.num_rigs = 1
    o.num_cameras_per_rig = 1
    o.num_frames_per_rig = 12
    o.num_points3D = 400
    o.camera_width, o.camera_height = 1600, 1339
    o.camera_model_id = pycolmap.CameraModelId.OPENCV
    o.camera_params = [948.0, 947.0, 770.0, 684.0, *TRUE]
    rec = pycolmap.synthesize_dataset(o)
    if model == "PINHOLE":
        # The calibration "missed" the distortion: same fx, fy, cx, cy.
        for cid, cam in list(rec.cameras.items()):
            fx, fy, cx, cy = [float(v) for v in cam.params[:4]]
            rec.cameras[cid] = pycolmap.Camera(model="PINHOLE", width=cam.width,
                                               height=cam.height,
                                               params=[fx, fy, cx, cy], camera_id=cid)
    return rec


def test_recovers_a_known_residual_distortion():
    rec = _scene("PINHOLE")
    rep = colmap_adapter._refine_residual_distortion(pycolmap, rec)
    assert rep is not None and rep["applied"], rep
    (k,) = rep["k1_k2_p1_p2"].values()
    assert np.allclose(k[:2], TRUE[:2], atol=5e-4), k
    cam = next(iter(rec.cameras.values()))
    assert np.allclose(cam.params[:4], [948.0, 947.0, 770.0, 684.0])   # focal/pp fixed


def test_leaves_non_pinhole_cameras_alone():
    rec = _scene("OPENCV")
    before = [float(v) for v in next(iter(rec.cameras.values())).params]
    assert colmap_adapter._refine_residual_distortion(pycolmap, rec) is None
    assert [float(v) for v in next(iter(rec.cameras.values())).params] == before
