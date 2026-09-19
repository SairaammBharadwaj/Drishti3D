"""ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (Column, String, Float, Integer, Boolean, DateTime,
                        ForeignKey, JSON, Text)
from sqlalchemy.orm import relationship

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="created")  # created|processing|done|failed
    created_at = Column(DateTime, default=_now)

    video_filename = Column(String, nullable=True)
    video_sha256 = Column(String, nullable=True)
    telemetry_filename = Column(String, nullable=True)
    intrinsics = Column(JSON, nullable=True)     # {fx,fy,cx,cy} optional

    jobs = relationship("Job", back_populates="project",
                        cascade="all, delete-orphan")
    measurements = relationship("Measurement", back_populates="project",
                                cascade="all, delete-orphan")

    @property
    def has_video(self) -> bool:
        return self.video_filename is not None

    @property
    def has_telemetry(self) -> bool:
        return self.telemetry_filename is not None


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    status = Column(String, default="queued")   # queued|running|done|failed
    stage = Column(String, default="")
    progress = Column(Float, default=0.0)
    message = Column(String, default="")
    error = Column(Text, nullable=True)
    warnings = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="jobs")


class Measurement(Base):
    """A computed geometric result, plus the verdict it was given.

    The uncertainty and acceptance columns are stored, not recomputed on read:
    a status is only meaningful alongside the artifact version and calibration
    profile that produced it, and a later reconstruction must invalidate the
    old verdict rather than silently re-answer with new geometry.
    """

    __tablename__ = "measurements"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    question_id = Column(String, ForeignKey("measurement_questions.id"),
                         nullable=True)
    kind = Column(String)                        # point|distance|height|area
    value = Column(Float, nullable=True)
    unit = Column(String, default="m")
    points_enu = Column(JSON)
    confidence_note = Column(String, default="")
    used_inferred = Column(Boolean, default=False)
    warnings = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)

    #: Propagated 1-sigma of ``value``. NULL means "not propagated"; it never
    #: means zero, and a NULL here must not read as a confident measurement.
    sigma = Column(Float, nullable=True)
    #: Half-width of the reported interval at ``interval_level``.
    interval_half_width = Column(Float, nullable=True)
    interval_level = Column(Integer, default=95)
    #: "calibrated" or "uncalibrated_sensitivity" -- what the interval means.
    interval_basis = Column(String, default="uncalibrated_sensitivity")
    #: One of drishti_recon.questions.Status.
    status = Column(String, default="estimated_only")
    #: Reason codes from drishti_recon.questions.Reason, worst first.
    status_reasons = Column(JSON, default=list)
    dominant_limitation = Column(String, nullable=True)
    threshold_result = Column(String, nullable=True)
    evidence = Column(JSON, default=dict)
    #: Identifies the reconstruction this verdict belongs to. When the project
    #: is reprocessed the artifact version changes and stored results become
    #: stale rather than quietly reinterpreted against new geometry.
    artifact_version = Column(String, nullable=True)
    calibration_profile = Column(JSON, nullable=True)

    project = relationship("Project", back_populates="measurements")
    question = relationship("MeasurementQuestion", back_populates="results")


class MeasurementQuestion(Base):
    """What the operator asked, stored apart from any answer.

    Keeping the question separate is what makes the Tolerance Lens honest: a
    changed tolerance re-evaluates the same question against the same geometry,
    and the history shows the ask changing rather than the measurement.
    """

    __tablename__ = "measurement_questions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    kind = Column(String)                        # point|distance|height|area
    label = Column(String, default="")
    points_enu = Column(JSON)                    # the selection, in ENU metres
    tolerance_m = Column(Float, nullable=True)
    interval_level = Column(Integer, default=95)
    threshold_m = Column(Float, nullable=True)
    threshold_direction = Column(String, default="at_least")
    allow_inferred = Column(Boolean, default=False)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project")
    results = relationship("Measurement", back_populates="question")
