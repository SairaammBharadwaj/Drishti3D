"""Candidate-view evidence assembled from stored artifacts (plan F3 groundwork)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from drishti_recon.evidence import ReconstructionEvidence


def _write(art, cams, *, K=True, alignment=None):
    art.mkdir(parents=True, exist_ok=True)
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[900.0, 0, 640.0], [0, 900.0, 360.0], [0, 0, 1.0]] if K else None,
        "image_size": [1280, 720] if K else None,
        "cameras_enu": cams}))
    (art / "manifest.json").write_text(json.dumps({
        "version": "0.1.0", "created": 1.0, "video_sha256": "b" * 64,
        "alignment": alignment}))
    return ReconstructionEvidence.load(art)


def _arc(n=9, radius=10.0, target=(0.0, 0.0, 0.0)):
    """Cameras on an arc around a target, all looking at it."""
    cams = []
    t = np.asarray(target, float)
    for k, a in enumerate(np.linspace(-0.9, 0.9, n)):
        C = t + np.array([radius * np.sin(a), -radius * np.cos(a), 3.0])
        fwd = t - C
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        cams.append({"frame_index": k * 3, "C": C.tolist(),
                     "R": np.stack([right, down, fwd]).tolist()})
    return cams


def test_relative_scale_uncertainty_is_divided_by_the_scale_factor(tmp_path):
    """`scale_sigma` is absolute, in the reconstruction's arbitrary units.

    Reporting it raw made a 1.1% scale error read as 19% on one engine and 1.2%
    on another, purely because the two solvers chose different internal units.
    """
    rec = _write(tmp_path / "a", _arc(),
                 alignment={"scale_source": "gps", "scale": 16.95,
                            "scale_sigma": 0.1943})
    assert rec.scale_source == "gps"
    assert rec.scale_sigma_rel == pytest.approx(0.1943 / 16.95, rel=1e-6)


def test_missing_alignment_leaves_scale_unknown_not_zero(tmp_path):
    rec = _write(tmp_path / "b", _arc(), alignment=None)
    assert rec.scale_source == "none"
    assert not np.isfinite(rec.scale_sigma_rel)


def test_visible_cameras_needs_intrinsics_and_returns_nothing_without_them(
        tmp_path):
    """No frustum test is possible without K; an empty answer beats a guess."""
    rec = _write(tmp_path / "c", [{"frame_index": 0, "C": [0, -10, 3]}],
                 K=False)
    assert len(rec.visible_cameras([0, 0, 0])) == 0


def test_parallax_is_measured_between_rays_not_counted_in_cameras(tmp_path):
    """A point on an arc has real parallax; one straight ahead of a line has none."""
    rec = _write(tmp_path / "d", _arc(n=9, radius=10.0))
    wide = rec.max_ray_separation_deg([0.0, 0.0, 0.0])
    assert wide > 40.0

    # Cameras strung along one short line, all looking the same way at a point
    # 400 m off. The baseline is 2 m against a 400 m range, so every ray is
    # essentially the same direction.
    fwd = np.array([0.0, 1.0, 0.0])
    right = np.array([1.0, 0.0, 0.0])
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd]).tolist()
    line = []
    for k, x in enumerate(np.linspace(-1.0, 1.0, 9)):
        line.append({"frame_index": k, "C": [x, -400.0, 0.0], "R": R})
    rec2 = _write(tmp_path / "e", line)
    assert len(rec2.visible_cameras([0.0, 0.0, 0.0])) == 9
    assert rec2.max_ray_separation_deg([0.0, 0.0, 0.0]) < 1.0


def test_evidence_is_stamped_as_an_upper_bound(tmp_path):
    rec = _write(tmp_path / "f", _arc(),
                 alignment={"scale_source": "gps", "scale": 10.0,
                            "scale_sigma": 0.05})
    ev = rec.for_points([[0.0, 0.0, 0.0]], provenances=[0])
    assert ev.view_support_basis == "frustum_upper_bound"
    assert ev.endpoints_observed is True
    assert ev.n_supporting_views > 2


def test_the_weakest_endpoint_sets_the_support(tmp_path):
    """A width is no better supported than its worse-seen end."""
    rec = _write(tmp_path / "g", _arc(n=9, radius=10.0))
    seen = [0.0, 0.0, 0.0]
    behind = [0.0, -600.0, 0.0]           # behind every camera on the arc
    ev = rec.for_points([seen, behind], provenances=[0, 0])
    assert ev.n_supporting_views == 0
    assert ev.max_ray_separation_deg == 0.0


def test_inferred_geometry_is_flagged(tmp_path):
    rec = _write(tmp_path / "h", _arc())
    ev = rec.for_points([[0.0, 0.0, 0.0]], provenances=[2])   # AI_ASSISTED
    assert ev.touches_inferred is True
    assert ev.endpoints_observed is False


def test_supporting_frames_are_ranked_for_diversity_not_proximity(tmp_path):
    rec = _write(tmp_path / "i", _arc(n=11, radius=10.0))
    frames = rec.supporting_frames([0.0, 0.0, 0.0], limit=4)
    assert len(frames) == 4
    picked = [f["camera_index"] for f in frames]
    assert len(set(picked)) == 4
    # A diversity ranking must not return four consecutive neighbours.
    assert max(picked) - min(picked) > 3


# --------------------------------------------------------------------------- #
# Observation lineage: support from the measurements that made the point
# --------------------------------------------------------------------------- #
def _with_lineage(tmp_path, cams, points, obs, alignment=None):
    art = tmp_path
    art.mkdir(parents=True, exist_ok=True)
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": [[900.0, 0, 640.0], [0, 900.0, 360.0], [0, 0, 1.0]],
        "image_size": [1280, 720], "cameras_enu": cams}))
    (art / "manifest.json").write_text(json.dumps({
        "version": "0.1.0", "created": 1.0, "video_sha256": "c" * 64,
        "alignment": alignment}))
    # Pad with a sparse shell so the cloud has a meaningful point spacing; the
    # first rows stay the points under test, which is what obs indexes.
    pts = np.asarray(points, float)
    shell = np.random.default_rng(3).uniform(-1.0, 1.0, (60, 3)) * 0.4 + 3.0
    np.savez_compressed(art / "cloud.npz", points=np.vstack([pts, shell]))
    np.savez_compressed(
        art / "observations.npz",
        point_index=np.asarray(obs["point_index"], np.int32),
        keyframe_index=np.asarray(obs["keyframe_index"], np.int32),
        frame_index=np.asarray(obs["frame_index"], np.int32),
        uv=np.asarray(obs["uv"], np.float32),
        image_width=np.array([1280], np.int32),
        image_height=np.array([720], np.int32))
    return ReconstructionEvidence.load(art)


def test_lineage_parallax_is_measured_not_available(tmp_path):
    """The whole point of lineage: two of nine cameras measured this point.

    A frustum test counts all nine and reports the arc's full spread. The
    measurements came from two adjacent cameras, so the parallax that actually
    constrained the depth is a fraction of that. Accepting a measurement on the
    larger figure would accept depth the capture never established.
    """
    cams = _arc(n=9, radius=10.0)
    pt = [0.0, 0.0, 0.0]
    rec = _with_lineage(tmp_path / "lin", cams, [pt], {
        "point_index": [0, 0],
        "keyframe_index": [0, 3],          # solver numbering, deliberately unused
        "frame_index": [cams[3]["frame_index"], cams[4]["frame_index"]],
        "uv": [[640.0, 360.0], [641.0, 359.0]]})
    assert rec.has_lineage
    measured = rec.measured_ray_separation_deg(pt)
    available = rec.max_ray_separation_deg(pt)
    assert len(rec.visible_cameras(pt)) == 9
    assert 0.0 < measured < available
    assert available > 40.0


def test_lineage_lifts_the_frustum_stamp(tmp_path):
    cams = _arc(n=9, radius=10.0)
    pt = [0.0, 0.0, 0.0]
    rec = _with_lineage(tmp_path / "lin2", cams, [pt], {
        "point_index": [0, 0, 0],
        "keyframe_index": [0, 1, 2],
        "frame_index": [cams[0]["frame_index"], cams[4]["frame_index"],
                        cams[8]["frame_index"]],
        "uv": [[10.0, 10.0], [640.0, 360.0], [1270.0, 700.0]]})
    ev = rec.for_points([pt], provenances=[0])
    assert ev.view_support_basis == "triangulated_observations"
    assert ev.n_supporting_views == 3
    assert ev.max_ray_separation_deg > 40.0


def test_frame_numbering_is_not_guessed_between(tmp_path):
    """Observations are matched to cameras by decoded frame index, not keyframe.

    The two numberings differ whenever keyframe selection decimates, and keying
    on the wrong one silently finds no camera at all -- which reads as zero
    parallax on a point that was measured from a wide baseline.
    """
    cams = _arc(n=9, radius=10.0)          # frame_index = 0, 3, 6, ... 24
    pt = [0.0, 0.0, 0.0]
    rec = _with_lineage(tmp_path / "lin3", cams, [pt], {
        "point_index": [0, 0],
        "keyframe_index": [0, 8],          # would resolve to cams[0] and cams[2]
        "frame_index": [cams[0]["frame_index"], cams[8]["frame_index"]],
        "uv": [[10.0, 10.0], [1270.0, 700.0]]})
    # Resolved via frame_index, the two measurements are the arc's extremes.
    assert rec.measured_ray_separation_deg(pt) == pytest.approx(
        rec.max_ray_separation_deg(pt), rel=1e-6)


def test_a_selection_far_from_any_point_inherits_no_lineage(tmp_path):
    """Borrowing a distant point's measurements would misattribute evidence."""
    cams = _arc(n=9, radius=10.0)
    cloud = [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.2, 0.0, 0.0]]
    rec = _with_lineage(tmp_path / "lin4", cams, cloud, {
        "point_index": [0, 0], "keyframe_index": [0, 1],
        "frame_index": [cams[0]["frame_index"], cams[8]["frame_index"]],
        "uv": [[10.0, 10.0], [1270.0, 700.0]]})
    assert rec.lineage_point([0.0, 0.0, 0.0]) == 0
    assert rec.lineage_point([50.0, 0.0, 0.0]) == -1
    assert len(rec.observations_of([50.0, 0.0, 0.0])["frame_index"]) == 0


