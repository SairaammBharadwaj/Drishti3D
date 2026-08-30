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
    __tablename__ = "measurements"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"))
    kind = Column(String)                        # point|distance|height|area
    value = Column(Float, nullable=True)
    unit = Column(String, default="m")
    points_enu = Column(JSON)
    confidence_note = Column(String, default="")
    used_inferred = Column(Boolean, default=False)
    warnings = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="measurements")
