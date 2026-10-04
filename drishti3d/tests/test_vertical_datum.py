"""What a mission's heights are measured from, carried from telemetry to exports.

Every export used to say "WGS84 ellipsoidal". DEC-047 found three sources that
were not: UseGeo's heights are above sea level (47 m apart in Sardinia), AGZ's
autopilot records MSL, and the AirLock DJI altitude is unlabelled and not
absolute at all. A source that does not say is "unknown", never a default.
"""
import json
import pathlib
import tempfile

import numpy as np
import pytest

from drishti_recon import exports
from drishti_recon import telemetry as tel
from drishti_recon.geo import ENUFrame, VERTICAL_DATUMS

ROWS = [(0.0, 47.3769, 8.5417, 460.2), (1.0, 47.3770, 8.5418, 460.5)]


def _csv(header: str, extra=None) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "t.csv"
    lines = [header] + [",".join(map(str, r)) + ("," + extra[i] if extra else "")
                        for i, r in enumerate(ROWS)]
    p.write_text("\n".join(lines) + "\n")
    return p


@pytest.mark.parametrize("label, datum", [
    ("ELLIPSOIDAL", "ellipsoidal"), ("MSL", "msl"), ("msl", "msl"),
    ("RELATIVE_TO_TAKEOFF", "relative"), ("UNSPECIFIED", "unknown"),
    ("AGL", "unknown"), ("EGM96", "msl"),
])
def test_altitude_reference_column(label, datum):
    r = tel.load(_csv("timestamp,latitude,longitude,altitude,altitude_reference",
                      [label, label]))
    assert r.vertical_datum == datum
    assert label in r.vertical_datum_basis
    assert r.samples[0].altitude == pytest.approx(460.2)       # never converted
    assert any("altitude reference unknown" in w for w in r.warnings) == (datum == "unknown")


def test_a_plain_altitude_column_is_unknown_not_ellipsoidal():
    r = tel.load(_csv("timestamp,latitude,longitude,altitude"))
    assert r.vertical_datum == "unknown"
    assert any("altitude_reference" in w for w in r.warnings)  # says how to fix it


@pytest.mark.parametrize("col, datum", [
    ("alt_msl", "msl"), ("altitude_msl_m", "msl"), ("ellipsoidal_altitude", "ellipsoidal"),
    ("altitude [m, WGS84]", "ellipsoidal"), ("rel_alt", None), ("altitude_agl", "unknown"),
])
def test_the_altitude_column_name_can_state_the_datum(col, datum):
    if datum is None:                     # not read as altitude at all: no telemetry
        with pytest.raises(Exception):
            r = tel.load(_csv(f"timestamp,latitude,longitude,{col}"))
            assert r.n_valid >= 2
        return
    r = tel.load(_csv(f'timestamp,latitude,longitude,"{col}"'))
    assert r.n_valid == 2
    assert r.vertical_datum == datum


def test_an_explicit_reference_beats_the_column_name():
    r = tel.load(_csv("timestamp,latitude,longitude,alt_msl,altitude_reference",
                      ["ELLIPSOIDAL", "ELLIPSOIDAL"]))
    assert r.vertical_datum == "ellipsoidal"


def test_samples_that_disagree_are_unknown():
    r = tel.load(_csv("timestamp,latitude,longitude,altitude,altitude_reference",
                      ["MSL", "ELLIPSOIDAL"]))
    assert r.vertical_datum == "unknown"
    assert "disagree" in r.vertical_datum_basis


def test_json_carries_the_reference():
    p = pathlib.Path(tempfile.mkdtemp()) / "t.json"
    p.write_text(json.dumps([{"timestamp": t, "latitude": a, "longitude": o, "altitude": h,
                              "altitude_reference": "MSL"} for t, a, o, h in ROWS]))
    assert tel.load(p).vertical_datum == "msl"


SRT = """1
00:00:00,000 --> 00:00:00,033
[latitude: 30.264601] [longitude: -97.753404] {alt}

2
00:00:01,000 --> 00:00:01,033
[latitude: 30.264611] [longitude: -97.753414] {alt}
"""


@pytest.mark.parametrize("alt, datum", [
    ("[rel_alt: 12.300 abs_alt: 464.910]", "msl"),
    ("[rel_alt: 12.300]", "relative"),
    ("[altitude: 445.300000]", "unknown"),         # the AirLock DJI form (DEC-047)
])
def test_srt_altitude_kinds(alt, datum):
    p = pathlib.Path(tempfile.mkdtemp()) / "t.srt"
    p.write_text(SRT.format(alt=alt))
    assert tel.load(p).vertical_datum == datum


def test_no_telemetry_is_unknown():
    assert tel.vertical_datum([]) == ("unknown", "no telemetry")
    assert tel.TelemetryReport([], 0, 0, []).vertical_datum == "unknown"


# --------------------------------------------------------------- exports
class _Cloud:
    points = np.zeros((2, 3))


FRAME = ENUFrame(39.566, 8.978, 188.9)


def test_sidecar_records_the_datum_it_is_given(tmp_path):
    doc = json.loads(open(exports.export_georeference_sidecar(
        tmp_path / "g.json", _Cloud(), FRAME, vertical_datum="msl",
        vertical_datum_basis="altitude_reference MSL")).read())
    assert doc["vertical_datum"] == "msl"
    assert doc["vertical_reference"] == VERTICAL_DATUMS["msl"]
    assert doc["vertical_datum_basis"] == "altitude_reference MSL"
    assert doc["local_origin_wgs84"]["alt_m"] == pytest.approx(188.9)
    assert "alt_ellipsoidal_m" not in doc["local_origin_wgs84"]


def test_sidecar_claims_nothing_by_default(tmp_path):
    doc = json.loads(open(exports.export_georeference_sidecar(
        tmp_path / "g.json", _Cloud(), FRAME)).read())
    assert doc["vertical_datum"] == "unknown"
    assert "ellipsoidal" not in doc["vertical_reference"]
