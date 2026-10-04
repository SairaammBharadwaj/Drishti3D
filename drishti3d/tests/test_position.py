"""Coordinates of a point in every form, and the refusal when the geoid is missing."""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon import position
from drishti_recon.geo import ENUFrame

# Austin, as DJI_1003: the geoid is 26.9 m below the ellipsoid here.
AUSTIN = ENUFrame(30.2644, -97.7527, 150.0)


def _egm2008_or_skip():
    try:
        position.orthometric_height(30.0, -97.0, 100.0)
    except position.GeoidUnavailable:
        pytest.skip("EGM2008 grid not installed")


def test_sea_level_height_uses_the_grid_not_a_ballpark():
    _egm2008_or_skip()
    tr = position._vertical_transformer()
    assert "us_nga_egm08_25.tif" in tr.definition          # the grid, by name
    H = position.orthometric_height(30.2644, -97.7527, 150.0)[0]
    assert abs((150.0 - H) - (-26.886)) < 0.01             # N = h - H


def test_mechanics_match_geographiclib_with_egm96():
    """GeographicLib's published GeoidEval example, through the same code path."""
    try:
        H = position.orthometric_height(16 + 46 / 60 + 33 / 3600, -(3 + 34 / 3600), 100.0,
                                        height_crs=5773)[0]
    except position.GeoidUnavailable:
        pytest.skip("EGM96 grid not installed")
    assert abs((100.0 - H) - 28.7068) < 0.02                 # Timbuktu, EGM96


def test_refuses_rather_than_returning_the_ellipsoidal_height():
    # NAVD88 height needs NOAA's GEOID18 grids, which are not installed here:
    # the call must raise, not hand back the input as if it were an answer.
    with pytest.raises(position.GeoidUnavailable, match="ellipsoidal"):
        position.orthometric_height(30.0, -97.0, 100.0, height_crs=5703)


def test_describe_gives_every_form_and_names_the_heights():
    out = position.describe(AUSTIN, [0.0, 0.0, 0.0], vertical_datum="ellipsoidal")
    assert abs(out["lat"] - 30.2644) < 1e-9 and abs(out["h_ellipsoidal_m"] - 150.0) < 1e-6
    assert out["utm"]["epsg"] == 32614 and out["utm"]["zone"] == "14N"
    if out["mgrs"] is not None:
        assert out["mgrs"].startswith("14R")
        assert out["mgrs"][-10:-5] == f"{int(out['utm']['easting_m']) % 100000:05d}"
    if out["h_msl_m"] is None:
        assert "ellipsoidal" in out["height_note"]
    else:
        assert abs(out["h_msl_m"] - (150.0 + 26.886)) < 0.01


def test_sea_level_source_is_given_as_recorded():
    _egm2008_or_skip()
    out = position.describe(AUSTIN, [0.0, 0.0, 0.0], vertical_datum="msl")
    assert out["h_msl_m"] == pytest.approx(150.0)              # not converted again
    assert "not stated" in out["h_msl_model"]
    assert out["h_ellipsoidal_m"] == pytest.approx(150.0 - 26.886, abs=0.01)
    assert "EGM2008" in out["h_ellipsoidal_model"]


@pytest.mark.parametrize("datum", ["unknown", "relative", None])
def test_no_absolute_height_without_a_stated_datum(datum):
    """DEC-047: Austin's unlabelled DJI altitude put the ground 115-135 m low."""
    kw = {} if datum is None else {"vertical_datum": datum}
    out = position.describe(AUSTIN, [0.0, 0.0, 0.0], **kw)
    assert out["h_msl_m"] is None and out["h_ellipsoidal_m"] is None
    assert out["vertical_datum"] == (datum or "unknown") and out["height_note"]
    assert abs(out["lat"] - 30.2644) < 1e-9                    # placement still given
    if datum == "relative":
        assert out["h_relative_m"] == pytest.approx(150.0)
    else:
        assert "h_relative_m" not in out


def test_relative_scale_has_no_position():
    out = position.describe(AUSTIN, [1.0, 2.0, 3.0], georeferenced=False)
    assert out == {"georeferenced": False,
                   "note": "relative scale: this reconstruction has no position on the earth"}
