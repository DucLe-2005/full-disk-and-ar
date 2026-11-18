"""Resolve an interrupted job after stopping the worker that claimed it."""

import argparse
from datetime import datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.job_progress import HEARTBEAT_STALE_SECONDS, elapsed_seconds
from app.models.pipeline_job import JobStatus, PipelineJob
from app.models.prediction import PredictionRecord


def reconcile(job_id: str) -> str:
    with SessionLocal.begin() as db:
        job = db.scalar(select(PipelineJob).where(PipelineJob.id == job_id).with_for_update())
        if job is None or job.status != JobStatus.RUNNING:
            raise ValueError("Only a running job can be reconciled.")

        now = datetime.utcnow()
        progress = job.progress
        latest = progress.heartbeat_at if progress else job.started_at
        age = elapsed_seconds(latest, now)
        if age is None or age < HEARTBEAT_STALE_SECONDS:
            raise ValueError("Wait until the job has been unresponsive for at least 90 seconds.")

        prediction_id = None
        if job.requested_at is not None:
            prediction_id = db.scalar(
                select(PredictionRecord.id).where(PredictionRecord.requested_at == job.requested_at)
            )

        job.finished_at = now
        job.prediction_id = prediction_id
        job.status = JobStatus.COMPLETED if prediction_id else JobStatus.FAILED
        job.error_message = None if prediction_id else "The worker stopped before completing this job."
        if progress:
            stages = progress.stages
            if stages and stages[-1]["status"] == "running":
                last = {
                    **stages[-1],
                    "status": "interrupted",
                }
                progress.stages = [*stages[:-1], last]
            progress.reused_prediction = bool(prediction_id)
            progress.failure_code = None if prediction_id else "worker_interrupted"

        return job.status.value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--worker-stopped", action="store_true", required=True)
    args = parser.parse_args()
    try:
        status = reconcile(args.job_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"{args.job_id}: {status}")


if __name__ == "__main__":
    main()
