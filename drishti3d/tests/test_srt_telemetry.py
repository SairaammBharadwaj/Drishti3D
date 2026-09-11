"""DJI/Autel .SRT telemetry parsing.

The altitude cases carry real risk: a DJI subtitle line contains *both*
``rel_alt`` (above take-off) and ``abs_alt`` (above MSL), often hundreds of
metres apart. Picking the wrong one puts the whole reconstruction out
vertically by the launch elevation, and nothing downstream can detect it.
"""
import pathlib
import tempfile

import pytest

from drishti_recon import telemetry


def _srt(body: str) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "t.srt"
    p.write_text(body)
    return p


DJI = """1
00:00:00,000 --> 00:00:00,033
[latitude: 47.384357] [longitude: 8.545178] [rel_alt: 12.300 abs_alt: 464.910] [gb_yaw: 137.2 gb_pitch: -89.9 gb_roll: 0.0] [focal_len: 24.00]

2
00:00:01,000 --> 00:00:01,033
[latitude: 47.384360] [longitude: 8.545180] [rel_alt: 12.400 abs_alt: 465.010] [gb_yaw: 137.3 gb_pitch: -90.0 gb_roll: 0.5] [focal_len: 24.00]
"""


class TestAltitude:
    def test_absolute_altitude_wins_over_relative(self):
        r = telemetry.load(_srt(DJI))
        s = r.samples[0]
        assert s.altitude == pytest.approx(464.910)     # MSL, not 12.3
        assert s.extra["altitude_kind"] == "msl"
        assert s.extra["rel_alt"] == pytest.approx(12.300)

    def test_relative_only_is_used_but_flagged(self):
        body = DJI.replace(" abs_alt: 464.910", "").replace(" abs_alt: 465.010", "")
        r = telemetry.load(_srt(body))
        assert r.samples[0].altitude == pytest.approx(12.300)
        assert r.samples[0].extra["altitude_kind"] == "relative_to_takeoff"
        assert any("relative to take-off" in w for w in r.warnings)

    def test_relative_is_not_silently_treated_as_msl(self):
        """The regression this guards: one alternation matching whichever
        altitude token appeared first."""
        body = DJI.replace("rel_alt: 12.300 abs_alt: 464.910",
                           "abs_alt: 464.910 rel_alt: 12.300")
        r = telemetry.load(_srt(body))
        assert r.samples[0].altitude == pytest.approx(464.910)


class TestGimbal:
    def test_gimbal_attitude_is_captured_as_roll_pitch_yaw(self):
        r = telemetry.load(_srt(DJI))
        assert r.samples[0].extra["gimbal_rpy_deg"] == [0.0, -89.9, 137.2]
        assert r.samples[1].extra["gimbal_rpy_deg"] == [0.5, -90.0, 137.3]

    def test_missing_gimbal_is_warned_not_assumed(self):
        import re
        body = re.sub(r"\[gb_[^\]]*\]", "", DJI)
        r = telemetry.load(_srt(body))
        assert not any("gimbal_rpy_deg" in s.extra for s in r.samples)
        assert any("gimbal" in w.lower() for w in r.warnings)

    def test_gimbal_feeds_the_frame_chain(self):
        import numpy as np
        from drishti_recon import frames
        r = telemetry.load(_srt(DJI))
        rpy = r.samples[1].extra["gimbal_rpy_deg"]      # pitch -90 = nadir
        v = frames.optical_axis_enu(frames.R_enu_from_cam(*rpy))
        assert v[2] < -0.99                              # looking down


class TestOtherFields:
    def test_focal_length_captured(self):
        r = telemetry.load(_srt(DJI))
        assert r.samples[0].extra["focal_len_mm"] == pytest.approx(24.0)

    def test_timestamps_parsed_and_ordered(self):
        r = telemetry.load(_srt(DJI))
        assert [s.timestamp for s in r.samples] == [0.0, 1.0]

    def test_position_parsed(self):
        s = telemetry.load(_srt(DJI)).samples[0]
        assert s.latitude == pytest.approx(47.384357)
        assert s.longitude == pytest.approx(8.545178)

    def test_autel_style_gimbal_keys(self):
        body = DJI.replace("gb_yaw", "gimbal_yaw").replace(
            "gb_pitch", "gimbal_pitch").replace("gb_roll", "gimbal_roll")
        r = telemetry.load(_srt(body))
        assert r.samples[0].extra["gimbal_rpy_deg"] == [0.0, -89.9, 137.2]

    def test_empty_file_warns_rather_than_crashing(self):
        r = telemetry.load(_srt("\n"))
        assert r.samples == []
        assert any("no GPS" in w for w in r.warnings)
