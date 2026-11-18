# Project Structure

This project is split into three main application areas:

- `app/`: FastAPI backend
- `web/`: Next.js frontend
- `prediction/`: Scheduled forecast runner and model pipeline

The dashboard and API read forecasts from PostgreSQL and artifacts from MinIO. The hourly scheduler and local backfill invoke the same one-shot predictor.

---

## Top-Level Layout

```text
Full-Disk-and-AR-models-for-forecasting-solar-flares/
|-- app/                 FastAPI backend
|-- web/                 Next.js frontend
|-- prediction/          Prediction pipeline and one-shot runner
|-- requirements/        Shared Python dependency files
|-- deploy/systemd/      Hourly production scheduler units
|-- data/                Optional offline evaluation data
|-- docker-compose.yml   Local full-stack runtime
|-- requirements.txt     Root Python dependency entrypoint
|-- README.md            Setup and runtime documentation
`-- structure.md         This file
```

---

## Backend: `app/`

The backend owns the API, database models, database repositories, services, settings, and MinIO upload helpers.

```text
app/
|-- api/
|   |-- repositories/    Database access for jobs and predictions
|   |-- routers/         FastAPI routes
|   |-- schemas/         Pydantic request/response schemas
|   `-- services/        Legacy/API service helpers
|
|-- core/
|   |-- config.py        Environment-driven settings
|   |-- database.py      SQLAlchemy engine, session, and Base
|   |-- dependencies.py  FastAPI dependency providers
|   |-- schema.py        First-start schema creation
|   `-- storage.py       MinIO artifact upload helpers
|
|-- models/
|   |-- pipeline_job.py  `pipeline_jobs` table
|   `-- prediction.py    `predictions` table
|
|-- services/
|   |-- job_service.py        Job creation, reuse, and status logic
|   `-- prediction_service.py Prediction history/query logic
|
|-- Dockerfile           Backend API container
`-- main.py              FastAPI application entrypoint
```

Main backend routes:

- `GET /health`
- `GET /predictions/jobs/{job_id}` (legacy status)
- `GET /history/`

---

## Frontend: `web/`

The frontend is a Next.js dashboard. Its live feed refreshes the latest 24 successful forecasts. The history view supports date and class filters and displays saved artifacts from MinIO.

```text
web/
|-- app/
|   |-- api/
|   |   |-- history/
|   |   |   `-- route.ts        Server proxy to FastAPI history endpoint
|   |   `-- jobs/
|   |       `-- [jobId]/
|   |           `-- route.ts    Legacy job-status proxy
|   |
|   |-- globals.css            Dashboard styles
|   |-- layout.tsx             Root layout
|   `-- page.tsx               Main prediction dashboard
|
|-- lib/
|   |-- api.ts                 Frontend API helpers
|   |-- artifacts.ts           MinIO/browser artifact URL helpers
|   `-- types.ts               Shared frontend types
|
|-- public/                    Static frontend assets
|-- Dockerfile                 Frontend container
|-- next.config.mjs
|-- package.json
|-- package-lock.json
`-- tsconfig.json
```

Important frontend behavior:

- Browser requests go to Next.js routes under `web/app/api/...`.
- Next.js server routes call FastAPI through `FASTAPI_BASE_URL`.
- Browser image URLs are built from `NEXT_PUBLIC_ARTIFACT_BASE_URL`.

---

## Prediction System: `prediction/`

The prediction folder separates application inference from manually invoked evaluation and reporting.

```text
prediction/
|-- modeling/
|   |-- active_region/   Active-region model definitions and weights
|   `-- full_disk/       Full-disk model, ensemble loader, and fold weights
|
|-- pipeline/
|   |-- stages/          Production download, attribution, crop, predict stages
|   |-- persistence.py   MinIO uploads and prediction row mapping
|   `-- run_pipeline.py  Inference and artifact generation
|
|-- run_forecast.py      One UTC slot or a resumable UTC range
|-- worker/              Legacy runner
|
|-- evaluation/          Offline download, labels, inference, metrics, reports
|
|-- Dockerfile           One-shot predictor container
`-- requirements.txt
```

The scheduler invokes `prediction.run_forecast` in the predictor container. Offline tasks run as Python modules under `prediction.evaluation`.

---

## Requirements

```text
requirements/
|-- api.txt              Backend/API dependencies
|-- base.txt             Shared Python dependencies
|-- pipeline.txt         Pipeline/model dependencies
|-- evaluation.txt       Pipeline plus optional offline FITS/JSOC dependencies
`-- requirements.txt     Combined include file
```

There is also a root `requirements.txt` entrypoint for installing dependencies from the repository root.

---

## Runtime Flow

```text
Hourly scheduler or manual backfill
  -> one-shot predictor -> Helioviewer + models
                       -> MinIO artifacts
                       -> PostgreSQL prediction row

Dashboard -> Next.js history and detail routes -> FastAPI -> PostgreSQL
          -> Next.js artifact route -> MinIO
```

The predictor takes a UTC forecast slot and acquires a PostgreSQL lock for that
hour. The pipeline uses a recent observation at or before the slot. It uploads
artifacts before the result is committed, so the dashboard can read the result
once its files are available. The slot, observation and publication times are
stored separately.

See [the README](README.md#hourly-deployment) for the hourly timer and cutover
instructions.

## Artifact Storage

The predictor generates images in a temporary directory and uploads them to
MinIO under a UTC hour prefix:

```text
predictions/YYYY/MM/DD/HH/full_disk/
predictions/YYYY/MM/DD/HH/heat_maps/
predictions/YYYY/MM/DD/HH/active_regions/
```

The database stores MinIO object paths. The frontend turns those object paths into browser URLs using:

```text
NEXT_PUBLIC_ARTIFACT_BASE_URL
```
