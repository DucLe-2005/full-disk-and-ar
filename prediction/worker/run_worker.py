import logging
import time
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.api.repositories.job_repository import JobRepository
from app.api.repositories.prediction_repository import PredictionRepository
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.job_progress import ProgressRecorder, elapsed_seconds, heartbeat
from app.core.logging import configure_logging
from app.core.schema import create_database_schema
from app.models.pipeline_job import PipelineJob
from prediction.pipeline.persistence import build_prediction_payload, upload_pipeline_artifacts
from prediction.pipeline.run_pipeline import run_pipeline
from prediction.pipeline.stages.download import MagnetogramNotFoundError

logger = logging.getLogger(__name__)

POLL_SECONDS = 5


def _resolve_helioviewer_date(job_payload: dict | None) -> str:
    helioviewer_date = (
        (job_payload or {}).get("helioviewer_date")
        or settings.default_helioviewer_date
    )
    if not helioviewer_date:
        raise ValueError(
            "Missing helioviewer_date. Provide it in the queued job payload or "
            "set DEFAULT_HELIOVIEWER_DATE."
        )
    return helioviewer_date


def _format_helioviewer_date(value: datetime) -> str:
    return value.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _process_claimed_job(
    job_repo: JobRepository,
    prediction_repo: PredictionRepository,
    job: PipelineJob,
    progress: ProgressRecorder,
) -> None:
    with progress.stage("prepare"):
        if job.requested_at is not None:
            requested_datetime = prediction_repo.normalize_requested_at(job.requested_at)
            helioviewer_date = _format_helioviewer_date(requested_datetime)
        else:
            helioviewer_date = _resolve_helioviewer_date(job.payload)
            requested_datetime = datetime.strptime(
                helioviewer_date.strip().replace("T", " ").replace("Z", ""),
                "%Y-%m-%d %H:%M:%S",
            )
            requested_datetime = prediction_repo.normalize_requested_at(requested_datetime)
        existing = prediction_repo.get_for_requested_at(requested_datetime)
        existing_id = existing.id if existing is not None else None
    if existing_id is not None:
        job.progress.reused_prediction = True
        job_repo.mark_completed(job, existing_id)
        return

    result = run_pipeline(helioviewer_date, stage=progress.stage)
    scoring_errors = {
        score["error"]
        for region in result["ar_region_crops"]
        for score in region.get("ar_predictions", {}).values()
        if "error" in score
    }
    if scoring_errors:
        job.progress.warnings = ["Some candidate region scores could not be computed."]
        logger.warning(
            "event=region_scoring_incomplete job_id=%s errors=%r",
            progress.job_id, sorted(scoring_errors),
        )

    with progress.stage("upload"):
        artifact_payload = upload_pipeline_artifacts(requested_datetime, result)

    with progress.stage("save", commit_on_exit=False):
        prediction_payload = build_prediction_payload(str(uuid4()), result, artifact_payload)
        prediction = prediction_repo.save_prediction(prediction_payload, commit=False)
    job_repo.mark_completed(job, prediction.id)


def _failure_details(exc: Exception, stage: str | None) -> tuple[str, str]:
    if isinstance(exc, SQLAlchemyError):
        return "database_error", "The database could not complete a job operation."
    if isinstance(exc, MagnetogramNotFoundError):
        return "magnetogram_unavailable", "No magnetogram was available for the requested hour."
    if stage == "upload":
        return "artifact_upload_failed", "The prediction artifacts could not be stored."
    return "processing_failed", "The prediction could not be processed."


def process_one_job() -> bool:
    with SessionLocal() as db:
        job_repo = JobRepository(db)
        prediction_repo = PredictionRepository(db)
        job = job_repo.claim_next_job()
        if job is None:
            return False

        progress = ProgressRecorder(db, job)
        logger.info(
            "event=job_claimed job_id=%s queue_wait_seconds=%s",
            progress.job_id, elapsed_seconds(job.created_at, job.started_at),
        )
        with heartbeat(progress.job_id):
            try:
                _process_claimed_job(job_repo, prediction_repo, job, progress)
            except Exception as exc:
                stage = progress.active_stage["name"] if progress.active_stage else None
                code, message = _failure_details(exc, stage)
                logger.exception(
                    "event=job_failed job_id=%s stage=%s failure_code=%s",
                    progress.job_id, stage, code,
                )
                db.rollback()
                progress.fail(code)
                job_repo.mark_failed(job, message)
            else:
                logger.info(
                    "event=job_completed job_id=%s prediction_id=%s processing_seconds=%s",
                    progress.job_id, job.prediction_id,
                    elapsed_seconds(job.started_at, job.finished_at),
                )
        return True


def main() -> None:
    configure_logging()
    logger.info("Worker started")
    create_database_schema()

    while True:
        try:
            if process_one_job():
                continue
        except SQLAlchemyError:
            logger.exception("event=worker_database_error")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
