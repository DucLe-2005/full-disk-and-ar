from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas.job import JobResponse, RecentJobsSummary
from app.core.dependencies import get_job_service
from app.services.job_service import JobService

router = APIRouter()


@router.get("/jobs/summary", response_model=RecentJobsSummary)
def recent_jobs_summary(service: JobService = Depends(get_job_service)) -> RecentJobsSummary:
    return service.recent_summary()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
