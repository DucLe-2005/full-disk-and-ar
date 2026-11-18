from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Enum as SqlEnum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        Index("ix_pipeline_jobs_status_created_at", "status", "created_at"),
        Index("ix_pipeline_jobs_status_requested_at", "status", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[JobStatus] = mapped_column(SqlEnum(JobStatus), nullable=False, default=JobStatus.QUEUED)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    prediction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    progress: Mapped[JobProgress | None] = relationship()
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobProgress(Base):
    __tablename__ = "pipeline_job_progress"

    job_id: Mapped[str] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="CASCADE"), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stages: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reused_prediction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
