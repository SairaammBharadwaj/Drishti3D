"""Accuracy against surveyed points, and terrain analytics on the rasters.

``/accuracy`` scores the reconstruction against GCPs and checkpoints
(``drishti_recon.accuracy``) and stores the report as ``accuracy.json``; every
block in it says whether it is independent. ``/terrain/*`` computes volume,
profile, slope and line of sight on the observed-only rasters
(``drishti_recon.terrain``). Both take points in the viewer's local ENU metres.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .. import storage

router = APIRouter(prefix="/api/projects", tags=["analysis"])

Point3 = list[float]


def _artifact(project_id: str, name: str):
    p = storage.artifacts_dir(project_id) / name
    if not p.exists():
        raise HTTPException(404, f"artifact '{name}' not available")
    return p


def _frame_and_geo(project_id: str):
    from drishti_recon.geo import ENUFrame
    geo = json.loads(_artifact(project_id, "georeference.json").read_text())
    frame = ENUFrame(**json.loads(
        _artifact(project_id, "trajectory.json").read_text())["frame"])
    return frame, geo


# -------------------------------------------------------------------- accuracy
class SurveyRow(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = None
    role: Literal["gcp", "check"] = "check"
    model_e: float
    model_n: float
    model_u: float


class AccuracyRequest(BaseModel):
    points: list[SurveyRow] = Field(min_length=1)
    #: What the survey heights are measured from: "ellipsoidal" or "msl".
    truth_vertical_datum: Literal["ellipsoidal", "msl"] = "ellipsoidal"
    truth_source: str = Field(min_length=1, max_length=300)
    allow_similarity: bool = True


def _run_accuracy(project_id: str, rows: list[dict], truth_datum: str,
                  truth_source: str, allow_similarity: bool) -> dict:
    from drishti_recon import accuracy
    from drishti_recon.position import GeoidUnavailable
    frame, geo = _frame_and_geo(project_id)
    georef = bool(geo.get("georeferenced"))
    mission_datum = geo.get("vertical_datum") or "unknown"
    try:
        pts = accuracy.points_from_rows(rows, frame if georef else None,
                                        truth_datum=truth_datum,
                                        mission_datum=mission_datum)
        rep = accuracy.evaluate(pts, allow_similarity=allow_similarity,
                                truth_source=truth_source, vertical_datum=mission_datum)
    except GeoidUnavailable as exc:
        raise HTTPException(422, f"survey heights need a geoid conversion: {exc}")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    rep["revision"] = storage.artifact_revision(project_id)
    rep["frame"] = "local ENU metres of this mission"
    rep["placement_source"] = geo.get("scale_source")
    (storage.artifacts_dir(project_id) / "accuracy.json").write_text(
        json.dumps(rep, indent=2))
    return rep


@router.post("/{project_id}/accuracy")
def post_accuracy(project_id: str, body: AccuracyRequest):
    """Score the model against surveyed points; stores and returns the report."""
    rows = [r.model_dump() for r in body.points]
    return _run_accuracy(project_id, rows, body.truth_vertical_datum,
                         body.truth_source, body.allow_similarity)


@router.post("/{project_id}/accuracy/csv")
async def post_accuracy_csv(project_id: str, file: UploadFile = File(...),
                            truth_source: str = Form(...),
                            truth_vertical_datum: Literal["ellipsoidal", "msl"] = Form("ellipsoidal"),
                            allow_similarity: bool = Form(True)):
    """The same, from a CSV: id, role, model_e/n/u and lat/lon/h, easting/northing/h/epsg or e/n/u."""
    import csv
    import io
    raw = await file.read()
    if len(raw) > 5 << 20:
        raise HTTPException(413, "checkpoint file over 5 MB")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise HTTPException(400, "checkpoint CSV must be UTF-8 text")
    if not rows:
        raise HTTPException(422, "no rows in the checkpoint CSV")
    return _run_accuracy(project_id, rows, truth_vertical_datum, truth_source,
                         allow_similarity)


@router.get("/{project_id}/accuracy")
def get_accuracy(project_id: str):
    """The stored report, flagged ``stale`` if the reconstruction has changed since."""
    rep = json.loads(_artifact(project_id, "accuracy.json").read_text())
    rep["stale"] = rep.get("revision") != storage.artifact_revision(project_id)
    return rep


# --------------------------------------------------------------------- terrain
_surface_cache: dict = {}


def _surfaces(project_id: str):
    from drishti_recon import terrain
    key = (project_id, storage.artifact_revision(project_id))
    if key not in _surface_cache:
        for k in [k for k in _surface_cache if k[0] == project_id]:
            _surface_cache.pop(k, None)
        _surface_cache[key] = terrain.Surfaces.load(_artifact(project_id, "rasters.npz"))
    return _surface_cache[key]


def _to_grid(project_id: str, enu_points) -> np.ndarray:
    """Viewer ENU -> the rasters' UTM coordinates."""
    from drishti_recon.exports import enu_to_utm
    frame, geo = _frame_and_geo(project_id)
    if not geo.get("georeferenced"):
        raise HTTPException(409, "the mission is not georeferenced: it has no rasters")
    p = np.asarray(enu_points, float).reshape(-1, 3)
    utm, epsg = enu_to_utm(frame, p)
    s = _surfaces(project_id)
    if epsg != s.epsg:
        raise HTTPException(409, f"rasters are in EPSG:{s.epsg}, the frame in EPSG:{epsg}")
    return utm


