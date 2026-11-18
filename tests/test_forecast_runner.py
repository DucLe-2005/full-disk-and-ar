from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.api.repositories.prediction_repository import PredictionRepository
from app.core import schema
from prediction import run_forecast
from prediction.pipeline import MagnetogramNotFoundError, persistence


SLOT = datetime(2026, 1, 1, 15)


def test_retry_after_failed_upload_publishes_once(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(schema, "engine", engine)
    schema.create_database_schema()
    sessions = sessionmaker(engine)
    monkeypatch.setattr(run_forecast, "SessionLocal", sessions)

    runs = []
    uploads = []
    observed_at = SLOT - timedelta(minutes=6)

    def simulate_pipeline(slot, directory, _stage):
        runs.append(slot)
        image = directory / "disk.jpg"
        image.write_bytes(b"test artifact")
        return {
            "jpg_path": str(image),
            "prediction_datetime": slot.isoformat(),
            "observed_at": observed_at.isoformat(),
            "prediction": {"p_flare": 0.7, "pred_class": 1},
            "ar_region_crops": [],
        }

    def fail_first_upload(path, key):
        assert Path(path).is_file()
        uploads.append(key)
        if len(uploads) == 1:
            raise OSError("temporary upload failure")
        return key

    monkeypatch.setattr(run_forecast, "_run_pipeline", simulate_pipeline)
    monkeypatch.setattr(persistence, "upload_file_to_minio", fail_first_upload)

    with pytest.raises(OSError, match="temporary upload failure"):
        run_forecast.predict_hour(SLOT, is_backfill=True)
    with sessions() as db:
        assert not PredictionRepository(db).exists_for_requested_at(SLOT)

    assert run_forecast.predict_hour(SLOT, is_backfill=True) == "published"
    assert run_forecast.predict_hour(SLOT, is_backfill=True) == "existing"
    assert runs == [SLOT, SLOT]
    key = "predictions/2026/01/01/15/full_disk/disk.jpg"
    assert uploads == [key, key]
    with sessions() as db:
        stored = PredictionRepository(db).get_for_requested_at(SLOT)
        assert stored.observed_at == observed_at
        assert stored.full_disk_image_path == key
        assert stored.is_backfill


def test_range_retries_same_slot_and_continues_after_failure(monkeypatch):
    calls = []
    next_slot = SLOT + run_forecast.HOUR

    def predict(slot, *, is_backfill):
        calls.append((slot, is_backfill))
        if slot == SLOT:
            raise RuntimeError("missing image")
        return "published"

    monkeypatch.setattr(run_forecast, "predict_hour", predict)
    assert run_forecast.run_range(
        SLOT, next_slot, live_slot=next_slot, attempts=2, retry_delay=0
    ) == 1
    assert calls == [(SLOT, True), (SLOT, True), (next_slot, False)]


def test_schema_adds_forecast_metadata_to_existing_table(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(schema, "engine", engine)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE predictions (id VARCHAR PRIMARY KEY)"))
        db.execute(text("INSERT INTO predictions VALUES ('old')"))

    schema.create_database_schema()
    schema.create_database_schema()

    assert {column["name"] for column in inspect(engine).get_columns("predictions")} == {
        "id", "observed_at", "is_backfill",
    }
    with engine.connect() as db:
        assert db.execute(text("SELECT * FROM predictions")).one() == ("old", None, None)


@pytest.mark.parametrize(
    ("error", "allow_missing", "failures"),
    [
        (MagnetogramNotFoundError("No eligible image"), True, 0),
        (MagnetogramNotFoundError("No eligible image"), False, 1),
        (OSError("Upload failed"), True, 1),
    ],
)
def test_range_can_tolerate_missing_images_only(monkeypatch, error, allow_missing, failures):
    def predict(_slot, *, is_backfill):
        raise error

    monkeypatch.setattr(run_forecast, "predict_hour", predict)
    assert run_forecast.run_range(
        SLOT, SLOT, live_slot=SLOT, attempts=1, retry_delay=0,
        allow_missing_magnetograms=allow_missing,
    ) == failures
