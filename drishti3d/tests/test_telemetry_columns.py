"""Telemetry CSV headers that annotate their units.

Exporters label units -- `latitude [deg]`, `altitude(m)`, `alt_m` -- and an
operator should not have to hand-edit the header of their own flight log to
load it. The importer required an exact match, so every one of these was
rejected with no usable telemetry and the mission silently fell back to
relative scale.
"""
import pathlib
import tempfile

import pytest

from drishti_recon import telemetry as tel

ROWS = "0.0,47.3769,8.5417,460.2\n1.0,47.3770,8.5418,460.5\n"


def _csv(header: str, rows: str = ROWS) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "t.csv"
    p.write_text(header + "\n" + rows)
    return p


@pytest.mark.parametrize("header", [
    "timestamp,latitude,longitude,altitude",
    "timestamp [s],latitude [deg],longitude [deg],altitude [m]",
    "timestamp(s),latitude(deg),longitude(deg),altitude(m)",
    "time_s,lat_deg,lon_deg,alt_m",
    "Timestamp [s],Latitude [degrees],Longitude [degrees],Altitude [metres]",
    "ts,lat,lng,height (m)",
    "t,lat,lon,alt",
])
def test_unit_annotated_headers_load(header):
    warnings = []
    samples, _ = tel.parse_csv(_csv(header), warnings)
    assert len(samples) == 2
    assert samples[0].latitude == pytest.approx(47.3769)
    assert samples[0].longitude == pytest.approx(8.5417)
    assert samples[0].altitude == pytest.approx(460.2)
    assert samples[0].timestamp == pytest.approx(0.0)


def test_nanosecond_column_does_not_collapse_onto_seconds():
    """The reason `ns`/`ms`/`us` are not stripped.

    Our own schema writes `timestamp` in seconds beside `timestamp_ns` in
    nanoseconds. Treating `_ns` as a unit suffix would map both to `timestamp`
    and read 1.7e18 as a time in seconds.
    """
    p = _csv("timestamp,timestamp_ns,latitude,longitude,altitude",
             "0.0,1700000000000000000,47.3769,8.5417,460.2\n"
             "1.0,1700000001000000000,47.3770,8.5418,460.5\n")
    samples, _ = tel.parse_csv(p, [])
    assert samples[0].timestamp == pytest.approx(0.0)
    assert samples[1].timestamp == pytest.approx(1.0)


def test_an_exact_column_beats_a_unit_stripped_one():
    """Order must not decide which column wins."""
    warnings = []
    p = _csv("timestamp,altitude,altitude_m,latitude,longitude",
             "0.0,460.2,999.9,47.3769,8.5417\n"
             "1.0,460.5,999.9,47.3770,8.5418\n")
    samples, _ = tel.parse_csv(p, warnings)
    assert samples[0].altitude == pytest.approx(460.2)
    assert any("altitude_m" in w for w in warnings)


def test_a_header_with_no_recognisable_columns_still_reports_rows():
    warnings = []
    p = _csv("a,b,c,d")
    samples, _ = tel.parse_csv(p, warnings)
    assert samples == []
    assert warnings


@pytest.mark.parametrize("name,expected", [
    ("latitude [deg]", "latitude"),
    ("Altitude (m)", "altitude"),
    ("alt_m", "alt"),
    ("timestamp_ns", "timestamp_ns"),
    ("ground_speed_mps", "ground_speed"),
    ("lat", "lat"),
])
def test_strip_units(name, expected):
    assert tel._strip_units(name) == expected
