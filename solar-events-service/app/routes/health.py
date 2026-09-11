"""Service health endpoints."""

from fastapi import APIRouter

from app.db.mongo import ping_database


router = APIRouter(tags=["health"])


@router.get("/")
def home() -> dict:
    """Return basic service identity and storage-backend information."""
    return {"message": "Solar events API is running.", "storage": "mongodb"}


@router.get("/health")
def health() -> dict:
    """Verify MongoDB connectivity and report readiness to Docker or operators."""
    ping_database()
    return {"status": "ok", "storage": "mongodb"}
