from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import history, predictions
from app.core.dependencies import get_job_service, get_prediction_service
from app.models.pipeline_job import JobStatus
from app.services.job_service import JobService
from app.services.prediction_service import PredictionService


REQUESTED_AT = datetime(2026, 9, 7, 13, 0, 0)


def prediction_record(**overrides):
    values = {
        "id": "prediction-1",
        "requested_at": REQUESTED_AT,
        "created_at": datetime(2026, 9, 7, 13, 2, 3),
        "global_flare_probability": 0.875,
        "localized_probabilities": [0.91],
        "predicted_class": 1,
        "jp2_object_path": "predictions/1/source.jp2",
        "full_disk_image_path": "predictions/1/full.png",
        "active_regions": [{"rank": 1, "probability": 0.91}],
        "heatmaps": [{"method_name": "Consensus", "image_path": "predictions/1/consensus.png"}],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PredictionRepo:
    def __init__(self, records=None, total=None):
        self.records = records or []
        self.total = len(self.records) if total is None else total
        self.list_args = None

    def list_predictions_page(self, **kwargs):
        self.list_args = kwargs
        return self.records, self.total

    def get_prediction(self, prediction_id):
        return next((record for record in self.records if record.id == prediction_id), None)


class JobRepo:
    def __init__(self, active_times=None):
        self.active_times = set(active_times or [])
        self.created_payloads = []

    def list_active_job_requested_at_between(self, _start, _end):
        return self.active_times

    def create_jobs(self, job_payloads):
        self.created_payloads = job_payloads
        return [
            SimpleNamespace(id=f"job-{index}", requested_at=requested_at)
            for index, (_payload, requested_at) in enumerate(job_payloads, 1)
        ]


class ExistingPredictionRepo:
    def __init__(self, existing_times=None):
        self.existing_times = set(existing_times or [])

    @staticmethod
    def normalize_requested_at(value):
        return value.replace(minute=0, second=0, microsecond=0)

    def list_requested_at_between(self, _start, _end):
        return self.existing_times


def test_prediction_service_maps_records_and_paginates():
    repo = PredictionRepo([prediction_record()], total=11)
    result = PredictionService(repo).list_prediction_history(page=2, page_size=10, predicted_class=1)

    assert result.page == 2
    assert result.total_pages == 2
    assert result.items[0].predicted_class == "flare"
    assert result.items[0].global_flare_probability == pytest.approx(0.875)
    assert result.items[0].heatmap_url == "predictions/1/consensus.png"
    assert repo.list_args["predicted_class"] == 1


def test_job_range_queues_only_uncovered_hours_and_normalizes_inputs():
    existing = {datetime(2026, 9, 7, 13)}
    active = {datetime(2026, 9, 7, 14)}
    job_repo = JobRepo(active)
    service = JobService(job_repo, ExistingPredictionRepo(existing))

    result = service.create_jobs_for_range(
        {"start_time": "2026-09-07T13:42:00Z", "end_time": "2026-09-07 15:01:00"}
    )

    assert result["total_hours"] == 3
    assert result["prediction_exists_count"] == 1
    assert result["job_exists_count"] == 1
    assert result["queued_count"] == 1
    assert job_repo.created_payloads[0][1] == datetime(2026, 9, 7, 15)
    assert job_repo.created_payloads[0][0]["helioviewer_date"] == "2026-09-07 15:00:00"


def api_client(*, prediction_service=None, job_service=None):
    api = FastAPI()
    api.include_router(history.router, prefix="/history")
    api.include_router(predictions.router, prefix="/predictions")
    if prediction_service is not None:
        api.dependency_overrides[get_prediction_service] = lambda: prediction_service
    if job_service is not None:
        api.dependency_overrides[get_job_service] = lambda: job_service
    return TestClient(api)


def test_history_endpoint_returns_documented_json_types():
    client = api_client(prediction_service=PredictionService(PredictionRepo([prediction_record()])))
    response = client.get("/history/?page=1&page_size=10&predicted_class=1")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["page"], int)
    assert isinstance(body["total"], int)
    item = body["items"][0]
    assert isinstance(item["prediction_id"], str)
    assert isinstance(item["global_flare_probability"], float)
    assert isinstance(item["localized_probabilities"], list)
    assert isinstance(item["active_regions"][0]["rank"], int)


def test_history_endpoint_validates_query_and_returns_404_for_missing_detail():
    client = api_client(prediction_service=PredictionService(PredictionRepo()))

    assert client.get("/history/?page=0").status_code == 422
    missing = client.get("/history/missing")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Prediction not found"}


def test_get_job_endpoint_serializes_datetimes_as_strings():
    job = SimpleNamespace(
        id="job-1",
        status=JobStatus.QUEUED,
        created_at=REQUESTED_AT,
        requested_at=REQUESTED_AT,
        started_at=None,
        finished_at=None,
        prediction_id=None,
        error_message=None,
        payload={"helioviewer_date": "2026-09-07 13:00:00"},
    )
    service = JobService(SimpleNamespace(get_job=lambda _job_id: job), ExistingPredictionRepo())
    response = api_client(job_service=service).get("/predictions/jobs/job-1")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["status"] == "queued"
    assert isinstance(body["created_at"], str)
    assert isinstance(body["payload"], dict)
