"""C01/U02: one definition of a measurement, and calibration that survives.

The review's findings: `POST /measurements` computed without scale uncertainty
and persisted a row with no sigma, interval basis, status or artifact identity,
so the same geometry meant different things through different routes; and
`ProcessRequest.intrinsics` silently dropped distortion coefficients.
"""
import numpy as np
import pytest

from app.schemas import Intrinsics, MeasurementOut, ProcessRequest


# --------------------------------------------------------------------------- #
# U02 -- calibration must not lose fields in transit
# --------------------------------------------------------------------------- #
def test_distortion_survives_validation():
    i = Intrinsics(fx=1000, fy=1000, cx=960, cy=540,
                   model="OPENCV", distortion=[-0.1, 0.02, 0.0, 0.0, 0.0])
    assert i.distortion == [-0.1, 0.02, 0.0, 0.0, 0.0]
    assert i.model == "OPENCV"


def test_source_resolution_survives_validation():
    i = Intrinsics(fx=1000, fy=1000, cx=960, cy=540,
                   source_width=1920, source_height=1080)
    assert (i.source_width, i.source_height) == (1920, 1080)


def test_unknown_calibration_fields_are_refused_not_dropped():
    """Silently discarding a field the caller believed was applied is worse
    than refusing it: the operator gets no signal either way."""
    with pytest.raises(Exception):
        Intrinsics(fx=1000, fy=1000, cx=960, cy=540, k1=-0.1)


def test_default_is_an_explicit_pinhole_claim():
    i = Intrinsics(fx=1000, fy=1000, cx=960, cy=540)
    assert i.model == "PINHOLE"
    assert i.distortion == []


def test_process_request_carries_distortion_through():
    r = ProcessRequest(intrinsics=Intrinsics(
        fx=1000, fy=1000, cx=960, cy=540, distortion=[-0.1, 0.02]))
    assert r.intrinsics.distortion == [-0.1, 0.02]


# --------------------------------------------------------------------------- #
# C01 -- both routes must report the same contract
# --------------------------------------------------------------------------- #
def test_measurement_out_exposes_the_trust_fields():
    fields = MeasurementOut.model_fields
    for name in ("sigma", "interval_half_width", "interval_basis",
                 "status", "status_reasons", "artifact_version"):
        assert name in fields, f"MeasurementOut drops {name}"


def test_measurement_out_defaults_are_not_falsely_confident():
    """A missing sigma must read as 'not propagated', never as zero."""
    m = MeasurementOut(id="x", project_id="y", kind="distance", value=1.0,
                       unit="m", points_enu=[[0, 0, 0], [1, 0, 0]],
                       confidence_note="", used_inferred=False, warnings=[],
                       created_at="2026-09-21T00:00:00")
    assert m.sigma is None
    assert m.interval_basis == "uncalibrated_sensitivity"
    assert m.status is None


def test_non_metric_scale_is_not_reported_in_metres(monkeypatch):
    """A reconstruction with no georeferencing has arbitrary scale."""
    from app import results
    monkeypatch.setattr(results, "scale_status",
                        lambda pid: {"scale_source": None,
                                     "scale_sigma_rel": None,
                                     "is_metric": False})
    monkeypatch.setattr(results, "evidence_for", lambda pid: None)
    monkeypatch.setattr(results, "artifact_version", lambda pid: "test@0")

    from drishti_recon.fusion import PointCloud
    from drishti_recon.provenance import Provenance
    xs, ys = np.meshgrid(np.linspace(0, 10, 40), np.linspace(0, 10, 40))
    pts = np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], 1)
    n = len(pts)
    cloud = PointCloud(pts, np.full((n, 3), 200, np.uint8), np.full(n, 0.9),
                       np.full(n, int(Provenance.OBSERVED_HIGH_CONFIDENCE)),
                       None, np.full(n, 0.01), np.full(n, 0.02))

    r = results.compute("a" * 32, cloud, kind="distance",
                        points=[[0, 0, 0], [10, 0, 0]], allow_inferred=False)
    assert r["unit"] == "reconstruction units"
    assert any("not metres" in w or "arbitrary" in w for w in r["warnings"])
    assert r["artifact_version"] == "test@0"


# --------------------------------------------------------------------------- #
# U02 -- calibration resolution must be honoured, not assumed
# --------------------------------------------------------------------------- #
def _K(intr, ow, oh, pw, ph):
    from drishti_recon.pipeline import _resolve_intrinsics
    warns = []
    return _resolve_intrinsics(intr, ow, oh, pw, ph, pw / ow, warns), warns


