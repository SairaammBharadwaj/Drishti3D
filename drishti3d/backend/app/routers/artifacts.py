"""Artifact access: quality, trajectory, model (viewer), files and exports."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project
from ..schemas import ExportRequest
from .. import cloud_pack, storage

router = APIRouter(prefix="/api/projects", tags=["artifacts"])

# artifact key -> filename produced by the pipeline
_EXPORT_FILES = {
    "ply": "point_cloud.ply",
    "las": "point_cloud.las",
    "mesh_glb": "mesh.glb",
    "geojson": "trajectory.geojson",
    "trajectory_csv": "trajectory.csv",
    "report_json": "quality_report.json",
    "report_html": "quality_report.html",
    "viewer": "viewer.json",
    # Without this, every cloud export leaves as unreferenced local metres and
    # the origin has to be communicated out of band.
    "georeference": "georeference.json",
    # Per-hole record of the inferred fill: what each surface rests on.
    "fill": "fill.json",
    # Raster products (drishti_recon.rasters), UTM GeoTIFFs.
    "dsm_tif": "dsm.tif",
    "dtm_tif": "dtm.tif",
    "ortho_tif": "ortho.tif",
    "sigma_tif": "sigma.tif",
    "landcover_tif": "landcover.tif",
}

#: Preview images rasters.py writes, by the name the API serves them under.
_RASTER_PREVIEWS = {"ortho": "ortho_preview.png", "dsm": "dsm_preview.png",
                    "dtm": "dtm_preview.png", "landcover": "landcover_preview.png"}

#: Provenance code of fill points (``Provenance.INFERRED_FILL``). Written here
#: rather than imported so the API does not load the reconstruction package.
_FILL_CODE = 6
#: Fill points added to the capped JSON preview, at most.
_FILL_PREVIEW_MAX = 40000


def _load_fill(project_id: str):
    """(points, colors) of the inferred hole fill, or None if there is none."""
    p = storage.artifacts_dir(project_id) / "fill.npz"
    if not p.exists():
        return None
    d = np.load(p)
    return d["points"], d["colors"]


def _artifact(project_id: str, filename: str) -> Path:
    p = storage.artifacts_dir(project_id) / filename
    if not p.exists():
        raise HTTPException(404, f"artifact '{filename}' not available yet")
    return p


def _load_json(project_id: str, filename: str):
    return json.loads(_artifact(project_id, filename).read_text())


@router.get("/{project_id}/quality")
def get_quality(project_id: str, db: Session = Depends(get_db)):
    q = _load_json(project_id, "quality_report.json")
    # `performance.processing_time_s` is the sum of stage timings taken before
    # exports run, so it understates the job (653.6 s against 733.7 s on
    # DJI_1003) and put "0.96x video" on screen for a run that took 1.08x.
    # timing.json is one monotonic clock around the whole run; add it rather
    # than replace the stage sum, which remains what it says it is.
    timing = storage.artifacts_dir(project_id) / "timing.json"
    if timing.exists():
        try:
            t = json.loads(timing.read_text())
        except ValueError:
            t = {}
        if t.get("wall_s") is not None:
            perf = q.setdefault("performance", {})
            perf["end_to_end_s"] = t["wall_s"]
            perf["end_to_end_ratio"] = t.get("wall_over_video")
    return q


@router.get("/{project_id}/trajectory")
def get_trajectory(project_id: str):
    return _load_json(project_id, "trajectory.json")


@router.get("/{project_id}/model")
def get_model(project_id: str, fill: bool = True):
    """Viewer point-cloud payload (downsampled, ENU + provenance).

    The inferred hole fill, when there is one, is appended with its own
    provenance code, zero confidence, and in proportion to how much of the
    full cloud it is -- so the preview looks like the full view. ``fill=false``
    returns only what was observed.
    """
    v = _load_json(project_id, "viewer.json")
    f = _load_fill(project_id) if fill else None
    if f is not None and len(f[0]):
        fp, fc = f
        n_cloud = len(np.load(_artifact(project_id, "cloud.npz"), mmap_mode="r")["provenance"])
        ratio = len(v["points"]) / max(n_cloud, 1)
        m = min(len(fp), _FILL_PREVIEW_MAX, max(1, int(round(len(fp) * ratio))))
        keep = np.random.default_rng(0).choice(len(fp), m, replace=False)
        v["points"] += np.round(fp[keep].astype(float), 3).tolist()
        v["colors"] += fc[keep].astype(int).tolist()
        v["confidence"] += [0.0] * m
        v["provenance"] += [_FILL_CODE] * m
        v["fill_count"] = m
    return JSONResponse(v)


#: Header layout for the full-cloud binary. Little-endian throughout, which is
#: what every browser this runs in uses natively.
_CLOUD_MAGIC = b"D3DC"
_CLOUD_VERSION = 1


@router.get("/{project_id}/model.bin")
def get_model_binary(project_id: str, fill: bool = True):
    """The complete point cloud, packed, with no downsampling.

    `viewer.json` caps at 120,000 points because JSON is ruinous for this: a
    2.69 M point cloud is about 148 MB as text, against 6.6 MB for the capped
    preview. The cap was never a rendering limit -- three.js draws millions of
    points comfortably -- it was a transfer and parse limit, and the fix is to
    stop sending numbers as text.

    Packed little-endian:

        magic   4 bytes  'D3DC'
        version 4 bytes  uint32
        count   4 bytes  uint32
        xyz     count * 3 * float32   ENU metres
        rgb     count * 3 * uint8
        prov    count * 1 * uint8     Provenance enum

    That is 16 bytes per point: about 43 MB for the same cloud, a third of the
    JSON and no parsing beyond a typed-array view. The capped JSON stays as the
    first paint; this is what "show every point" loads.

    The inferred hole fill is appended after the cloud with provenance
    ``INFERRED_FILL`` (``fill=false`` leaves it out); ``X-Fill-Count`` says how
    many of the points it is.
    """
    import io
    pts, cols, prov, n_fill = _full_cloud(project_id, fill)
    n = len(pts)

    buf = io.BytesIO()
    buf.write(_CLOUD_MAGIC)
    buf.write(np.uint32(_CLOUD_VERSION).tobytes())
    buf.write(np.uint32(n).tobytes())
    buf.write(pts.tobytes())
    buf.write(cols.tobytes())
    buf.write(prov.tobytes())
    data = buf.getvalue()
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Length": str(len(data)),
                 "X-Point-Count": str(n),
                 "X-Fill-Count": str(n_fill),
                 "Cache-Control": "no-cache"})


def _full_cloud(project_id: str, fill: bool):
    """Every point the viewer shows: the cloud, then the inferred fill."""
    d = np.load(_artifact(project_id, "cloud.npz"))
    pts = np.ascontiguousarray(d["points"], dtype="<f4")
    n = len(pts)
    cols = np.ascontiguousarray(
        d["colors"] if "colors" in d.files else np.full((n, 3), 200),
        dtype=np.uint8)
    prov = np.ascontiguousarray(
        d["provenance"] if "provenance" in d.files else np.zeros(n),
        dtype=np.uint8)
    n_fill = 0
    f = _load_fill(project_id) if fill else None
    if f is not None and len(f[0]):
        n_fill = len(f[0])
        pts = np.concatenate([pts, np.asarray(f[0], dtype="<f4")])
        cols = np.concatenate([cols, np.asarray(f[1], dtype=np.uint8)])
        prov = np.concatenate([prov, np.full(n_fill, _FILL_CODE, np.uint8)])
    return pts, cols, prov, n_fill


def pack_for(project_id: str, fill: bool = True) -> bytes:
    """The cloud as model.pack sends it, built once per artifact revision."""
    key = (project_id, storage.artifact_revision(project_id), fill)

    def build():
        pts, cols, prov, _ = _full_cloud(project_id, fill)
        return cloud_pack.encode(pts, cols, prov)
    return cloud_pack.cached(key, build)


@router.get("/{project_id}/model.pack")
def get_model_pack(project_id: str, fill: bool = True):
    """The same points as model.bin, 2.7x smaller: see cloud_pack.py.

    For display over a slow link. Positions are quantised to about 2 cm on a
    1.4 km scene; measurements never use them, they are made on the
    full-precision cloud here.
    """
    data = pack_for(project_id, fill)
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Length": str(len(data))})


#: What a mission's placement on the earth rests on, by georeference.json's
#: scale_source. The coordinates are only as good as this.
_PLACEMENT_NOTES = {
    "rtk": "Placed by RTK GNSS. Where checked against same-flight LiDAR, "
           "placement was within 0.08-0.28 m horizontally (DEC-044).",
    "gps": "Placed by GPS without RTK. The absolute position can be off by "
           "metres or more; the Austin missions' placement is unverified "
           "(DEC-045). Distances and heights within the scene are unaffected.",
}


@router.get("/{project_id}/point_info")
def point_info(project_id: str, e: float, n: float, u: float):
    """Every coordinate form of one picked point (``drishti_recon.position``).

    Latitude/longitude, UTM, MGRS, and the heights the mission's vertical
    datum supports: ellipsoidal and above sea level (EGM2008) when the
    telemetry said which it was, none when it did not. A sidecar written
    before the datum was recorded counts as unknown. A mission that is not
    georeferenced has no position to give.
    """
    from drishti_recon import position
    from drishti_recon.geo import ENUFrame
    geo = _load_json(project_id, "georeference.json")
    frame = ENUFrame(**_load_json(project_id, "trajectory.json")["frame"])
    out = position.describe(frame, [e, n, u],
                            georeferenced=bool(geo.get("georeferenced")),
                            vertical_datum=geo.get("vertical_datum") or "unknown")
    if out.get("georeferenced"):
        src = geo.get("scale_source")
        out["placement_source"] = src
        out["placement_note"] = _PLACEMENT_NOTES.get(
            src, f"Placement source '{src}' has no recorded accuracy.")
        out["vertical_datum_basis"] = geo.get("vertical_datum_basis")
    return out


@router.get("/{project_id}/rasters")
def get_rasters(project_id: str):
    """The raster products' summary and which preview images exist.

    404 when the mission has none: it is not georeferenced, or predates them
    and ``scripts/build_rasters.py`` has not been run for it.
    """
    summary = _load_json(project_id, "rasters.json")
    d = storage.artifacts_dir(project_id)
    previews = [k for k, f in _RASTER_PREVIEWS.items() if (d / f).exists()]
    return {"summary": summary, "previews": previews}


@router.get("/{project_id}/rasters/{name}.png")
def get_raster_preview(project_id: str, name: str):
    if name not in _RASTER_PREVIEWS:
        raise HTTPException(404, "unknown raster preview")
    return FileResponse(_artifact(project_id, _RASTER_PREVIEWS[name]),
                        media_type="image/png")


@router.get("/{project_id}/keyframes")
def get_keyframes(project_id: str):
    return _load_json(project_id, "keyframes.json")


@router.get("/{project_id}/frame_metrics")
def get_frame_metrics(project_id: str):
    return _load_json(project_id, "frame_metrics.json")


@router.get("/{project_id}/exports")
def list_exports(project_id: str):
    d = storage.artifacts_dir(project_id)
    available = {k: v for k, v in _EXPORT_FILES.items() if (d / v).exists()}
    return {"available": available}


@router.get("/{project_id}/exports/{key}")
def download_export(project_id: str, key: str):
    if key not in _EXPORT_FILES:
        raise HTTPException(404, "unknown export")
    p = _artifact(project_id, _EXPORT_FILES[key])
    return FileResponse(p, filename=p.name)
