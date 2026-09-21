"""C08: exports must be placeable and must keep their uncertainty.

Counterexample from the review: `export_las(..., frame=...)` accepted a frame,
ignored it, wrote local coordinates, and produced a file whose
`header.parse_crs()` was None with no provenance or uncertainty fields.
"""
import json
import numpy as np
import pytest

laspy = pytest.importorskip("laspy")
pyproj = pytest.importorskip("pyproj")

from drishti_recon import exports
from drishti_recon.geo import ENUFrame
from drishti_recon.fusion import PointCloud
from drishti_recon.provenance import Provenance

# Zurich, matching the AGZ missions.
FRAME = ENUFrame(47.3769, 8.5417, 430.0)


def _cloud(n=50):
    rng = np.random.default_rng(0)
    return PointCloud(
        rng.normal(0, 20, (n, 3)),
        np.full((n, 3), 200, np.uint8),
        np.full(n, 0.8),
        np.full(n, int(Provenance.OBSERVED_HIGH_CONFIDENCE)),
        None,
        np.full(n, 0.03),
        np.full(n, 0.05),
    )


def test_las_declares_a_crs_when_given_a_frame(tmp_path):
    p = exports.export_las(tmp_path / "c.las", _cloud(), FRAME)
    crs = laspy.read(p).header.parse_crs()
    assert crs is not None, "georeferenced export still has no CRS"
    assert crs.to_epsg() == 32632          # UTM 32N covers Zurich


def test_las_points_land_in_the_right_place(tmp_path):
    """The origin must round-trip to its own geodetic position."""
    cloud = _cloud(1)
    cloud.points = np.zeros((1, 3))
    las = laspy.read(exports.export_las(tmp_path / "c.las", cloud, FRAME))
    tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
    x0, y0 = tr.transform(FRAME.lon0, FRAME.lat0)
    assert float(las.x[0]) == pytest.approx(x0, abs=0.05)
    assert float(las.y[0]) == pytest.approx(y0, abs=0.05)
    assert float(las.z[0]) == pytest.approx(FRAME.alt0, abs=0.05)


def test_known_offset_survives_the_round_trip(tmp_path):
    """100 m east must still be 100 m east after projection."""
    cloud = _cloud(2)
    cloud.points = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
    las = laspy.read(exports.export_las(tmp_path / "c.las", cloud, FRAME))
    d = np.hypot(float(las.x[1]) - float(las.x[0]),
                 float(las.y[1]) - float(las.y[0]))
    # UTM scale factor departs from 1 by <1e-3 in-zone; 0.2 m over 100 m.
    assert d == pytest.approx(100.0, abs=0.2)


def test_las_carries_provenance_confidence_and_sigma(tmp_path):
    las = laspy.read(exports.export_las(tmp_path / "c.las", _cloud(), FRAME))
    names = set(las.point_format.dimension_names)
    assert {"provenance", "confidence", "sigma"} <= names
    assert np.allclose(np.asarray(las.sigma), 0.05)
    assert np.all(np.asarray(las.provenance)
                  == int(Provenance.OBSERVED_HIGH_CONFIDENCE))


def test_las_without_a_frame_stays_local_and_says_nothing_false(tmp_path):
    las = laspy.read(exports.export_las(tmp_path / "c.las", _cloud(), None))
    assert las.header.parse_crs() is None
    assert {"provenance", "sigma"} <= set(las.point_format.dimension_names)


def test_sigma_is_nan_when_the_cloud_has_none(tmp_path):
    c = _cloud()
    c.sigma = c.sigma_major = None
    las = laspy.read(exports.export_las(tmp_path / "c.las", c, FRAME))
    assert np.all(np.isnan(np.asarray(las.sigma)))


def test_ply_carries_sigma(tmp_path):
    p = exports.export_ply(tmp_path / "c.ply", _cloud())
    text = open(p).read()
    assert "property float sigma" in text
    body = [l for l in text.splitlines() if not l[0].isalpha()]
    assert float(body[0].split()[-1]) == pytest.approx(0.05)


def test_sidecar_places_a_local_file(tmp_path):
    p = exports.export_georeference_sidecar(tmp_path / "geo.json", _cloud(), FRAME)
    doc = json.loads(open(p).read())
    assert doc["projected_crs"] == "EPSG:32632"
    assert doc["local_origin_wgs84"]["lat"] == pytest.approx(FRAME.lat0)
    assert "ellipsoidal" in doc["vertical_reference"]
    assert "sigma" in doc["fields"]
    assert "not a calibrated interval" in doc["caveat"]


def test_sidecar_is_honest_without_a_frame(tmp_path):
    doc = json.loads(open(exports.export_georeference_sidecar(
        tmp_path / "geo.json", _cloud(), None)).read())
    assert doc["projected_crs"] is None
    assert doc["local_origin_wgs84"] is None


@pytest.mark.parametrize("lat,lon,epsg", [
    (47.37, 8.54, 32632),      # Zurich
    (12.97, 77.59, 32643),     # Bengaluru
    (-33.87, 151.21, 32756),   # Sydney, southern hemisphere
])
def test_utm_zone_selection(lat, lon, epsg):
    assert exports.utm_epsg(lat, lon) == epsg
