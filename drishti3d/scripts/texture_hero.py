"""Photo-textured mesh for one hero mission, with OpenMVS: display geometry only.

    python scripts/texture_hero.py data/projects/<id>/artifacts \\
        --colmap /path/to/colmap/workspace --openmvs /opt/openmvs/bin

The workspace is the one a ``--engine colmap`` run keeps (``images/`` and
``sparse/0`` or ``sparse/``). This runs OpenMVS's InterfaceCOLMAP,
DensifyPointCloud, ReconstructMesh and TextureMesh, then moves the textured
OBJ from COLMAP's coordinates into the mission's stored ENU frame with the
transform the reconstruction itself recorded (``manifest.json``:
``transforms.recon_to_enu`` and ``gravity_leveling``), so it lines up with the
cloud in the viewer.

Before it writes anything it checks that transform: COLMAP's camera centres,
moved by it, must land on the solved cameras in ``trajectory.json``. If they
do not (another workspace, a rerun), it refuses rather than misplace a mesh.

The result is **display geometry**: a surface interpolated between observed
points, textured from the images. It is written as ``textured_mesh.obj`` (+
``.mtl`` and textures) and ``textured_mesh.zip``, with ``textured_mesh.json``
saying so. Measurements are never made on it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

CAVEAT = ("display only: photo-textured surface reconstructed by OpenMVS and "
          "interpolated between observed points; never used for measurement")
#: Camera-centre agreement (metres RMS) required before a mesh is placed.
MAX_CAMERA_RMS_M = 0.05


# ------------------------------------------------------------------ transform
def recon_to_enu(manifest: dict):
    """(scale, R, t) mapping reconstruction coordinates to stored ENU, or None.

    ``recon_to_enu`` already has any accepted levelling composed in. A cloud
    with no alignment (no GNSS) may still have been levelled about a pivot.
    """
    tr = (manifest.get("transforms") or {})
    a = tr.get("recon_to_enu")
    if a:
        return float(a["scale"]), np.asarray(a["R"], float), np.asarray(a["t"], float)
    lv = tr.get("gravity_leveling") or {}
    R = np.eye(3)
    t = np.zeros(3)
    if lv.get("applied") and not lv.get("composed_into_alignment"):
        R = np.asarray(lv["rotation"], float)
        c0 = np.asarray(lv["pivot_enu"], float)
        t = c0 - R @ c0
    return 1.0, R, t


def apply(sim, pts) -> np.ndarray:
    s, R, t = sim
    return s * np.asarray(pts, float).reshape(-1, 3) @ R.T + t


def transform_obj(src: Path, dst: Path, sim, header: list[str]) -> int:
    """Copy an OBJ, moving every ``v`` line; returns the vertex count.

    Normals (``vn``) are rotated; texture coordinates and faces are unchanged.
    """
    s, R, t = sim
    n = 0
    with open(src) as fi, open(dst, "w") as fo:
        for line in header:
            fo.write(f"# {line}\n")
        for line in fi:
            if line.startswith("v "):
                parts = line.split()
                p = apply(sim, [float(x) for x in parts[1:4]])[0]
                rest = " ".join(parts[4:])
                fo.write(f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}" + (f" {rest}" if rest else "") + "\n")
                n += 1
            elif line.startswith("vn "):
                v = R @ np.asarray([float(x) for x in line.split()[1:4]])
                v /= max(np.linalg.norm(v), 1e-12)
                fo.write(f"vn {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n")
            else:
                fo.write(line)
    return n


# ------------------------------------------------------- COLMAP camera centres
def _qvec_to_R(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def colmap_centres(sparse: Path) -> dict[str, np.ndarray]:
    """Image name -> camera centre, from images.txt or images.bin."""
    out = {}
    txt, binf = sparse / "images.txt", sparse / "images.bin"
    if txt.exists():
        # Two lines per image: the pose, then its 2-D points (often empty).
        lines = [l for l in txt.read_text().splitlines() if not l.startswith("#")]
        i = 0
        while i < len(lines):
            p = lines[i].split()
            if len(p) < 10:
                i += 1
                continue
            q, tv = np.array(p[1:5], float), np.array(p[5:8], float)
            out[p[9]] = -_qvec_to_R(q).T @ tv
            i += 2
        return out
    with open(binf, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            vals = struct.unpack("<idddddddi", f.read(64))
            q, tv = np.array(vals[1:5]), np.array(vals[5:8])
            name = b""
            while (c := f.read(1)) != b"\x00":
                name += c
            (npts,) = struct.unpack("<Q", f.read(8))
            f.read(24 * npts)
            out[name.decode()] = -_qvec_to_R(q).T @ tv
    return out


def check_alignment(sim, centres: dict[str, np.ndarray], trajectory: dict) -> dict:
    """RMS distance between moved COLMAP centres and the stored ENU cameras.

    Matched by order of frame index: the pipeline names keyframe images by
    their position, so both lists are sorted and compared pairwise when they
    have the same length.
    """
    cams = sorted(trajectory.get("cameras_enu", []), key=lambda c: c["frame_index"])
    names = sorted(centres)
    if not cams or len(cams) != len(names):
        return {"ok": False, "reason": f"{len(names)} COLMAP images against {len(cams)} "
                                       "solved cameras: not the same reconstruction"}
    moved = apply(sim, [centres[n] for n in names])
    stored = np.array([c["C"] for c in cams], float)
    rms = float(np.sqrt(np.mean(np.sum((moved - stored) ** 2, axis=1))))
    return {"ok": rms <= MAX_CAMERA_RMS_M, "camera_rms_m": rms, "n": len(names),
            "reason": None if rms <= MAX_CAMERA_RMS_M else
            f"camera centres disagree by {rms:.3f} m RMS (limit {MAX_CAMERA_RMS_M} m)"}


# ------------------------------------------------------------------- OpenMVS
def run_openmvs(bin_dir: Path, workspace: Path, work: Path, densify: bool) -> Path:
    def tool(name, *args):
        exe = bin_dir / name
        if not exe.exists():
            raise SystemExit(f"{exe} not found: point --openmvs at OpenMVS's bin directory")
        print("+", name, *args)
        subprocess.run([str(exe), *args, "-w", str(work)], check=True)

    work.mkdir(parents=True, exist_ok=True)
    tool("InterfaceCOLMAP", "-i", str(workspace), "-o", "scene.mvs",
         "--image-folder", str(workspace / "images"))
    scene = "scene.mvs"
    if densify:
        tool("DensifyPointCloud", scene)
        scene = "scene_dense.mvs"
    tool("ReconstructMesh", scene)
    mesh = scene.replace(".mvs", "_mesh.mvs")
    tool("TextureMesh", mesh, "--export-type", "obj")
    obj = work / mesh.replace(".mvs", "_texture.obj")
    if not obj.exists():
        raise SystemExit(f"TextureMesh did not write {obj}")
    return obj


def place(obj: Path, art: Path, manifest: dict, trajectory: dict, sparse: Path) -> dict:
    sim = recon_to_enu(manifest)
    check = check_alignment(sim, colmap_centres(sparse), trajectory)
    if not check["ok"]:
        raise SystemExit(f"refusing to place the mesh: {check['reason']}")
    out = art / "textured_mesh.obj"
    header = ["Drishti3D textured mesh, local ENU metres (x east, y north, z up)", CAVEAT]
    n = transform_obj(obj, out, sim, header)
    files = [out]
    for mtl in obj.parent.glob(obj.stem + "*.mtl"):
        shutil.copy(mtl, art / "textured_mesh.mtl")
        files.append(art / "textured_mesh.mtl")
        for line in mtl.read_text().splitlines():
            if line.strip().startswith("map_"):
                tex = obj.parent / line.split()[-1]
                if tex.exists():
                    shutil.copy(tex, art / tex.name)
                    files.append(art / tex.name)
    # The OBJ names its material file; keep the reference valid.
    text = out.read_text()
    out.write_text("\n".join(
        "mtllib textured_mesh.mtl" if l.startswith("mtllib") else l
        for l in text.splitlines()) + "\n")
    with zipfile.ZipFile(art / "textured_mesh.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    status = {"display_only": True, "caveat": CAVEAT, "vertices": n,
              "frame": "local ENU metres of this mission",
              "transform": {"scale": sim[0], "R": sim[1].tolist(), "t": sim[2].tolist()},
              "alignment_check": check, "files": [f.name for f in files]}
    (art / "textured_mesh.json").write_text(json.dumps(status, indent=2))
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifacts", type=Path)
    ap.add_argument("--colmap", type=Path, required=True, help="COLMAP workspace kept by the run")
    ap.add_argument("--openmvs", type=Path, help="OpenMVS bin directory")
    ap.add_argument("--obj", type=Path, help="skip OpenMVS: place this textured OBJ")
    ap.add_argument("--no-densify", action="store_true")
    a = ap.parse_args(argv)
    manifest = json.loads((a.artifacts / "manifest.json").read_text())
    trajectory = json.loads((a.artifacts / "trajectory.json").read_text())
    sparse = next((p for p in (a.colmap / "sparse" / "0", a.colmap / "sparse", a.colmap)
                   if (p / "images.bin").exists() or (p / "images.txt").exists()), None)
    if sparse is None:
        raise SystemExit(f"no COLMAP model (images.bin/txt) under {a.colmap}")
    obj = a.obj or run_openmvs(a.openmvs or Path("/usr/local/bin/OpenMVS"), a.colmap,
                               a.artifacts / "openmvs_work", not a.no_densify)
    status = place(obj, a.artifacts, manifest, trajectory, sparse)
    print(json.dumps({k: status[k] for k in ("vertices", "alignment_check")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