def test_calibration_at_the_video_resolution_scales_as_before():
    K, warns = _K({"fx": 1000, "fy": 1000, "cx": 960, "cy": 540},
                  1920, 1080, 960, 540)
    assert K[0, 0] == pytest.approx(500.0)
    assert warns == []


def test_calibration_measured_at_another_resolution_is_rescaled():
    """4K calibration, 1080p video, 960-wide processing."""
    K, warns = _K({"fx": 4000, "fy": 4000, "cx": 1920, "cy": 1080,
                   "source_width": 3840, "source_height": 2160},
                  1920, 1080, 960, 540)
    assert K[0, 0] == pytest.approx(1000.0)     # 4000 * 960/3840
    assert any("measured at 3840x2160" in w for w in warns)


def test_mismatched_aspect_ratio_is_flagged_not_silently_scaled():
    K, warns = _K({"fx": 1000, "fy": 1000, "cx": 640, "cy": 640,
                   "source_width": 1280, "source_height": 1280},
                  1920, 1080, 960, 540)
    assert any("aspect ratio" in w for w in warns)


def test_compute_returns_every_field_it_promises(monkeypatch):
    """Each key must come from where that information actually lives.

    Verdict.to_dict() carries the judgement, not the measurement: it has no
    `sigma`, no `evidence`, and names the reason list `reasons`. Reading
    `status_reasons` and `evidence` off it silently produced an empty list and
    an empty dict -- a stored refusal with nothing saying why.
    """
    from app import results
    from drishti_recon.fusion import PointCloud
    from drishti_recon.provenance import Provenance

    monkeypatch.setattr(results, "scale_status",
                        lambda pid: {"scale_source": "gps",
                                     "scale_sigma_rel": 0.01,
                                     "is_metric": True})
    monkeypatch.setattr(results, "evidence_for", lambda pid: None)
    monkeypatch.setattr(results, "artifact_version", lambda pid: "v@1")

    xs, ys = np.meshgrid(np.linspace(0, 10, 40), np.linspace(0, 10, 40))
    pts = np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], 1)
    n = len(pts)
    cloud = PointCloud(pts, np.full((n, 3), 200, np.uint8), np.full(n, 0.9),
                       np.full(n, int(Provenance.OBSERVED_HIGH_CONFIDENCE)),
                       None, np.full(n, 0.01), np.full(n, 0.02))

    r = results.compute("a" * 32, cloud, kind="distance",
                        points=[[0, 0, 0], [10, 0, 0]], allow_inferred=False,
                        tolerance_m=0.05)
    # With no trajectory artifact the endpoints are unverifiable, which is a
    # hard refusal and short-circuits the softer checks -- so the reason here
    # is endpoint_not_observed, and the point is that a reason is present at
    # all rather than the empty list the wrong key produced.
    assert r["status_reasons"], "a refusal with no reasons explains nothing"
    assert "endpoint_not_observed" in r["status_reasons"]
    assert isinstance(r["evidence"], dict) and r["evidence"]
    assert r["evidence"]["endpoints_observed"] is False
    assert r["sigma"] is not None and r["sigma"] > 0
    assert r["status"] == "not_observable"
    assert r["dominant_limitation"] == "endpoint_not_observed"
    assert r["unit"] == "m"


def test_uncalibrated_is_reported_once_the_hard_refusals_clear(monkeypatch):
    """The reason that actually blocks this system, with evidence present."""
    from app import results
    from drishti_recon import questions as qmod

    good = qmod.Evidence(
        n_supporting_views=6, max_ray_separation_deg=30.0,
        view_support_basis="triangulated_observations",
        endpoints_observed=True, endpoints_within_coverage=True,
        scale_source="gps", scale_sigma_rel=0.001)
    verdict = qmod.evaluate(
        qmod.MeasurementQuestion(kind="distance", tolerance_m=5.0),
        value=10.0, sigma=0.05, evidence=good, profile=None)
    reasons = verdict.to_dict()["reasons"]
    assert "interval_not_calibrated" in reasons
    assert verdict.status.value == "estimated_only"


# --------------------------------------------------------------------------- #
# U07 -- a question that cannot be answered must not be stored
# --------------------------------------------------------------------------- #
def test_min_points_matches_what_each_kind_needs():
    from app.routers.questions import MIN_POINTS
    assert MIN_POINTS == {"point": 1, "distance": 2, "height": 2, "area": 3}


def test_supported_levels_come_from_the_library_not_a_copy():
    from app.routers.questions import SUPPORTED_INTERVAL_LEVELS
    from drishti_recon import questions as qmod
    assert SUPPORTED_INTERVAL_LEVELS == set(qmod.SUPPORTED_INTERVAL_LEVELS)


