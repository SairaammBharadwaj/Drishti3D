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


class QuestionCreate(BaseModel):
    kind: str                              # point|distance|height|area
    points: list[list[float]]              # ENU selection [[e,n,u], ...]
    tolerance_m: Optional[float] = None    # absolute, same unit as the result
    interval_level: int = 95
    threshold_m: Optional[float] = None
    threshold_direction: str = "at_least"  # at_least|at_most
    allow_inferred: bool = False
    label: str = ""
    notes: str = ""


class QuestionUpdate(BaseModel):
    """Only the requirement may change; the selection defines the question."""

    tolerance_m: Optional[float] = None
    interval_level: Optional[int] = None
    threshold_m: Optional[float] = None
    threshold_direction: Optional[str] = None
    label: Optional[str] = None


class QuestionOut(BaseModel):
    id: str
    project_id: str
    kind: str
    label: str
    points_enu: list
    tolerance_m: Optional[float]
    interval_level: int
    threshold_m: Optional[float]
    threshold_direction: str
    allow_inferred: bool
    notes: str
    created_at: datetime
    updated_at: datetime
    result: Optional[dict] = None
    guidance: list = []


class QuestionEvidenceOut(BaseModel):
    question_id: str
    support_basis: str
    endpoints: list
    note: str = ""


class RefineRequest(BaseModel):
    """How much compute the operator is willing to spend on one measurement."""

    budget_frames: int = 6      # frames actually registered and folded in
    max_decode: int = 24        # candidates decoded before giving up


class RefinementOut(BaseModel):
    id: str
    question_id: str
    parent_measurement_id: Optional[str]
    result_measurement_id: Optional[str]
    improved: bool
    n_considered: int
    n_added: int
    termination_reason: str
    wall_seconds: float
    before: dict
    after: dict
    added_frames: list
    rejected: list
    notes: list
    created_at: datetime


class ExportRequest(BaseModel):
    formats: list[str] = ["ply", "geojson", "report_html"]


class CapabilitiesOut(BaseModel):
    engines: dict
    ai_backends: list
    optional: dict
