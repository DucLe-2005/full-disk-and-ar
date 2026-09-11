from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.prediction import PredictionRecord


class PredictionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_predictions_page(
        self,
        *,
        page: int,
        page_size: int,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        predicted_class: int | None = None,
    ) -> tuple[list[PredictionRecord], int]:
        filters = []
        if start_at is not None:
            filters.append(PredictionRecord.requested_at >= start_at)
        if end_at is not None:
            filters.append(PredictionRecord.requested_at <= end_at)
        if predicted_class is not None:
            filters.append(PredictionRecord.predicted_class == predicted_class)

        count_stmt = select(func.count()).select_from(PredictionRecord).where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)

        stmt = (
            select(PredictionRecord)
            .where(*filters)
            .order_by(PredictionRecord.requested_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(stmt)), total

    def get_latest_prediction(self) -> PredictionRecord | None:
        stmt = (
            select(PredictionRecord)
            .order_by(PredictionRecord.requested_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_prediction(self, prediction_id: str) -> PredictionRecord | None:
        return self.db.get(PredictionRecord, prediction_id)

    def normalize_requested_at(self, requested_at: datetime) -> datetime:
        return requested_at.replace(minute=0, second=0, microsecond=0)

    def get_for_requested_at(self, requested_at: datetime) -> PredictionRecord | None:
        normalized_requested_at = self.normalize_requested_at(requested_at)
        stmt = (
            select(PredictionRecord)
            .where(PredictionRecord.requested_at == normalized_requested_at)
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_requested_at_between(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> set[datetime]:
        stmt = select(PredictionRecord.requested_at).where(
            PredictionRecord.requested_at.between(start_at, end_at)
        )
        return set(self.db.scalars(stmt))

    def exists_for_requested_at(self, requested_at: datetime) -> bool:
        return self.get_for_requested_at(requested_at) is not None

    def save_prediction(self, prediction: dict) -> PredictionRecord:
        prediction["requested_at"] = self.normalize_requested_at(prediction["requested_at"])
        record = PredictionRecord(**prediction)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record
