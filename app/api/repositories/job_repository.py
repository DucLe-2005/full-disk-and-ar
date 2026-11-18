from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.pipeline_job import JobProgress, JobStatus, PipelineJob


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        payload: dict | None = None,
        requested_at: datetime | None = None,
    ) -> PipelineJob:
        job = PipelineJob(
            status=JobStatus.QUEUED,
            payload=payload or {},
            requested_at=requested_at,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def create_jobs(
        self,
        job_payloads: list[tuple[dict, datetime]],
    ) -> list[PipelineJob]:
        jobs = [
            PipelineJob(
                id=str(uuid4()),
                status=JobStatus.QUEUED,
                payload=payload,
                requested_at=requested_at,
            )
            for payload, requested_at in job_payloads
        ]
        self.db.add_all(jobs)
        self.db.commit()
        return jobs

    def get_job(self, job_id: str) -> PipelineJob | None:
        stmt = select(PipelineJob).options(joinedload(PipelineJob.progress)).where(PipelineJob.id == job_id)
        return self.db.scalar(stmt)

    def get_next_queued_job(self) -> PipelineJob | None:
        stmt = (
            select(PipelineJob)
            .where(PipelineJob.status == JobStatus.QUEUED)
            .order_by(PipelineJob.requested_at.asc().nullslast(), PipelineJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_active_job_for_requested_at(self, requested_at: datetime) -> PipelineJob | None:
        stmt = (
            select(PipelineJob)
            .where(PipelineJob.requested_at == requested_at)
            .where(PipelineJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .order_by(PipelineJob.created_at.asc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_active_job_requested_at_between(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> set[datetime]:
        stmt = (
            select(PipelineJob.requested_at)
            .where(PipelineJob.requested_at.between(start_at, end_at))
            .where(PipelineJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        )
        return {requested_at for requested_at in self.db.scalars(stmt) if requested_at is not None}

    def terminal_counts(self, since: datetime) -> dict[JobStatus, int]:
        return dict(self.db.execute(
            select(PipelineJob.status, func.count())
            .where(PipelineJob.finished_at >= since)
            .where(PipelineJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]))
            .group_by(PipelineJob.status)
        ).all())

    def recent_upload_failure_count(self, since: datetime) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(PipelineJob)
            .join(JobProgress)
            .where(PipelineJob.status == JobStatus.FAILED, PipelineJob.finished_at >= since)
            .where(JobProgress.failure_code == "artifact_upload_failed")
        ) or 0

    def recent_processing_times(self, since: datetime, limit: int) -> list[tuple[datetime, datetime]]:
        return self.db.execute(
            select(PipelineJob.started_at, PipelineJob.finished_at)
            .where(PipelineJob.finished_at >= since, PipelineJob.started_at.is_not(None))
            .where(PipelineJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]))
            .order_by(PipelineJob.finished_at.desc(), PipelineJob.id)
            .limit(limit)
        ).all()

    def queue_snapshot(self) -> tuple[int, datetime | None]:
        return self.db.execute(
            select(func.count(), func.min(PipelineJob.created_at))
            .select_from(PipelineJob)
            .where(PipelineJob.status == JobStatus.QUEUED)
        ).one()

    def claim_next_job(self) -> PipelineJob | None:
        job = self.get_next_queued_job()
        if job is not None:
            self.mark_running(job)
        return job

    def mark_running(self, job: PipelineJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.progress = JobProgress(heartbeat_at=job.started_at)
        self.db.commit()

    def mark_completed(self, job: PipelineJob, prediction_id: str) -> None:
        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.utcnow()
        job.prediction_id = prediction_id
        self.db.commit()

    def mark_failed(self, job: PipelineJob, error_message: str) -> None:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.utcnow()
        job.error_message = error_message[:4000]
        self.db.commit()
