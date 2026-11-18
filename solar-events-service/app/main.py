"""FastAPI application factory and route registration."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import events, health
from app.services.catalog_bootstrap import seed_event_catalog


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(seed_event_catalog)
    yield


app = FastAPI(title="Solar Events Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(events.router)
