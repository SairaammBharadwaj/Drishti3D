"""OBJ is always written; FBX through assimp, or an explicit unavailable state."""
import json

import numpy as np
import pytest

from drishti_recon import exports
from drishti_recon.geo import ENUFrame

V = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 1], [0, 10, 1]], float)
F = np.array([[0, 1, 2], [0, 2, 3]])
C = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]], np.uint8)


def _read_obj(path):
    v, f = [], []
    for line in open(path):
        if line.startswith("v "):
            v.append([float(x) for x in line.split()[1:]])
        elif line.startswith("f "):
            f.append([int(x) for x in line.split()[1:]])
    return np.array(v), np.array(f)


def test_obj_round_trips_geometry_and_colour(tmp_path):
    p = exports.export_obj(tmp_path / "m.obj", V, F, C)
    v, f = _read_obj(p)
    assert np.allclose(v[:, :3], V)
    assert np.allclose(v[:, 3:], C / 255.0, atol=1e-4)
    assert (f - 1 == F).all()                  # OBJ is 1-based
    head = open(p).read().splitlines()[:3]
    assert any("not for measurement" in h for h in head)


def test_obj_rejects_bad_faces(tmp_path):
    with pytest.raises(ValueError):
        exports.export_obj(tmp_path / "m.obj", V, [[0, 1, 9]])


def test_fbx_unavailable_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "assimp_available", lambda: None)
    out = exports.export_mesh_formats(tmp_path, V, F, C,
                                      frame=ENUFrame(12.97, 77.59, 920.0))
    assert "mesh_obj" in out["artifacts"] and "mesh_fbx" not in out["artifacts"]
    fbx = out["status"]["fbx"]
    assert fbx == {"available": False, "ok": False, "detail": fbx["detail"]}
    assert "assimp unavailable" in fbx["detail"]
    doc = json.loads((tmp_path / "mesh_formats.json").read_text())
    assert doc["caveat"] == exports.MESH_CAVEAT
    assert "lat 12.97" in open(out["artifacts"]["mesh_obj"]).read()


def test_fbx_through_assimp(tmp_path):
    if exports.assimp_available() is None:
        pytest.skip("assimp command-line tool not installed")
    out = exports.export_mesh_formats(tmp_path, V, F, C)
    assert out["status"]["fbx"]["ok"], out["status"]["fbx"]
    data = open(out["artifacts"]["mesh_fbx"], "rb").read()
    assert data[:18] == b"Kaydara FBX Binary" or b"FBXHeaderExtension" in data[:4096]


def test_assimp_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "assimp_available", lambda: "/bin/false")
    out = exports.convert_with_assimp(tmp_path / "missing.obj", tmp_path / "x.fbx")
    assert out["available"] and not out["ok"] and "assimp failed" in out["detail"]
