"""Dataset adapters -> a common :class:`EvalCase`.

Each adapter reads a dataset's native on-disk layout and produces an EvalCase:
an ordered image sequence, optional intrinsics, optional ground-truth camera
centres, an optional ground-truth point cloud, and whether *real* GPS exists.

Supported layouts (auto-detected by :func:`detect_dataset`):

  odm        OpenDroneMap / ODMData -- a folder of images with GPS EXIF (or a
             sibling ``geo.txt`` / ``*_telemetry.csv``).  Optional GT cloud
             (``*.ply`` / ``*.las`` / ``*.laz``) and OpenSfM poses.
  tartanair  TartanAir P0xx trajectory -- ``image_left/*_left.png`` +
             ``pose_left.txt`` (NED tx ty tz qx qy qz qw), fixed 640x480 K.
  eth3d      ETH3D SLAM (TUM-style) -- ``rgb/`` + ``rgb.txt`` +
             ``groundtruth.txt`` + ``calibration.txt``.
  tum        Generic TUM: ``rgb/`` + ``groundtruth.txt`` (+ optional cloud /
             ``calibration.txt``).  Used for AGI2P / RTK-SLAM style aerial sets.
  synthetic  A Drishti3D synthetic scene with a ``ground_truth.json`` -- lets
             the whole harness be exercised end-to-end with no download.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
CLOUD_EXTS = {".ply", ".las", ".laz"}


@dataclass
class EvalCase:
    """A ground-truth-bearing case ready for the harness."""

    name: str
    kind: str                        # odm | tartanair | eth3d | tum | synthetic
    images: list[Path]               # ordered capture sequence
    intrinsics: dict | None = None   # {fx,fy,cx,cy} at full image resolution
    gt_centers: np.ndarray | None = None      # (N,3) GT camera centres, metric
    gps: np.ndarray | None = None    # (N,4) real GPS lat,lon,alt,acc (or None)
    gt_cloud_path: Path | None = None
    gt_cloud_pts: np.ndarray | None = None    # in-memory GT cloud (M,3), if any
    #: Exact point->surface distance function, when the scene's geometry is
    #: known analytically. Nearest-neighbour distance to a *sampled* GT cloud
    #: cannot resolve error below that cloud's own spacing: the synthetic
    #: scene's 3,750-point sample has 0.33 m median self-spacing, which floored
    #: measured accuracy at 0.78 m where the analytic value is 0.02 m. When
    #: this is set, accuracy is scored against it and the sampled cloud is used
    #: only for completeness (which asks the opposite question and is sound).
    gt_surface_distance: object | None = None
    reference_distances: list | None = None   # [{name,meters,a,b}] for dimensional error
    frame_stride: int = 1            # subsample very long sequences
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.frame_stride > 1:
            self.images = self.images[:: self.frame_stride]
            if self.gt_centers is not None:
                self.gt_centers = self.gt_centers[:: self.frame_stride]
            if self.gps is not None:
                self.gps = self.gps[:: self.frame_stride]

    @property
    def has_real_gps(self) -> bool:
        return self.gps is not None and len(self.gps) >= 2

    @property
    def n(self) -> int:
        return len(self.images)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sorted_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in IMG_EXTS)


def _quat_center_from_tum(line: str) -> np.ndarray:
    # TUM groundtruth line: [timestamp] tx ty tz qx qy qz qw -> centre = t
    parts = line.split()
    off = 1 if len(parts) >= 8 else 0
    return np.array(parts[off:off + 3], float)


def _read_calibration(path: Path) -> dict | None:
    """ETH3D/TUM calibration.txt: 'fx fy cx cy' (optionally more)."""
    if not path.exists():
        return None
    vals = [float(x) for x in path.read_text().split()[:4]]
    if len(vals) < 4:
        return None
    fx, fy, cx, cy = vals
    return {"fx": fx, "fy": fy, "cx": cx, "cy": cy}


# --------------------------------------------------------------------------- #
# EXIF GPS (ODM)
# --------------------------------------------------------------------------- #
def _exif_gps(path: Path):
    """Return (lat, lon, alt) from image EXIF, or None."""
    try:
        from PIL import Image, ExifTags
    except Exception:
        return None
    try:
        img = Image.open(path)
        exif = img.getexif()
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if not gps_ifd:
            return None
        g = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}

        def dms(v):
            d, m, s = [float(x) for x in v]
            return d + m / 60.0 + s / 3600.0

        lat = dms(g["GPSLatitude"])
        if g.get("GPSLatitudeRef", "N") in ("S", b"S"):
            lat = -lat
        lon = dms(g["GPSLongitude"])
        if g.get("GPSLongitudeRef", "E") in ("W", b"W"):
            lon = -lon
        alt = float(g.get("GPSAltitude", 0.0) or 0.0)
        if g.get("GPSAltitudeRef", 0) in (1, b"\x01"):
            alt = -alt
        return lat, lon, alt
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# adapters
# --------------------------------------------------------------------------- #
def _exif_intrinsics(path: Path) -> dict | None:
    """Recover fx, fy, cx, cy from EXIF, in pixels at the image's own resolution.

    Guessing ``0.9 * max(w, h)`` is a poor stand-in for a real camera: measured on
    the Bellus set (Canon PowerShot S110) the guess was 3643 px against a true
    2795 px -- a 30% error, which collapsed registration to 21% because both
    essential-matrix estimation and PnP depend directly on focal length.

    EXIF gives focal length in millimetres and the focal-plane resolution in
    pixels per inch, which together fix the sensor width and hence the focal
    length in pixels.
    """
    try:
        from PIL import Image, ExifTags
    except Exception:
        return None
    try:
        img = Image.open(path)
        w, h = img.size
        exif = img.getexif()
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
        tags = {ExifTags.TAGS.get(k, k): v for k, v in ifd.items()}
        base = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

        f_mm = tags.get("FocalLength") or base.get("FocalLength")
        fpx = tags.get("FocalPlaneXResolution")
        unit = tags.get("FocalPlaneResolutionUnit", 2)
        exif_w = tags.get("ExifImageWidth") or w

        if f_mm and fpx:
            # unit 2 = inches, 3 = centimetres
            per_mm = float(fpx) / (25.4 if unit in (2, None) else 10.0)
            sensor_w = float(exif_w) / per_mm
            if sensor_w > 0:
                fx = float(f_mm) * w / sensor_w
                return {"fx": fx, "fy": fx, "cx": w / 2.0, "cy": h / 2.0,
                        "width": w, "height": h, "source": "exif_focal_plane"}

        f35 = tags.get("FocalLengthIn35mmFilm")
        if f35:
            # 35 mm frame is 36 mm wide by definition
            fx = float(f35) * w / 36.0
            return {"fx": fx, "fy": fx, "cx": w / 2.0, "cy": h / 2.0,
                    "width": w, "height": h, "source": "exif_35mm_equivalent"}
    except Exception:
        return None
    return None


def _load_odm(root: Path, name: str, stride: int) -> EvalCase:
    # images live in root, or root/images
    img_dir = root / "images" if (root / "images").is_dir() else root
    images = _sorted_images(img_dir)
    if not images:
        raise ValueError(f"no images under {img_dir}")

    # GPS: prefer a geo.txt / *_telemetry.csv, else per-image EXIF
    gps = _odm_geo_txt(root) or _odm_telemetry_csv(root)
    if gps is None:
        rows = []
        for p in images:
            g = _exif_gps(p)
            rows.append([np.nan, np.nan, np.nan] if g is None else list(g))
        arr = np.array(rows, float)
        if not np.isnan(arr).any():
            gps = np.column_stack([arr, np.full(len(arr), 5.0)])  # 5 m default acc

    gt_cloud = _find_cloud(root)
    # Real intrinsics from EXIF where the camera recorded them. Without this the
    # pipeline falls back to a 0.9*max(w,h) guess, which on this dataset was 30%
    # wrong and cost most of the registration.
    intr = _exif_intrinsics(images[0]) if images else None
    return EvalCase(name=name, kind="odm", images=images, gps=gps,
                    intrinsics=intr,
                    gt_cloud_path=gt_cloud, frame_stride=stride,
                    meta={"img_dir": str(img_dir)})


def _odm_geo_txt(root: Path):
    """OpenDroneMap geo.txt: header line (SRS), then 'name lon lat alt ...'."""
    p = root / "geo.txt"
    if not p.exists():
        p = root / "images" / "geo.txt"
    if not p.exists():
        return None
    rows = []
    for i, line in enumerate(p.read_text().splitlines()):
        if i == 0 or not line.strip():
            continue
        f = line.split()
        # name x(lon) y(lat) z(alt) ...
        rows.append([float(f[2]), float(f[1]), float(f[3]), 3.0])
    return np.array(rows, float) if rows else None


def _odm_telemetry_csv(root: Path):
    for cand in (root, root / "images"):
        for p in cand.glob("*telemetry*.csv"):
            rows = []
            with open(p, newline="") as fh:
                for r in csv.DictReader(fh):
                    rows.append([float(r["latitude"]), float(r["longitude"]),
                                 float(r.get("altitude", 0) or 0),
                                 float(r.get("gps_accuracy", 5) or 5)])
            return np.array(rows, float) if rows else None
    return None


def _load_tartanair(root: Path, name: str, stride: int) -> EvalCase:
    img_dir = root / "image_left"
    pose = root / "pose_left.txt"
    images = _sorted_images(img_dir)
    centers = np.array([_quat_center_from_tum(l)
                        for l in pose.read_text().splitlines() if l.strip()])
    n = min(len(images), len(centers))
    intr = {"fx": 320.0, "fy": 320.0, "cx": 320.0, "cy": 240.0}  # TartanAir 640x480
    return EvalCase(name=name, kind="tartanair", images=images[:n],
                    gt_centers=centers[:n], intrinsics=intr, frame_stride=stride)


def _load_tum(root: Path, name: str, stride: int, kind: str) -> EvalCase:
    img_dir = root / "rgb"
    images = _sorted_images(img_dir)
    gt = root / "groundtruth.txt"
    centers = np.array([_quat_center_from_tum(l)
                        for l in gt.read_text().splitlines()
                        if l.strip() and not l.startswith("#")])
    n = min(len(images), len(centers))
    intr = _read_calibration(root / "calibration.txt")
    return EvalCase(name=name, kind=kind, images=images[:n],
                    gt_centers=centers[:n], intrinsics=intr,
                    gt_cloud_path=_find_cloud(root), frame_stride=stride)


def _load_synthetic(root: Path, name: str, stride: int) -> EvalCase:
    """A Drishti3D synthetic scene dir (has *_telemetry.csv + ground_truth.json).

    We reconstruct straight from the rendered video via the harness, so here we
    only need the GT: intrinsics + the true camera centres (ENU) from the GT
    JSON, plus the real (noisy) GPS already written by the generator.
    """
    gt = json.loads((root / "ground_truth.json").read_text())
    gps = _odm_telemetry_csv(root)
    cams = gt.get("cameras_enu") or []
    centers = np.array([c["C_enu"] for c in cams], float) if cams else None
    cloud = np.array(gt["scene_points_enu"], float) if "scene_points_enu" in gt else None
    # frames come from the pre-rendered video, not a folder -> passed via meta
    video = next(iter(root.glob("*.mp4")), None)
    # The synthetic scene's geometry is fixed across seeds (only textures shift
    # with the seed), so one analytic distance function serves every case.
    from drishti_recon import synth as _synth
    return EvalCase(name=name, kind="synthetic", images=[],
                    intrinsics=gt.get("intrinsics"), gt_centers=centers, gps=gps,
                    gt_cloud_pts=cloud,
                    gt_surface_distance=_synth.surface_distance,
                    reference_distances=gt.get("reference_distances"),
                    frame_stride=stride,
                    meta={"video": str(video) if video else None,
                          "telemetry": str(next(root.glob("*telemetry*.csv"))),
                          "gt_json": str(root / "ground_truth.json")})


def _find_cloud(root: Path) -> Path | None:
    best = None
    for p in root.rglob("*"):
        if p.suffix.lower() in CLOUD_EXTS:
            # prefer a georeferenced / dense model if named as such
            score = ("georef" in p.name.lower()) * 2 + ("dense" in p.name.lower())
            if best is None or score > best[0]:
                best = (score, p)
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# detection + public loader
# --------------------------------------------------------------------------- #
def detect_dataset(root: Path) -> str:
    root = Path(root)
    if (root / "pose_left.txt").exists() and (root / "image_left").is_dir():
        return "tartanair"
    if (root / "groundtruth.txt").exists() and (root / "rgb").is_dir():
        return "eth3d" if (root / "calibration.txt").exists() else "tum"
    if (root / "ground_truth.json").exists():
        return "synthetic"
    # ODM: any images + (geo/exif). Treat as the default for an image folder.
    img_dir = root / "images" if (root / "images").is_dir() else root
    if any(p.suffix.lower() in IMG_EXTS for p in img_dir.iterdir() if p.is_file()):
        return "odm"
    raise ValueError(f"could not detect dataset layout under {root}")


def load_case(root: str | Path, *, name: str | None = None,
              stride: int = 1, kind: str | None = None) -> EvalCase:
    root = Path(root)
    kind = kind or detect_dataset(root)
    name = name or f"{kind}:{root.name}"
    if kind == "tartanair":
        return _load_tartanair(root, name, stride)
    if kind in ("eth3d", "tum"):
        return _load_tum(root, name, stride, kind)
    if kind == "synthetic":
        return _load_synthetic(root, name, stride)
    if kind == "odm":
        return _load_odm(root, name, stride)
    raise ValueError(f"unknown dataset kind {kind!r}")
