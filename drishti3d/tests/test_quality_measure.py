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
    c = _grid_cloud()
    # add an AI-assisted point far above; default measurement must not snap to it
    c.points = np.vstack([c.points, [5, 5, 100.0]])
    c.provenance = np.append(c.provenance, int(Provenance.AI_ASSISTED))
    c.confidence = np.append(c.confidence, 0.0)
    c.colors = np.vstack([c.colors, [155, 89, 182]])
    m = measure.measure_point(c, [5, 5, 100], allow_inferred=False)
    assert m.points_enu[0][2] < 50   # snapped to observed grid, not the AI point
