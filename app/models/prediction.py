from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, unique=True, index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_backfill: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    global_flare_probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_class: Mapped[int] = mapped_column(Integer, nullable=False)
    localized_probabilities: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)

    jp2_object_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    full_disk_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    active_regions: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    heatmaps: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
