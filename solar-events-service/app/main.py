"""FastAPI application factory and route registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import events, health


app = FastAPI(title="Solar Events Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(events.router)
