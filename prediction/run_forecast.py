"""Run and publish one UTC forecast, or replay a range of forecast slots."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import text

from app.api.repositories.prediction_repository import PredictionRepository
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.core.schema import create_database_schema

logger = logging.getLogger(__name__)
HOUR = timedelta(hours=1)
EPOCH = datetime(1970, 1, 1)
LOCK_NAMESPACE = 176368431


def current_hour() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def parse_slot(value: str, *, end_of_day: bool = False) -> datetime:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        slot = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if slot.tzinfo is not None:
            slot = slot.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        slot = datetime.combine(day, datetime.min.time()).replace(hour=23 if end_of_day else 0)
    if slot.minute or slot.second or slot.microsecond:
        raise ValueError("Forecast slots must fall on a whole UTC hour")
    return slot


def _run_pipeline(slot: datetime, directory: Path, stage) -> dict:
    from prediction.pipeline.run_pipeline import run_pipeline

    return run_pipeline(slot.isoformat(), data_root=directory, stage=stage)


def predict_hour(slot: datetime, *, is_backfill: bool) -> str:
    """Publish a normalized UTC slot once, serializing concurrent attempts in Postgres."""
    from prediction.pipeline.persistence import build_prediction_payload, upload_pipeline_artifacts

    @contextmanager
    def stage(name: str):
        started = monotonic()
        try:
            yield
        except Exception:
            logger.error("event=stage_failed slot=%sZ stage=%s", slot.isoformat(), name)
            raise
        else:
            logger.info(
                "event=stage_completed slot=%sZ stage=%s seconds=%.3f",
                slot.isoformat(), name, monotonic() - started,
            )

    with SessionLocal.begin() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :hour)"),
                {"namespace": LOCK_NAMESPACE, "hour": (slot - EPOCH) // HOUR},
            )
        repository = PredictionRepository(db)
        if repository.exists_for_requested_at(slot):
            return "existing"

        with TemporaryDirectory(prefix="flare-forecast-") as directory:
            result = _run_pipeline(slot, Path(directory), stage)
            scoring_errors = {
                score["error"]
                for region in result["ar_region_crops"]
                for score in region.get("ar_predictions", {}).values()
                if "error" in score
            }
            if scoring_errors:
                logger.warning(
                    "event=region_scoring_incomplete slot=%sZ errors=%r",
                    slot.isoformat(), sorted(scoring_errors),
                )
            with stage("upload"):
                artifacts = upload_pipeline_artifacts(slot, result)
            with stage("save"):
                payload = build_prediction_payload(str(uuid4()), result, artifacts)
                repository.save_prediction({**payload, "is_backfill": is_backfill}, commit=False)
    return "published"


def run_range(
    start: datetime, end: datetime, *, live_slot: datetime, attempts: int, retry_delay: int
) -> int:
    counts = {"published": 0, "existing": 0, "failed": 0}
    slot = start
    while slot <= end:
        for attempt in range(1, attempts + 1):
            try:
                status = predict_hour(slot, is_backfill=slot < live_slot)
            except Exception:
                logger.exception(
                    "event=forecast_attempt_failed slot=%sZ attempt=%d attempts=%d",
                    slot.isoformat(), attempt, attempts,
                )
                if attempt < attempts:
                    sleep(retry_delay)
                    continue
                status = "failed"
            counts[status] += 1
            logger.info("event=forecast_result slot=%sZ status=%s", slot.isoformat(), status)
            break
        slot += HOUR
    logger.info("event=forecast_summary counts=%s", counts)
    return counts["failed"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--current-hour", action="store_true", help="Use the current UTC hour")
    mode.add_argument("--hour", help="Run one explicit UTC slot")
    mode.add_argument("--start-time", help="First UTC slot in an inclusive range")
    parser.add_argument("--end-time", help="Last UTC slot. A date includes its final hour")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--retry-delay", type=int, default=60, help="Seconds between retries")
    args = parser.parse_args()
    if bool(args.start_time) != bool(args.end_time):
        parser.error("--start-time and --end-time must be provided together")
    if args.attempts < 1 or args.retry_delay < 0:
        parser.error("--attempts must be positive and --retry-delay must be nonnegative")
    now = current_hour()
    try:
        start = now if args.current_hour else parse_slot(args.hour or args.start_time)
        end = parse_slot(args.end_time, end_of_day=True) if args.end_time else start
    except ValueError as exc:
        parser.error(str(exc))
    if start > end or end > now:
        parser.error("Choose an ordered range that ends at or before the current UTC hour")

    configure_logging()
    create_database_schema()
    failures = run_range(start, end, live_slot=now, attempts=args.attempts, retry_delay=args.retry_delay)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
