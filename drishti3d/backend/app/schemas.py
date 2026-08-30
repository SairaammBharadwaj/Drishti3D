"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class Intrinsics(BaseModel):
    fx: float
    fy: float
    cx: float
    cy: float


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    has_video: bool
    has_telemetry: bool
    video_filename: Optional[str] = None
    telemetry_filename: Optional[str] = None
    intrinsics: Optional[dict] = None

    class Config:
        from_attributes = True


class ProcessRequest(BaseModel):
    preset: str = "balanced"          # fast|balanced|quality
    mask_backend: str = "none"        # none|optical_flow|semantic
    do_mesh: bool = True
    engine: str = "opencv"            # opencv|colmap|auto
    densify: str = "none"             # none|depth (monocular depth-prior fusion)
    intrinsics: Optional[Intrinsics] = None


class JobOut(BaseModel):
    id: str
    project_id: str
    status: str
    stage: str
    progress: float
    message: str
    error: Optional[str] = None
    warnings: list = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MeasurementCreate(BaseModel):
    kind: str                         # point|distance|height|area
    points: list[list[float]]         # ENU points [[e,n,u], ...]
    allow_inferred: bool = False


class MeasurementOut(BaseModel):
    id: str
    project_id: str
    kind: str
    value: Optional[float]
    unit: str
    points_enu: list
    confidence_note: str
    used_inferred: bool
    warnings: list
    created_at: datetime

    class Config:
        from_attributes = True


class ExportRequest(BaseModel):
    formats: list[str] = ["ply", "geojson", "report_html"]


class CapabilitiesOut(BaseModel):
    engines: dict
    ai_backends: list
    optional: dict
