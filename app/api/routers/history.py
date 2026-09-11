from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException

from app.api.schemas.prediction import PredictionHistoryPage, PredictionResponse
from app.core.dependencies import get_prediction_service
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.get("/", response_model=PredictionHistoryPage)
def get_prediction_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    predicted_class: int | None = Query(default=None, ge=0, le=1),
    service: PredictionService = Depends(get_prediction_service),
) -> PredictionHistoryPage:
    return service.list_prediction_history(
        page=page,
        page_size=page_size,
        start_at=start_time,
        end_at=end_time,
        predicted_class=predicted_class,
    )


@router.get("/{prediction_id}", response_model=PredictionResponse)
def get_prediction_detail(
    prediction_id: str,
    service: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    try:
        return service.get_prediction_detail(prediction_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
