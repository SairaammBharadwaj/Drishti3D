"""Frame-quality scoring and metric measurements."""
import numpy as np
from drishti_recon import frame_quality as fq
from drishti_recon import measure
from drishti_recon.fusion import PointCloud
from drishti_recon.provenance import Provenance


def _img(val, noise=False, size=(120, 160)):
    img = np.full((*size, 3), val, np.uint8)
    if noise:
        rng = np.random.default_rng(0)
        img = rng.integers(0, 255, (*size, 3), dtype=np.uint8)
    return img


def test_blur_detects_sharp_vs_flat():
    sharp = fq.analyze([(0, 0.0, _img(0, noise=True))])[0]
    flat = fq.analyze([(1, 0.0, _img(128))])[0]
    assert sharp.blur > flat.blur
    assert "blurry" in flat.reasons


def test_exposure_flags():
    dark = fq.analyze([(0, 0.0, _img(2))])[0]
    bright = fq.analyze([(1, 0.0, _img(254))])[0]
    assert "underexposed" in dark.reasons or "clipped_dark" in dark.reasons
    assert "overexposed" in bright.reasons or "clipped_bright" in bright.reasons


def _grid_cloud():
    xs, ys = np.meshgrid(np.linspace(0, 10, 40), np.linspace(0, 10, 40))
    pts = np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], 1)
    cols = np.full((len(pts), 3), 200, np.uint8)
    conf = np.full(len(pts), 0.9)
    prov = np.full(len(pts), int(Provenance.OBSERVED_HIGH_CONFIDENCE))
    return PointCloud(pts, cols, conf, prov, None)


def test_distance_measurement():
    c = _grid_cloud()
    m = measure.measure_distance(c, [[0, 0, 0], [10, 0, 0]], allow_inferred=True)
    assert abs(m.value - 10.0) < 0.3
    assert m.unit == "m"


def test_height_measurement():
    c = _grid_cloud()
    # add an elevated point
    c.points = np.vstack([c.points, [5, 5, 4.0]])
    c.provenance = np.append(c.provenance, int(Provenance.OBSERVED_HIGH_CONFIDENCE))
    c.confidence = np.append(c.confidence, 0.9)
    c.colors = np.vstack([c.colors, [200, 200, 200]])
    m = measure.measure_height(c, [5, 5, 0], [5, 5, 4], allow_inferred=True)
    assert abs(m.value - 4.0) < 0.3


def test_area_of_unit_square():
    c = _grid_cloud()
    m = measure.measure_area(c, [[0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0]],
                             allow_inferred=True)
    assert abs(m.value - 16.0) < 1.0


def test_measurement_excludes_inferred_by_default():
    """Selecting AI geometry with inference off must refuse, not substitute.

    This test used to assert the opposite -- that the pick snapped 100 m down
    to the observed grid -- which is the silent substitution C03 describes: the
    operator selects a roof and is quietly given the ground beneath it. Hiding
    the AI point is necessary but not sufficient; the nearest *observed* point
    is not automatically what was meant.
    """
    c = _grid_cloud()
    c.points = np.vstack([c.points, [5, 5, 100.0]])
    c.provenance = np.append(c.provenance, int(Provenance.AI_ASSISTED))
    c.confidence = np.append(c.confidence, 0.0)
    c.colors = np.vstack([c.colors, [155, 89, 182]])
    m = measure.measure_point(c, [5, 5, 100], allow_inferred=False)
    assert m.extra["all_selections_resolved"] is False
    assert m.extra["max_snap_displacement_m"] > 50
    assert not np.isfinite(m.sigma)
    assert any("not on measurable geometry" in w for w in m.warnings)
    # The AI point is still excluded: it was never the resolved provenance.
    assert not m.used_inferred


def test_inferred_point_is_usable_when_explicitly_allowed():
    c = _grid_cloud()
    c.points = np.vstack([c.points, [5, 5, 100.0]])
    c.provenance = np.append(c.provenance, int(Provenance.AI_ASSISTED))
    c.confidence = np.append(c.confidence, 0.0)
    c.colors = np.vstack([c.colors, [155, 89, 182]])
    m = measure.measure_point(c, [5, 5, 100], allow_inferred=True)
    assert m.extra["all_selections_resolved"] is True
    assert m.used_inferred
    assert any("AI-assisted" in w for w in m.warnings)
