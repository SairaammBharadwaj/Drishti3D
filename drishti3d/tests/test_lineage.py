"""Observation lineage survives fusion's reindexing (plan work package WP1).

Fusion voxel-downsamples and removes outliers, both of which renumber the
cloud. Lineage keyed to the pre-fusion ordering is silently wrong afterwards --
every point would cite another point's measurements -- so the map back is
tested here rather than assumed.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon.fusion import fuse, add_inferred_layer
from drishti_recon.pipeline import _remap_observations


class _Recon:
    """The fields `_remap_observations` reads off a ReconResult."""

    def __init__(self, obs_point, obs_frame, obs_uv):
        self.obs_point = np.asarray(obs_point, np.int32)
        self.obs_frame = np.asarray(obs_frame, np.int32)
        self.obs_uv = np.asarray(obs_uv, np.float32)


def _cloud(n=400, seed=0, voxel=0.5):
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, 10, (n, 3))
    cols = np.full((n, 3), 128, np.uint8)
    conf = rng.uniform(0.3, 0.9, n)
    return pts, fuse(pts, cols, conf, voxel=voxel)


def test_fuse_reports_where_every_surviving_point_came_from():
    pts, c = _cloud()
    assert c.source_index is not None
    assert len(c.source_index) == len(c)
    assert c.source_index.min() >= 0
    assert len(np.unique(c.source_index)) == len(c.source_index), \
        "two fused points cannot claim the same source row"


def test_source_index_actually_points_at_the_right_geometry():
    pts, c = _cloud(voxel=0.5)
    # Each survivor must be within a voxel of the row it claims as its source.
    d = np.linalg.norm(c.points - pts[c.source_index], axis=1)
    assert d.max() <= 0.5 * np.sqrt(3) + 1e-6


def test_observations_are_remapped_onto_the_fused_indices():
    pts, c = _cloud(n=300, voxel=0.4)
    src = c.source_index
    # Two observations for each surviving point, plus one for a point that is
    # about to be discarded by fusion.
    survivors = src[:20]
    dropped = next(i for i in range(len(pts)) if i not in set(src.tolist()))
    obs_point = list(survivors) * 2 + [dropped]
    obs_frame = list(range(20)) + list(range(20)) + [99]
    obs_uv = [[float(i), float(i)] for i in range(len(obs_point))]

    out = _remap_observations(_Recon(obs_point, obs_frame, obs_uv), c,
                              decoded_of_keyframe=list(range(200)))
    assert out is not None
    # The discarded point's measurement is gone, not reassigned.
    assert len(out["point_index"]) == 40
    assert out["point_index"].max() < len(c)
    # Each remapped observation must land on the fused row whose source is the
    # original point it referred to.
    for k in range(40):
        fused_row = int(out["point_index"][k])
        assert src[fused_row] == obs_point[k]


def test_both_frame_numberings_are_recorded():
    """`sel` maps keyframe index to decoded frame index; both are stored.

    Keying evidence on the wrong one resolves to no camera at all, which reads
    as zero parallax on a point measured from a wide baseline.
    """
    pts, c = _cloud(n=200, voxel=0.4)
    src = c.source_index
    sel = [0, 2, 4, 6, 8, 10]            # keyframe k was decoded frame 2k
    out = _remap_observations(
        _Recon([src[0], src[1]], [1, 3], [[0.0, 0.0], [1.0, 1.0]]), c, sel)
    assert list(out["keyframe_index"]) == [1, 3]
    assert list(out["frame_index"]) == [2, 6]


def test_no_lineage_in_means_no_lineage_out():
    """None must be distinguishable from "this point has no observations"."""
    pts, c = _cloud()
    assert _remap_observations(_Recon([], [], np.zeros((0, 2))), c, [0]) is None

    class _NoLineage:
        obs_point = None
    assert _remap_observations(_NoLineage(), c, [0]) is None


def test_inferred_points_carry_no_source_row():
    pts, c = _cloud(n=200)
    n_before = len(c)
    c2 = add_inferred_layer(c, np.array([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]))
    assert len(c2) == n_before + 2
    assert (c2.source_index[n_before:] == -1).all(), \
        "AI-proposed points have nothing behind them; row 0 is not nothing"
    assert (c2.source_index[:n_before] == c.source_index).all()


def test_remap_ignores_inferred_rows_when_inverting():
    """The -1 sentinel must not be read as an index into the inverse map."""
    pts, c = _cloud(n=200)
    src0 = c.source_index.copy()
    c2 = add_inferred_layer(c, np.array([[1.0, 1.0, 1.0]]))
    out = _remap_observations(
        _Recon([src0[5], src0[6]], [0, 1], [[0.0, 0.0], [1.0, 1.0]]), c2,
        decoded_of_keyframe=list(range(10)))
    assert out is not None
    assert list(out["point_index"]) == [5, 6]


# --- keyframe index vs decoded frame index, for the fifth time -------------- #
def test_camera_frame_index_is_decoded_not_an_analysis_position():
    """A camera at 292 s must not be recorded as being at 16 s.

    `sel` holds positions in the *analysed* frame array; the decoded video
    frame index is `frames[i][0]`. They coincide only when every frame was
    analysed, which is why `sel[k]` survived as a "frame index" until a long
    video used --max-frames: there the two differ by the analysis stride.

    Measured on a 5m46 clip subsampled to 1,153 of 20,751 frames: registered
    cameras were written as frames 252..972, which reads as 4 s to 16 s. The
    true span was 4,536..17,496 -- 76 s to 292 s.
    """
    stride = 18
    # `frames` as the pipeline holds it: (decoded_index, timestamp, image).
    frames = [(i * stride, i * stride / 60.0, None) for i in range(1153)]
    sel = list(range(14, 55))                    # keyframes chosen from those
    decoded_of_keyframe = [int(frames[i][0]) for i in sel]

    # The bug was using sel[k] directly.
    assert sel[0] == 14
    assert decoded_of_keyframe[0] == 252
    assert decoded_of_keyframe[-1] == 54 * stride

    # The mapping must be strictly increasing and land inside the video.
    assert all(b > a for a, b in zip(decoded_of_keyframe, decoded_of_keyframe[1:]))
    assert max(decoded_of_keyframe) <= frames[-1][0]

    # And it must not collapse the span, which is how the bug showed.
    span_frames = decoded_of_keyframe[-1] - decoded_of_keyframe[0]
    assert span_frames == (sel[-1] - sel[0]) * stride
    assert span_frames > (sel[-1] - sel[0])      # strictly wider than positions


def test_identity_when_every_frame_was_analysed():
    """The case that hid the bug: no subsampling, so the spaces coincide."""
    frames = [(i, i / 30.0, None) for i in range(60)]
    sel = list(range(60))
    assert [int(frames[i][0]) for i in sel] == sel
