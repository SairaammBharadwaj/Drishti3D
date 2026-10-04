"""RTKLIB .pos import: quality codes, GPS time, datum, malformed rows."""
import calendar
from pathlib import Path

import pytest

from drishti_recon import rtk, telemetry

FIX = Path(__file__).parent / "fixtures" / "rtk"


def test_quality_codes_map_and_keep_the_original():
    rep = telemetry.load(FIX / "mixed_quality.pos")
    status = [s.rtk_status for s in rep.samples]
    assert status == ["RTK_FIXED", "RTK_FIXED", "RTK_FLOAT", "SBAS", "DGPS", "SINGLE",
                      "UNKNOWN"]
    assert [s.extra["rtklib_q"] for s in rep.samples] == [1, 1, 2, 3, 4, 5, 7]
    # Q=4 is DGPS in RTKLIB, not "fixed" as in the CSV convention.
    assert rep.fix_quality_counts == {"fixed": 2, "float": 1, "other": 4, "unknown": 0}
    assert not rep.has_rtk
    s0 = rep.samples[0]
    assert s0.extra["ns"] == 14 and s0.extra["ratio"] == pytest.approx(12.4)
    assert s0.extra["sdu_m"] == pytest.approx(0.0193)
    assert s0.gps_accuracy == pytest.approx((0.0081 ** 2 + 0.0062 ** 2) ** 0.5)


def test_malformed_rows_are_reported_not_dropped_silently():
    rep = telemetry.load(FIX / "mixed_quality.pos")
    bad = [w for w in rep.warnings if ".pos line" in w]
    assert len(bad) == 4            # NaN latitude, short row, month 13, unknown Q
    assert any("invalid position" in w for w in bad)
    assert any("too few columns" in w for w in bad)
    assert any("unreadable epoch" in w for w in bad)
    assert any("Q=7" in w for w in bad)
    assert rep.n_valid == 7


def test_gps_time_becomes_utc_and_relative_timestamps():
    rep = telemetry.load(FIX / "mixed_quality.pos")
    s = rep.samples
    assert [round(x.timestamp, 3) for x in s[:3]] == [0.0, 0.2, 0.4]
    # 06:12:30 GPST is 06:12:12 UTC: GPS has run 18 s ahead since 2017.
    assert s[0].extra["utc_unix"] == calendar.timegm((2024, 3, 5, 6, 12, 12))
    assert s[0].extra["gps_week"] == 2304
    assert s[0].extra["gps_tow"] == pytest.approx(2 * 86400 + 6 * 3600 + 12 * 60 + 30)


def test_week_and_time_of_week_epochs():
    a = telemetry.load(FIX / "gps_week_tow.pos").samples
    b = telemetry.load(FIX / "mixed_quality.pos").samples
    assert a[0].extra["utc_unix"] == b[0].extra["utc_unix"]
    assert a[1].timestamp == pytest.approx(0.5)


def test_utc_file_and_geodetic_height():
    rep = telemetry.load(FIX / "week_tow_utc_geodetic.pos")
    s = rep.samples[0]
    assert s.extra["time_system"] == "UTC"
    assert s.extra["utc_unix"] == calendar.timegm((2024, 3, 5, 6, 12, 12))
    assert s.extra["gps_tow"] == pytest.approx(2 * 86400 + 6 * 3600 + 12 * 60 + 30)
    # "WGS84/geodetic" heights are above the geoid, not the ellipsoid.
    assert rep.vertical_datum == "msl"


def test_ellipsoidal_header_sets_the_datum():
    rep = telemetry.load(FIX / "mixed_quality.pos")
    assert rep.vertical_datum == "ellipsoidal"
    assert "ELLIPSOIDAL" in rep.vertical_datum_basis


def test_ecef_solution():
    s = telemetry.load(FIX / "ecef.pos").samples[0]
    assert s.latitude == pytest.approx(47.3769, abs=1e-7)
    assert s.longitude == pytest.approx(8.5417, abs=1e-7)
    assert s.altitude == pytest.approx(430.0, abs=1e-3)


def test_all_fixed_track_counts_as_rtk(tmp_path):
    lines = (FIX / "mixed_quality.pos").read_text().splitlines()
    keep = [l for l in lines if l.startswith("%")] + [
        l for l in lines if not l.startswith("%") and l.split()[5:6] == ["1"]][:2]
    p = tmp_path / "fixed.pos"
    p.write_text("\n".join(keep) + "\n")
    rep = telemetry.load(p)
    assert rep.n_valid == 2 and rep.has_rtk


def test_missing_datum_in_header_is_unknown(tmp_path):
    body = [l for l in (FIX / "mixed_quality.pos").read_text().splitlines()
            if not l.startswith("% (")]
    p = tmp_path / "nodatum.pos"
    p.write_text("\n".join(body) + "\n")
    rep = telemetry.load(p)
    assert rep.vertical_datum == "unknown"
    assert any("does not state the height datum" in w for w in rep.warnings)


def test_leap_seconds():
    assert rtk.gps_minus_utc(calendar.timegm((2016, 12, 31, 23, 59, 59))) == 17
    assert rtk.gps_minus_utc(calendar.timegm((2017, 1, 1, 0, 0, 0))) == 18
    t = calendar.timegm((2024, 1, 1, 0, 0, 18))
    assert rtk.gpst_to_utc(t) == calendar.timegm((2024, 1, 1, 0, 0, 0))


def test_upload_accepts_pos():
    from app.config import ALLOWED_TELEMETRY_EXT
    assert ".pos" in ALLOWED_TELEMETRY_EXT