def test_unsupported_level_is_refused_by_the_library_too():
    """The API guard is not the only defence; _Z must not substitute."""
    from drishti_recon import questions as qmod
    with pytest.raises(ValueError, match="not supported"):
        qmod._Z(97)
    assert qmod._Z(95) == pytest.approx(1.96)


@pytest.mark.parametrize("level", [50, 68, 80, 90, 95, 99])
def test_every_advertised_level_actually_works(level):
    from drishti_recon import questions as qmod
    assert qmod._Z(level) > 0


# --------------------------------------------------------------------------- #
# Follow-up verification findings (CRITICAL_REVIEW_VERIFICATION_2026-09-21)
# --------------------------------------------------------------------------- #
def test_both_routes_share_one_result_service():
    """F03: DEC-021 claimed both routes called compute; only one did."""
    import inspect
    from app.routers import questions as qr
    src = inspect.getsource(qr._answer)
    assert "results.compute" in src, (
        "_answer still holds its own copy of the computation")


def test_evidence_ignores_stored_diagnostics():
    """F04: refinement metadata broke the next tolerance change."""
    from drishti_recon import questions as qmod
    stored = {"n_supporting_views": 5, "max_ray_separation_deg": 30.0,
              "view_support_basis": "triangulated_observations",
              "endpoints_observed": True, "endpoints_within_coverage": True,
              "dynamic_contamination": False, "scale_source": "gps",
              "scale_sigma_rel": 0.01,
              "diagnostics": {"endpoints_moved_m": [0.1, 0.0]},
              "endpoints_moved_m": [0.1, 0.0]}
    ev = qmod.Evidence.from_dict(stored)
    assert ev.n_supporting_views == 5
    assert ev.scale_source == "gps"
    assert not hasattr(ev, "endpoints_moved_m")


def test_evidence_from_empty_record_is_the_pessimistic_default():
    from drishti_recon import questions as qmod
    ev = qmod.Evidence.from_dict(None)
    assert ev.endpoints_observed is False
    assert ev.view_support_basis == "frustum_upper_bound"


def test_artifact_version_tracks_the_files_not_only_the_manifest():
    """F06: replacing cloud.npz left stored answers looking current."""
    import inspect
    from app import results
    src = inspect.getsource(results.artifact_version)
    assert "artifact_revision" in src


def test_snap_tolerance_is_strict_when_spacing_is_unknowable():
    """F07: a one-point cloud returned infinity, i.e. no bound at all."""
    from drishti_recon import measure
    from drishti_recon.fusion import PointCloud
    from drishti_recon.provenance import Provenance
    one = PointCloud(np.zeros((1, 3)), np.full((1, 3), 200, np.uint8),
                     np.full(1, 0.9),
                     np.full(1, int(Provenance.OBSERVED_HIGH_CONFIDENCE)),
                     None, np.zeros(1), np.zeros(1))
    assert measure.snap_tolerance(one) == measure.MIN_SNAP_TOLERANCE_M
    m = measure.measure_point(one, [1000.0, 0, 0])
    assert m.extra["all_selections_resolved"] is False


# --------------------------------------------------------------------------- #
# A guessed focal must not be frozen (regression on DEC-038)
# --------------------------------------------------------------------------- #
def _resolve(intr):
    from drishti_recon.pipeline import _resolve_intrinsics
    return _resolve_intrinsics(intr, 1920, 1080, 1600, 900, 1600 / 1920,
                               [], want_flag=True)


def test_a_measured_calibration_reports_itself_as_calibrated():
    K, calibrated = _resolve({"fx": 900, "fy": 900, "cx": 960, "cy": 540})
    assert calibrated is True
    assert K[0, 0] == pytest.approx(900 * 1600 / 1920)


def test_the_estimated_fallback_is_not_calibrated():
    """0.9*max(w,h) is a guess; freezing it is worse than self-calibrating."""
    K, calibrated = _resolve(None)
    assert calibrated is False
    assert K[0, 0] == pytest.approx(0.9 * 1600)


def test_a_bare_focal_length_is_not_a_calibration():
    """No principal point means partial information, not a calibration."""
    K, calibrated = _resolve({"focal_length": 1000})
    assert calibrated is False
    assert K[0, 2] == pytest.approx(800)      # principal point assumed centre


def test_reconstruct_frames_accepts_the_flag():
    import inspect
    from drishti_recon import colmap_adapter
    sig = inspect.signature(colmap_adapter.reconstruct_frames)
    assert "fix_intrinsics" in sig.parameters
