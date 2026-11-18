import logging
from contextlib import contextmanager
from datetime import datetime
from threading import Event, Thread
from time import monotonic

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.pipeline_job import JobProgress, PipelineJob

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
HEARTBEAT_STALE_SECONDS = 90


def elapsed_seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round(max(0.0, (end - start).total_seconds()), 3)


class ProgressRecorder:
    def __init__(self, db: Session, job: PipelineJob):
        self.db = db
        self.job = job
        self.job_id = job.id
        self.active_stage: dict | None = None
        self.started = 0.0

    def _finish_stage(self, status: str) -> None:
        if self.active_stage is None:
            return
        duration = round(monotonic() - self.started, 3)
        finished = {
            **self.active_stage,
            "status": status,
            "finished_at": f"{datetime.utcnow().isoformat()}Z",
            "duration_seconds": duration,
        }
        progress = self.job.progress
        stages = progress.stages
        if stages and stages[-1] == self.active_stage:
            stages = stages[:-1]
        progress.stages = [*stages, finished]
        logger.info(
            "event=stage_finished job_id=%s stage=%s status=%s duration_seconds=%s",
            self.job_id, finished["name"], status, duration,
        )

    @contextmanager
    def stage(self, name: str, *, commit_on_exit: bool = True):
        self.active_stage = {
            "name": name,
            "status": "running",
            "started_at": f"{datetime.utcnow().isoformat()}Z",
        }
        self.started = monotonic()
        progress = self.job.progress
        progress.stages = [*progress.stages, self.active_stage]
        self.db.commit()
        logger.info("event=stage_started job_id=%s stage=%s", self.job_id, name)
        yield
        self._finish_stage("completed")
        if commit_on_exit:
            self.db.commit()
            self.active_stage = None

    def fail(self, code: str) -> None:
        self._finish_stage("failed")
        self.job.progress.failure_code = code


@contextmanager
def heartbeat(job_id: str):
    stop = Event()

    def pulse() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                with SessionLocal.begin() as db:
                    db.execute(
                        update(JobProgress)
                        .where(JobProgress.job_id == job_id)
                        .values(heartbeat_at=datetime.utcnow())
                    )
            except Exception:
                logger.exception("event=heartbeat_failed job_id=%s", job_id)

    thread = Thread(target=pulse, name=f"heartbeat-{job_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
