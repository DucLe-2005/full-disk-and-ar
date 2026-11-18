from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.repositories.job_repository import JobRepository
from app.api.repositories.prediction_repository import PredictionRepository
from app.core.database import Base
from app.models.pipeline_job import JobStatus
from app.services.job_service import JobService
from app.core.job_progress import ProgressRecorder


@pytest.fixture
def repositories():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield JobRepository(db), PredictionRepository(db)


def test_running_job_reports_stage_and_stale_heartbeat(repositories):
    jobs, predictions = repositories
    queued = jobs.create_job()
    assert JobService(jobs, predictions).get_job(queued.id).worker_unresponsive is None

    job = jobs.claim_next_job()
    recorder = ProgressRecorder(jobs.db, job)
    with recorder.stage("full_disk"):
        response = JobService(jobs, predictions).get_job(job.id)
        assert response.current_stage == "full_disk"
        assert response.queue_wait_seconds >= 0
        assert response.worker_unresponsive is False
        job.progress.heartbeat_at = datetime.utcnow() - timedelta(minutes=5)
        jobs.db.commit()
        assert JobService(jobs, predictions).get_job(job.id).worker_unresponsive is True
        assert job.status == JobStatus.RUNNING

    response = JobService(jobs, predictions).get_job(job.id)
    assert response.current_stage is None
    assert response.stages[0].status == "completed"
    assert response.stages[0].duration_seconds >= 0


def test_failed_save_rolls_back_prediction_and_preserves_stage_history(repositories):
    jobs, predictions = repositories
    jobs.create_job()
    job = jobs.claim_next_job()
    recorder = ProgressRecorder(jobs.db, job)
    with recorder.stage("upload"):
        pass
    with pytest.raises(RuntimeError), recorder.stage("save", commit_on_exit=False):
        predictions.save_prediction(
            {
                "id": "prediction-1",
                "requested_at": datetime.utcnow(),
                "global_flare_probability": 0.5,
                "predicted_class": 1,
            },
            commit=False,
        )
        raise RuntimeError("Simulated interrupted save")

    jobs.db.rollback()
    recorder.fail("database_error")
    jobs.mark_failed(job, "Could not save")
    assert predictions.get_prediction("prediction-1") is None
    service = JobService(jobs, predictions)
    response = service.get_job(job.id)
    assert response.status == "failed"
    assert response.failure_code == "database_error"
    assert [stage.status for stage in response.stages] == ["completed", "failed"]
    assert service.recent_summary().failed_count == 1
    assert service.recent_summary().processing_sample_count == 1


def test_completed_job_links_prediction_and_commits_final_stage(repositories):
    jobs, predictions = repositories
    jobs.create_job()
    job = jobs.claim_next_job()
    recorder = ProgressRecorder(jobs.db, job)
    with recorder.stage("save", commit_on_exit=False):
        prediction = predictions.save_prediction(
            {
                "id": "prediction-1",
                "requested_at": datetime.utcnow(),
                "global_flare_probability": 0.5,
                "predicted_class": 1,
            },
            commit=False,
        )
    jobs.mark_completed(job, prediction.id)

    assert predictions.get_prediction("prediction-1") is not None
    response = JobService(jobs, predictions).get_job(job.id)
    assert response.status == "completed"
    assert response.prediction_id == "prediction-1"
    assert response.stages[-1].status == "completed"
    assert response.total_elapsed_seconds >= response.processing_seconds


def test_schema_adds_progress_to_existing_database(monkeypatch):
    from app.core import schema
    from app.models.pipeline_job import PipelineJob

    engine = create_engine("sqlite://")
    PipelineJob.__table__.create(engine)
    with Session(engine) as db:
        legacy_id = JobRepository(db).create_job().id

    monkeypatch.setattr(schema, "engine", engine)
    schema.create_database_schema()

    with Session(engine) as db:
        response = JobService(JobRepository(db), PredictionRepository(db)).get_job(legacy_id)
        assert response.status == "queued"
        assert response.stages == []
        assert response.heartbeat_at is None


def test_reconciliation_requires_stale_heartbeat(monkeypatch, repositories):
    from sqlalchemy.orm import sessionmaker

    from app.scripts import reconcile_job

    jobs, _ = repositories
    jobs.create_job()
    job = jobs.claim_next_job()
    job_id = job.id
    monkeypatch.setattr(reconcile_job, "SessionLocal", sessionmaker(jobs.db.get_bind()))

    with pytest.raises(ValueError, match="unresponsive"):
        reconcile_job.reconcile(job_id)

    job.progress.heartbeat_at = datetime.utcnow() - timedelta(minutes=5)
    jobs.db.commit()
    assert reconcile_job.reconcile(job_id) == "failed"
    assert jobs.get_job(job_id).progress.failure_code == "worker_interrupted"

    with pytest.raises(ValueError, match="Only a running job"):
        reconcile_job.reconcile(job_id)