def _context(project_id: str, out: dict) -> dict:
    summary = json.loads(_artifact(project_id, "rasters.json").read_text())
    out["crs"] = summary.get("crs")
    out["vertical_datum"] = summary.get("vertical_datum")
    out["cell_size_m"] = summary.get("cell_size_m")
    out["revision"] = storage.artifact_revision(project_id)
    out["evidence"] = "observed points only; empty cells are unknown, never interpolated"
    return out


class PolygonRequest(BaseModel):
    polygon: list[Point3] = Field(min_length=3, max_length=500)


class VolumeRequest(PolygonRequest):
    base: Literal["edge", "lowest", "fixed"] = "edge"
    #: For base="fixed": the base height as local ENU up, metres (the viewer's
    #: z), converted to the rasters' heights at the polygon's centroid.
    base_z: Optional[float] = None


class LineRequest(BaseModel):
    a: Point3
    b: Point3
    step_m: Optional[float] = Field(default=None, gt=0)


class LosRequest(BaseModel):
    observer: Point3
    target: Point3
    observer_height_m: float = Field(default=1.7, ge=0, le=500)
    target_height_m: float = Field(default=0.0, ge=0, le=500)
    #: Use the picked points' own heights rather than the DSM under them.
    use_point_heights: bool = False


@router.post("/{project_id}/terrain/volume")
def terrain_volume(project_id: str, body: VolumeRequest):
    from drishti_recon import terrain
    utm = _to_grid(project_id, body.polygon)
    base_z = None
    if body.base_z is not None:
        c = np.asarray(body.polygon, float)[:, :2].mean(axis=0)
        base_z = float(_to_grid(project_id, [[c[0], c[1], body.base_z]])[0, 2])
    try:
        out = terrain.volume(_surfaces(project_id), utm[:, :2], base=body.base,
                             base_z=base_z)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return _context(project_id, out)


@router.post("/{project_id}/terrain/profile")
def terrain_profile(project_id: str, body: LineRequest):
    from drishti_recon import terrain
    utm = _to_grid(project_id, [body.a, body.b])
    out = terrain.profile(_surfaces(project_id), utm[0], utm[1], step=body.step_m)
    return _context(project_id, out)


@router.post("/{project_id}/terrain/slope")
def terrain_slope(project_id: str, body: PolygonRequest):
    from drishti_recon import terrain
    utm = _to_grid(project_id, body.polygon)
    try:
        out = terrain.slope(_surfaces(project_id), utm[:, :2])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return _context(project_id, out)


@router.post("/{project_id}/terrain/los")
def terrain_los(project_id: str, body: LosRequest):
    from drishti_recon import terrain
    utm = _to_grid(project_id, [body.observer, body.target])
    a, b = (utm[0], utm[1]) if body.use_point_heights else (utm[0, :2], utm[1, :2])
    out = terrain.line_of_sight(_surfaces(project_id), a, b,
                                observer_height=body.observer_height_m,
                                target_height=body.target_height_m)
    return _context(project_id, out)


# ----------------------------------------------------------------------- geoid
system = APIRouter(prefix="/api/system", tags=["system"])


@system.get("/geoid")
def geoid_status():
    """Whether heights above sea level can be given on this machine.

    Probes EGM2008 at a fixed point. Without the grid the answer is
    ``available: false`` with the install instruction: sea-level heights are
    then refused, never replaced by the ellipsoidal height.
    """
    from drishti_recon import position
    lat, lon = 12.9716, 77.5946
    try:
        H = float(position.orthometric_height(lat, lon, 0.0)[0])
    except position.GeoidUnavailable as exc:
        return {"available": False, "model": "EGM2008", "grid": position.EGM2008_GRID,
                "detail": str(exc)}
    return {"available": True, "model": "EGM2008", "grid": position.EGM2008_GRID,
            "probe": {"lat": lat, "lon": lon, "geoid_height_m": -H}}
