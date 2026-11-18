from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    helioviewer_date: str


class CreateJobRangeRequest(BaseModel):
    start_time: str
    end_time: str


class QueuedRangeJob(BaseModel):
    job_id: str
    requested_at: str


class JobRangeResponse(BaseModel):
    status: str
    start_requested_at: str
    end_requested_at: str
    total_hours: int
    queued_count: int
    prediction_exists_count: int
    job_exists_count: int
    returned_jobs_count: int
    queued_jobs: list[QueuedRangeJob]


class JobStage(BaseModel):
    name: str
    status: Literal["running", "completed", "failed", "interrupted"]
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    requested_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    prediction_id: str | None = None
    error_message: str | None = None
    payload: dict[str, Any]
    queue_wait_seconds: float | None = None
    processing_seconds: float | None = None
    total_elapsed_seconds: float | None = None
    heartbeat_at: str | None = None
    worker_unresponsive: bool | None = None
    current_stage: str | None = None
    stages: list[JobStage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failure_code: str | None = None
    reused_prediction: bool = False


class RecentJobsSummary(BaseModel):
    window_hours: int
    queued_count: int
    oldest_queued_at: str | None
    completed_count: int
    failed_count: int
    artifact_upload_failure_count: int
    processing_sample_count: int
    mean_processing_seconds: float | None
