"""Telemetry parsing + frame/telemetry synchronization."""
import json
import numpy as np
from drishti_recon import telemetry as tel
from drishti_recon import sync as syncmod


def _write_csv(p, rows, header="timestamp,latitude,longitude,altitude"):
    p.write_text(header + "\n" + "\n".join(rows))
    return p


def test_parse_csv_basic(tmp_path):
    p = _write_csv(tmp_path / "t.csv",
                   ["0,28.6,77.2,220", "1,28.6001,77.2001,221"])
    rep = tel.load(p)
    assert rep.ok and rep.n_valid == 2
    assert rep.samples[0].latitude == 28.6


def test_parse_csv_aliases_and_invalid(tmp_path):
    p = (tmp_path / "t.csv")
    p.write_text("time,lat,lng,alt\n0,28.6,77.2,220\n1,999,77,220\n2,28.7,77.3,221\n")
    rep = tel.load(p)
    assert rep.n_valid == 2                      # invalid lat=999 skipped
    assert any("invalid" in w for w in rep.warnings)


def test_parse_json(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([
        {"timestamp": 0, "latitude": 1.0, "longitude": 2.0, "altitude": 3.0},
        {"timestamp": 1, "latitude": 1.1, "longitude": 2.1, "altitude": 3.1}]))
    rep = tel.load(p)
    assert rep.n_valid == 2


def test_rtk_detection(tmp_path):
    p = (tmp_path / "t.csv")
    p.write_text("timestamp,latitude,longitude,altitude,rtk_status\n"
                 "0,28.6,77.2,220,RTK\n1,28.6001,77.2001,221,RTK\n")
    rep = tel.load(p)
    assert rep.has_rtk


def test_sync_interpolates_midpoint(tmp_path):
    p = _write_csv(tmp_path / "t.csv",
                   ["0,0,0,0", "2,0,0.0002,0"])
    rep = tel.load(p)
    frame = syncmod.build_enu_frame(rep.samples)
    s = syncmod.synchronize([(0, 0.0), (1, 1.0), (2, 2.0)], rep.samples, frame)
    # endpoints hit the samples; t=1 is their linear midpoint (the mean position)
    assert np.isclose(s[1].enu[0], (s[0].enu[0] + s[2].enu[0]) / 2, atol=1e-6)
    assert s[2].enu[0] > s[0].enu[0]      # east increases along the pass
    assert all(f.confidence > 0 for f in s)


def test_angle_interp_wraps():
    # yaw 350 -> 10 should interpolate through 0, not backwards through 180
    v = syncmod._angle_interp(350.0, 10.0, 0.5)
    assert np.isclose(v % 360, 0.0, atol=1e-6)
