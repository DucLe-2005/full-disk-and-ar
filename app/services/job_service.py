from datetime import datetime, timedelta

from app.api.repositories.job_repository import JobRepository
from app.api.schemas.job import JobResponse, RecentJobsSummary
from app.api.repositories.prediction_repository import PredictionRepository
from app.core.job_progress import HEARTBEAT_STALE_SECONDS, elapsed_seconds
from app.models.pipeline_job import JobStatus, PipelineJob


class JobService:
    RANGE_RETURN_LIMIT = 100

    def __init__(self, job_repo: JobRepository, prediction_repo: PredictionRepository):
        self.job_repo = job_repo
        self.prediction_repo = prediction_repo

    def create_job(self, payload: dict | None = None) -> dict:
        payload = payload or {}
        requested_at = self._parse_requested_at(payload)
        requested_at = self.prediction_repo.normalize_requested_at(requested_at)
        normalized_payload = {
            **payload,
            "helioviewer_date": self._format_requested_at(requested_at),
        }

        existing_prediction = self.prediction_repo.get_for_requested_at(requested_at)
        if existing_prediction is not None:
            return {
                "status": "prediction_exists",
                "prediction_id": existing_prediction.id,
                "requested_at": requested_at,
                "job": None,
            }

        active_job = self.job_repo.get_active_job_for_requested_at(requested_at)
        if active_job is not None:
            return {
                "status": "job_exists",
                "prediction_id": None,
                "requested_at": requested_at,
                "job": active_job,
            }

        job = self.job_repo.create_job(
            payload=normalized_payload,
            requested_at=requested_at,
        )
        return {
            "status": "queued",
            "prediction_id": None,
            "requested_at": requested_at,
            "job": job,
        }

    def create_jobs_for_range(self, payload: dict | None = None) -> dict:
        payload = payload or {}
        start_datetime = self._parse_datetime_value(payload.get("start_time"), "start_time")
        end_datetime = self._parse_datetime_value(payload.get("end_time"), "end_time")

        start_at = self.prediction_repo.normalize_requested_at(start_datetime)
        end_at = self.prediction_repo.normalize_requested_at(end_datetime)
        if end_at < start_at:
            raise ValueError("end_time must be greater than or equal to start_time")

        requested_times = self._iter_hours(start_at, end_at)
        existing_requested_times = self.prediction_repo.list_requested_at_between(
            start_at,
            end_at,
        )
        active_job_requested_times = self.job_repo.list_active_job_requested_at_between(
            start_at,
            end_at,
        )

        job_payloads: list[tuple[dict, datetime]] = []
        for requested_at in requested_times:
            if requested_at in existing_requested_times:
                continue
            if requested_at in active_job_requested_times:
                continue
            job_payloads.append(
                (
                    {
                        "helioviewer_date": self._format_requested_at(requested_at),
                        "range_start_time": self._format_requested_at(start_at),
                        "range_end_time": self._format_requested_at(end_at),
                        "request_type": "range_backfill",
                    },
                    requested_at,
                )
            )

        queued_jobs = self.job_repo.create_jobs(job_payloads) if job_payloads else []
        returned_jobs = queued_jobs[: self.RANGE_RETURN_LIMIT]

        return {
            "status": "queued" if queued_jobs else "already_covered",
            "start_requested_at": self._format_requested_at(start_at),
            "end_requested_at": self._format_requested_at(end_at),
            "total_hours": len(requested_times),
            "queued_count": len(queued_jobs),
            "prediction_exists_count": len(existing_requested_times),
            "job_exists_count": len(active_job_requested_times - existing_requested_times),
            "returned_jobs_count": len(returned_jobs),
            "queued_jobs": [
                {
                    "job_id": job.id,
                    "requested_at": self._format_requested_at(job.requested_at),
                }
                for job in returned_jobs
                if job.requested_at is not None
            ],
        }

    def get_job(self, job_id: str) -> JobResponse | None:
        job = self.job_repo.get_job(job_id)
        if job is None:
            return None
        return self._to_response(job)

    def recent_summary(self) -> RecentJobsSummary:
        window_hours = 24
        since = datetime.utcnow() - timedelta(hours=window_hours)
        queued_count, oldest = self.job_repo.queue_snapshot()
        counts = self.job_repo.terminal_counts(since)
        durations = [
            elapsed_seconds(start, end)
            for start, end in self.job_repo.recent_processing_times(since, limit=1000)
        ]
        measured = [duration for duration in durations if duration is not None]
        return RecentJobsSummary(
            window_hours=window_hours,
            queued_count=queued_count,
            oldest_queued_at=f"{oldest.isoformat()}Z" if oldest else None,
            completed_count=counts.get(JobStatus.COMPLETED, 0),
            failed_count=counts.get(JobStatus.FAILED, 0),
            artifact_upload_failure_count=self.job_repo.recent_upload_failure_count(since),
            processing_sample_count=len(measured),
            mean_processing_seconds=round(sum(measured) / len(measured), 3) if measured else None,
        )

    def _to_response(self, job: PipelineJob) -> JobResponse:
        now = datetime.utcnow()
        progress = getattr(job, "progress", None)
        stages = progress.stages if progress else []
        active = stages[-1] if stages and stages[-1]["status"] == "running" else None
        running = job.status == JobStatus.RUNNING
        end = now if running or job.status == JobStatus.QUEUED else job.finished_at
        heartbeat = progress.heartbeat_at if progress else None
        return JobResponse(
            job_id=job.id,
            status=job.status.value,
            created_at=job.created_at.isoformat(),
            requested_at=(
                job.requested_at.isoformat()
                if job.requested_at is not None
                else None
            ),
            started_at=job.started_at.isoformat() if job.started_at is not None else None,
            finished_at=job.finished_at.isoformat() if job.finished_at is not None else None,
            prediction_id=job.prediction_id,
            error_message=job.error_message,
            payload=job.payload,
            queue_wait_seconds=elapsed_seconds(job.created_at, job.started_at or end),
            processing_seconds=elapsed_seconds(job.started_at, end),
            total_elapsed_seconds=elapsed_seconds(job.created_at, end),
            heartbeat_at=f"{heartbeat.isoformat()}Z" if heartbeat else None,
            worker_unresponsive=(
                (now - heartbeat).total_seconds() >= HEARTBEAT_STALE_SECONDS
                if heartbeat is not None and running else None
            ),
            current_stage=active["name"] if active else None,
            stages=stages,
            warnings=progress.warnings if progress else [],
            failure_code=progress.failure_code if progress else None,
            reused_prediction=progress.reused_prediction if progress else False,
        )

    def _parse_requested_at(self, payload: dict) -> datetime:
        helioviewer_date = payload.get("helioviewer_date")
        return self._parse_datetime_value(helioviewer_date, "helioviewer_date")

    def _parse_datetime_value(self, value: object, field_name: str) -> datetime:
        if not value:
            raise ValueError(f"{field_name} is required")
        return datetime.strptime(
            str(value).strip().replace("T", " ").replace("Z", ""),
            "%Y-%m-%d %H:%M:%S",
        )

    def _iter_hours(self, start_hour: datetime, end_hour: datetime) -> list[datetime]:
        hours: list[datetime] = []
        current = start_hour
        while current <= end_hour:
            hours.append(current)
            current += timedelta(hours=1)
        return hours

    def _format_requested_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")