def test_one_endpoint_without_lineage_downgrades_the_whole_measurement(tmp_path):
    """A width is frustum-derived if either end is; averaging would hide that."""
    cams = _arc(n=9, radius=10.0)
    rec = _with_lineage(tmp_path / "lin5", cams, [[0.0, 0.0, 0.0]], {
        "point_index": [0, 0], "keyframe_index": [0, 1],
        "frame_index": [cams[0]["frame_index"], cams[8]["frame_index"]],
        "uv": [[10.0, 10.0], [1270.0, 700.0]]})
    ev = rec.for_points([[0.0, 0.0, 0.0], [40.0, 0.0, 0.0]],
                        provenances=[0, 0])
    assert ev.view_support_basis == "frustum_upper_bound"


def test_supporting_frames_carry_the_measured_pixel(tmp_path):
    cams = _arc(n=9, radius=10.0)
    pt = [0.0, 0.0, 0.0]
    rec = _with_lineage(tmp_path / "lin6", cams, [pt], {
        "point_index": [0, 0], "keyframe_index": [0, 1],
        "frame_index": [cams[0]["frame_index"], cams[8]["frame_index"]],
        "uv": [[11.0, 12.0], [1270.0, 700.0]]})
    frames = rec.supporting_frames(pt)
    assert len(frames) == 2, "only the frames that measured it"
    assert all(f["measured"] for f in frames)
    pixels = {f["frame_index"]: f["pixel"] for f in frames}
    assert pixels[cams[0]["frame_index"]] == (11.0, 12.0)
