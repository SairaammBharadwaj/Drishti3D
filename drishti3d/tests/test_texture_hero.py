"""scripts/texture_hero.py: place an OpenMVS textured OBJ in ENU, or refuse."""
import importlib.util
import json
import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("texture_hero", ROOT / "scripts" / "texture_hero.py")
th = importlib.util.module_from_spec(spec)
spec.loader.exec_module(th)


def _rz(deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _R_to_qvec(R):
    from drishti_recon.replay import matrix_to_quaternion
    x, y, z, w = matrix_to_quaternion(R)
    return [w, x, y, z]


def mission(tmp_path, *, bin_model=False, shift=0.0):
    """A COLMAP model whose cameras the manifest's transform puts on trajectory.json."""
    s, R, t = 3.0, _rz(30), np.array([100.0, -50.0, 20.0])
    centres = [np.array([i, 0.2 * i, 1.0]) for i in range(5)]
    sparse = tmp_path / "ws" / "sparse" / "0"
    sparse.mkdir(parents=True)
    Rc = _rz(10)                                   # any camera rotation
    if bin_model:
        with open(sparse / "images.bin", "wb") as f:
            f.write(struct.pack("<Q", len(centres)))
            for i, C in enumerate(centres):
                tv = -Rc @ C
                f.write(struct.pack("<idddddddi", i + 1, *_R_to_qvec(Rc), *tv, 1))
                f.write(f"{i:04d}.jpg".encode() + b"\x00")
                f.write(struct.pack("<Q", 0))
    else:
        lines = []
        for i, C in enumerate(centres):
            q, tv = _R_to_qvec(Rc), -Rc @ C
            lines.append(f"{i + 1} {' '.join(map(str, q))} {' '.join(map(str, tv))} 1 {i:04d}.jpg")
            lines.append("")
        (sparse / "images.txt").write_text("\n".join(lines))
    art = tmp_path / "art"
    art.mkdir()
    (art / "manifest.json").write_text(json.dumps({"transforms": {
        "recon_to_enu": {"scale": s, "R": R.tolist(), "t": t.tolist()}}}))
    stored = [(s * R @ C + t + shift).tolist() for C in centres]
    (art / "trajectory.json").write_text(json.dumps({"cameras_enu": [
        {"frame_index": 10 * i, "C": c} for i, c in enumerate(stored)]}))
    mv = tmp_path / "mvs"
    mv.mkdir()
    (mv / "scene_mesh_texture.obj").write_text(
        "mtllib scene_mesh_texture.mtl\nv 1 0 0\nv 0 1 0\nv 0 0 1\nvt 0 0\nvt 1 0\nvt 0 1\n"
        "vn 0 0 1\nusemtl m\nf 1/1/1 2/2/1 3/3/1\n")
    (mv / "scene_mesh_texture.mtl").write_text("newmtl m\nmap_Kd scene_mesh_texture0.png\n")
    (mv / "scene_mesh_texture0.png").write_bytes(b"\x89PNG fake")
    return art, sparse, mv / "scene_mesh_texture.obj", (s, R, t)


@pytest.mark.parametrize("bin_model", [False, True])
def test_places_the_mesh_in_enu(tmp_path, bin_model):
    art, sparse, obj, (s, R, t) = mission(tmp_path, bin_model=bin_model)
    status = th.place(obj, art, json.loads((art / "manifest.json").read_text()),
                      json.loads((art / "trajectory.json").read_text()), sparse)
    assert status["display_only"] and status["alignment_check"]["camera_rms_m"] < 1e-6
    v = [list(map(float, l.split()[1:4])) for l in open(art / "textured_mesh.obj")
         if l.startswith("v ")]
    assert np.allclose(v[0], s * R @ [1, 0, 0] + t, atol=1e-3)
    text = (art / "textured_mesh.obj").read_text()
    assert "never used for measurement" in text and "mtllib textured_mesh.mtl" in text
    assert "f 1/1/1 2/2/1 3/3/1" in text
    names = zipfile.ZipFile(art / "textured_mesh.zip").namelist()
    assert set(names) == {"textured_mesh.obj", "textured_mesh.mtl", "scene_mesh_texture0.png"}


def test_refuses_a_mismatched_workspace(tmp_path):
    art, sparse, obj, _ = mission(tmp_path, shift=0.5)
    with pytest.raises(SystemExit, match="refusing"):
        th.place(obj, art, json.loads((art / "manifest.json").read_text()),
                 json.loads((art / "trajectory.json").read_text()), sparse)
    assert not (art / "textured_mesh.obj").exists()


def test_levelling_without_alignment():
    R = _rz(2)
    sim = th.recon_to_enu({"transforms": {"recon_to_enu": None, "gravity_leveling": {
        "applied": True, "composed_into_alignment": False,
        "rotation": R.tolist(), "pivot_enu": [5, 5, 0]}}})
    assert np.allclose(th.apply(sim, [5, 5, 0]), [5, 5, 0])
    assert th.recon_to_enu({})[0] == 1.0
