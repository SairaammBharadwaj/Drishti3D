"""C05: dense contributor records must not read as measured feature pixels.

The review's finding: `_dense_observations` projects a surviving point into the
cameras that fused it, writes the result into the same `uv` array sparse
feature measurements use, and nothing downstream can tell them apart -- so
"99.9% project inside the image", an indexing check, could be read as evidence
that a pixel was measured there.
"""
import numpy as np
import pytest

from drishti_recon import pipeline
from drishti_recon.evidence import ReconstructionEvidence


def test_kind_codes_are_distinct_and_named():
    assert pipeline.OBS_SPARSE_FEATURE != pipeline.OBS_DENSE_FUSION_CONTRIBUTOR
    names = pipeline.OBSERVATION_KIND_NAMES
    assert names[pipeline.OBS_SPARSE_FEATURE] == "sparse_feature_observation"
    assert names[pipeline.OBS_DENSE_FUSION_CONTRIBUTOR] == "dense_fusion_contributor"


def _artifacts(tmp_path, kinds=None):
    import json
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[500, 0, 320], [0, 500, 240], [0, 0, 1]],
        "image_size": [640, 480],
        "cameras_enu": [
            {"frame_index": 0, "C": [0, 0, 10], "R": np.eye(3).tolist()},
            {"frame_index": 1, "C": [5, 0, 10], "R": np.eye(3).tolist()},
            {"frame_index": 2, "C": [10, 0, 10], "R": np.eye(3).tolist()},
        ],
    }))
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    np.savez(art / "cloud.npz", points=pts,
             colors=np.full((2, 3), 200, np.uint8),
             confidence=np.full(2, 0.9), provenance=np.zeros(2, np.int32),
             sigma=np.full(2, 0.01), sigma_major=np.full(2, 0.02))
    obs = {"point_index": np.array([0, 0, 1, 1], np.int32),
           "keyframe_index": np.array([0, 1, 1, 2], np.int32),
           "frame_index": np.array([0, 1, 1, 2], np.int32),
           "uv": np.zeros((4, 2), np.float32),
           "image_width": np.array([640], np.int32),
           "image_height": np.array([480], np.int32)}
    if kinds is not None:
        obs["observation_kind"] = np.asarray(kinds, np.uint8)
    np.savez(art / "observations.npz", **obs)
    return art


def test_kinds_are_reported_per_point(tmp_path):
    art = _artifacts(tmp_path, kinds=[0, 0, 1, 1])
    rec = ReconstructionEvidence.load(art)
    a = rec.observation_kinds_of([0.0, 0.0, 0.0])
    b = rec.observation_kinds_of([1.0, 0.0, 0.0])
    assert a["sparse_feature_observation"] == 2
    assert a["dense_fusion_contributor"] == 0
    assert b["sparse_feature_observation"] == 0
    assert b["dense_fusion_contributor"] == 2
    assert a["kinds_recorded"] is True


def test_mixed_support_is_reported_as_mixed(tmp_path):
    art = _artifacts(tmp_path, kinds=[0, 1, 1, 1])
    rec = ReconstructionEvidence.load(art)
    a = rec.observation_kinds_of([0.0, 0.0, 0.0])
    assert a["sparse_feature_observation"] == 1
    assert a["dense_fusion_contributor"] == 1


def test_older_artifacts_declare_that_they_did_not_record_kinds(tmp_path):
    """Absence must not be silently reported as 'all measured features'."""
    art = _artifacts(tmp_path, kinds=None)
    rec = ReconstructionEvidence.load(art)
    a = rec.observation_kinds_of([0.0, 0.0, 0.0])
    assert a["kinds_recorded"] is False
    assert a["sparse_feature_observation"] == 2      # the honest default
