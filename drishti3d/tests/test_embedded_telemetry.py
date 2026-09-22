"""Telemetry carried inside the video, not beside it.

Newer DJI models write their SRT as a subtitle stream in the MP4 rather than a
sidecar file. Requiring the sidecar refuses perfectly good footage over a
packaging detail the operator has no reason to know about.
"""
import shutil
import subprocess
import textwrap

import pytest

from drishti_recon import telemetry as tel

SRT = textwrap.dedent("""\
    1
    00:00:00,000 --> 00:00:01,000
    <font size="28">FrameCnt: 1, DiffTime: 33ms
    2024-05-01 10:00:00,000,000
    [latitude: 47.376900] [longitude: 8.541700] [rel_alt: 30.100 abs_alt: 460.200] [gb_yaw: 12.3 gb_pitch: -89.9 gb_roll: 0.0] [focal_len: 240]</font>

    2
    00:00:01,000 --> 00:00:02,000
    <font size="28">FrameCnt: 2, DiffTime: 33ms
    2024-05-01 10:00:01,000,000
    [latitude: 47.376950] [longitude: 8.541750] [rel_alt: 30.300 abs_alt: 460.400] [gb_yaw: 12.4 gb_pitch: -89.9 gb_roll: 0.0] [focal_len: 240]</font>
    """)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed")


def _video(tmp_path, with_subs: bool):
    plain = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=320x240:d=4", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(plain)], check=True)
    if not with_subs:
        return plain
    srt = tmp_path / "t.srt"
    srt.write_text(SRT)
    out = tmp_path / "with_srt.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(plain),
                    "-i", str(srt), "-c", "copy", "-c:s", "mov_text",
                    str(out)], check=True)
    return out


@needs_ffmpeg
def test_telemetry_is_read_from_an_embedded_subtitle_track(tmp_path):
    report = tel.load(_video(tmp_path, with_subs=True))
    assert report.n_valid == 2
    assert report.samples[0].latitude == pytest.approx(47.3769)
    assert report.samples[1].longitude == pytest.approx(8.54175)
    # Absolute altitude is preferred over relative, per parse_srt.
    assert report.samples[0].altitude == pytest.approx(460.2)
    assert any("subtitle track" in w for w in report.warnings)


@needs_ffmpeg
def test_a_video_without_subtitles_says_so_rather_than_returning_nothing(tmp_path):
    with pytest.raises(ValueError, match="no subtitle track"):
        tel.load(_video(tmp_path, with_subs=False))


@needs_ffmpeg
def test_extract_returns_none_for_a_plain_video(tmp_path):
    assert tel.extract_embedded_srt(_video(tmp_path, with_subs=False)) is None


def test_a_sidecar_srt_still_works(tmp_path):
    srt = tmp_path / "flight.srt"
    srt.write_text(SRT)
    report = tel.load(srt)
    assert report.n_valid == 2
    assert not any("subtitle track" in w for w in report.warnings)


def test_video_suffixes_cover_what_drones_actually_write():
    for ext in (".mp4", ".mov", ".mkv", ".lrv"):
        assert ext in tel.VIDEO_SUFFIXES
