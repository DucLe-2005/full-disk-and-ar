# Solar Flare Forecasting
This repo presents the web application and deep learning pipeline that integrates full-disk solar flare prediction model and active region prediction models. Using three explainability methods (i) Guided Gradient=weighted Class Activation Mapping, (ii) Deep Shapley Additive Exaplantions, and (iii) Integrated Gradients.

## Demo

[Watch the demo video on YouTube](https://youtu.be/VvdGnm-D_tU)

## Structure

- `app/`: backend server
- `prediction/pipeline/`: inference stages used by the application.
- `prediction/worker/`: cosume prediction jobs in the queue and save artifacts generated.
- `prediction/modeling/`: model architectures and trained weights.
- `prediction/evaluation/`: Offline dataset preparation, model evaluation, and
  localization analysis. These utilities reuse selected production pipeline
  stages but are not imported by the production worker.

## Source Code Documentation

1. download_2025_magnetograms.py: This function downloads HMI Magnetograms at every mid night (if present) in 2025. These HMI magnetograms will then be used for evaluation.
2. labels.py: The function `create_24h_labels()` creates dataset.csv with lables for existing 2025 HMI JPGs. `true_label` is 1 when an M- or X-class flare peaks in the interval [magnetogram timestamp, timestamp + 24 hours), otherwise 0. 
3. `dataset.py`: This class loads the labled full-disk magnetograms listed in a dataset CSV.
4. `localization.py`: Parses flare-event positions, projects their heliographic coordinates into image pixels, matches them to proposed active-region hulls, and creates diagnostic overlays.

  ### Full-disk evaluation — `evaluate_full_disk.py`

  The full-disk evaluation entry point evaluates the fold-1 full-disk
  classifier over the 2025 magnetogram archive. It first creates 24-hour
  M/X-flare labels, loads the labeled magnetograms in batches, runs softmax
  inference with the trained fold-1 `Custom_AlexNet` checkpoint (on CPU or
  CUDA), applies a `0.5` flare-probability threshold, and writes both per-image
  predictions and summary metrics.

  Run it with:

  ```sh
  python -m prediction.evaluation.evaluate_full_disk
  ```

  Its outputs are written to `data/evaluation_2025/`:

  - `dataset.csv`: one 2025 magnetogram per row, with timestamp, image path,
    and the next-24-hour M/X flare label.
  - `full_disk_predictions.csv`: true labels, class probabilities, and binary
    predictions for every evaluated image.
  - `metrics.csv`: TN, FP, FN, TP, accuracy, precision, recall, F1, TSS, and
    HSS for the full-disk model.

  ### Active-region evaluation — `evaluate_ar.py`

  The active-region evaluation entry point evaluates the MobileNet
  active-region classifier on regions proposed from each 2025 full-disk
  magnetogram. For every image, it generates attribution-based region hulls,
  projects catalogued M/X-flare active-region locations from `data/events.csv`
  into the 512px image coordinate system, labels proposals by whether they
  contain a catalogued active region, crops each proposal from the matching
  JP2 magnetogram, and classifies the crop at a `0.5` threshold. It also saves
  an overlay whenever a magnetogram has catalogued active regions.

  Run it with:

  ```sh
  python -m prediction.evaluation.evaluate_ar
  ```

  Its outputs are written to `data/active_region_evaluation_2025/`:

  - `active_region_predictions.csv`: one row per proposed region, including
    its rank, true label, flare probability, and predicted label.
  - `metrics.csv`: TN, FP, FN, TP, accuracy, precision, recall, F1, TSS, and
    HSS for active-region proposals.
  - `final_hulls_with_actual_ars/`: diagnostic overlays of proposal hulls and
    projected catalogue active-region locations.

- `web/`: web dashboard to view all solar flare predictions.

## Quick Start

Confirm model weights exist:

```text
prediction/modeling/full_disk/trained_models/
prediction/modeling/active_region/trained_models/
```

Choose one of the following setup paths. Run `make help` at any time to see the
standardized Docker commands.

### Docker Compose

Create a `.env` file in the repository root using `.env.example` as the
template, then start the complete stack:

```sh
make build
make up
```

For Docker-based development with source bind mounts and automatic API and
frontend reloads, use:

```sh
make up
```

Restart the worker after changing its Python source:

```sh
make restart SERVICE=worker
```

### Production deployment

Publish versioned API, web, and worker images to Docker Hub from a checkout
where the Git-LFS model files have been downloaded:

```sh
docker login
DOCKERHUB_USERNAME=ducleanh IMAGE_TAG=v1.0.0 scripts/publish-images.sh
```

On the production host, copy `docker-compose.prod.yml` and create `.env` from
`.env.prod.example`. Set the image tag, replace all example passwords, then
start the stack without cloning the source code:

```sh
make prod-pull
make prod-up
```

Only the dashboard is published to the host (port `3000` by default). Postgres,
MinIO, the API, and the worker remain on a private Compose network.

### Local development

Create `.env` from `.env.example` in the repository root and create
`web/.env.local` from `web/.env.local.example`. Install dependencies, then run
the API, worker, and frontend in separate terminals:

```sh
# Install Python dependencies
python -m pip install -r requirements.txt

# Terminal 1: API
uvicorn app.main:app --reload

# Terminal 2: worker
python -m prediction.worker.run_worker

# Terminal 3: frontend
cd web
npm install
npm run dev
```

Services:

- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- API health: `http://localhost:8000/health`
- Solar events API: `http://localhost:8001` (MongoDB-backed; run `make scrape-events` to populate a new database)
- Solar events MongoDB: `mongodb://localhost:27017`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

The model weights are mounted read-only into the worker and manual pipeline containers. They are excluded from the Docker build context to keep rebuilds fast.

When the dashboard opens an individual prediction, it requests `GET /history/{prediction_id}`. The API queries the solar-events service for actual M/X flare regions in the following 24 hours and, when locations are available, returns an `actual_flare_overlay_url` with those locations marked on the candidate-region image. Set `SOLAR_EVENTS_SERVICE_URL` to override the default internal Compose URL.

## Common Commands

```sh
# Create/start or control existing development containers
make up
make start
make stop
make restart

# Operate on one service
make restart SERVICE=worker
make logs SERVICE=api
make build SERVICE=web
make rebuild SERVICE=worker

# Inspect, pull, and validate
make ps
make logs
make pull
make config

# Remove containers, or completely reset containers and volumes
make down
make shutdown
```

`up` creates missing containers and starts the development stack in the
background. `start` only starts containers that already exist. `down` preserves
named volumes; `shutdown` removes volumes and orphan containers as well.

## Backfill

Queue hourly jobs from `2020-01-01 00:00:00` through `2025-12-31 23:00:00`:

```sh
make backfill
```

Custom inclusive range:

```sh
make backfill-range START_TIME="2020-01-01" END_TIME="2025-12-31"
```

The service skips hours with an existing prediction or an already queued/running job. The worker processes the resulting queue normally.

## Offline Evaluation

Download one full-resolution HMI magnetogram per day for 365 days in 2025,
starting at midnight, and convert each JP2 to JPG:

```sh
python -m prediction.evaluation.download_2025_magnetograms
```

To invoke it from Python instead:

```python
from prediction.evaluation.download_2025_magnetograms import download_2025_magnetograms

download_2025_magnetograms()
```

Files are written under:

```text
data/YYYY/MM/DD/HH/mm/ss/jp2/
data/YYYY/MM/DD/HH/mm/ss/jpg/
```

The downloader reuses existing JP2 files and skips existing JPG conversions.
Run the complete 2025 evaluation after the archive is available:

```sh
python -m prediction.evaluation.evaluate_full_disk
```

This creates `data/evaluation_2025/dataset.csv`, runs batched inference, and
writes `full_disk_predictions.csv` and `metrics.csv`. See
`prediction/evaluation/README.md` for the offline package structure.

## Job Flow

1. The API normalizes requested timestamps to the whole hour.
2. It deduplicates by requested hour and inserts a queued job.
3. The worker polls Postgres and claims the oldest queued job.
4. The pipeline requests the closest Helioviewer image.
5. The image is accepted only when its timestamp is within `+/-12` minutes of the requested hour; otherwise the job is marked failed.
6. The worker uploads artifacts to MinIO, saves prediction metadata, and marks the job completed.

The worker processes existing jobs only. It does not currently enqueue a new job automatically at each hour.

## API

- `GET /health`
- `POST /predictions/jobs`
- `POST /predictions/jobs/range`
- `GET /predictions/jobs/{job_id}`
- `GET /history/`

## Pipeline

The pipeline in `prediction/pipeline/run_pipeline.py`:

1. Downloads an HMI JP2 and converts it to a full-disk JPG.
2. Runs the fold-1 full-disk classifier.
3. Generates Guided Grad-CAM, Integrated Gradients, and DeepLiftShap maps in memory.
4. Combines them into a consensus heatmap.
5. Runs Canny, DBSCAN, convex-hull buffering, solar-disk masking, and reclustering.
6. Saves the buffered solar mask.
7. Produces padded fixed-size `512x512` active-region crops.
8. Runs active-region model inference.

Every final reclustered hull is retained as an active-region proposal. Proposals are ranked by a normalized area-weighted consensus score: mean heatmap intensity inside the polygon multiplied by `log1p(region_area) / log1p(max_region_area)`.

Production has no command-line parser. The worker supplies only the requested
Helioviewer timestamp; stable model selections, thresholds, crop size,
clustering settings, and proposal buffers are named constants in
`run_pipeline.py` and `region_proposal.py`.

## Artifact Storage

Local worker artifacts:

```text
data/YYYY/MM/DD/full_disk/
data/YYYY/MM/DD/heat_maps/
data/YYYY/MM/DD/active_regions/
```

MinIO object keys:

```text
predictions/YYYY/MM/DD/HH/full_disk/{filename}
predictions/YYYY/MM/DD/HH/heat_maps/{buffered-mask-filename}
predictions/YYYY/MM/DD/HH/active_regions/{filename}
```

The JP2 is an intermediate input and is not uploaded. The database stores MinIO object keys. The frontend resolves them as:

```text
NEXT_PUBLIC_ARTIFACT_BASE_URL + "/" + object_key
```

With the default Compose configuration:

```text
http://localhost:9000/solar-artifacts/predictions/YYYY/MM/DD/HH/...
```

## Environment

The main settings are defined in `.env.example`:

- `DATABASE_URL`: Postgres connection used by API and worker.
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`.
- `DEFAULT_HELIOVIEWER_DATE`: fallback for jobs missing a requested date.

Compose uses service hostnames such as `db` and `minio`. Local processes outside Docker should use reachable hostnames such as `localhost`.

## Troubleshooting

- Worker failures: `make logs SERVICE=worker`
- Missing images: verify MinIO at `http://localhost:9000` and `NEXT_PUBLIC_ARTIFACT_BASE_URL=http://localhost:9000/solar-artifacts`.
- Stale service image: rebuild only that service with `make rebuild SERVICE=<service>`.
- Clean reset: run `make shutdown`, then `make build` and `make up`.

## Tests

Build the isolated test images and run all three suites:

```bash
make test
```

To run an individual suite:

```bash
make test-api
make test-solar-events
make test-web
```

## Continuous Integration

GitHub Actions runs the three Dockerized test suites in parallel for every
commit pushed to any branch and for every pull request. The workflow can also
be started manually from the Actions tab. It uses the same `make test-api`,
`make test-solar-events`, and `make test-web` commands used during development,
so local and CI behavior stay aligned.

The workflow is defined in `.github/workflows/ci.yml`. It grants read-only
repository permissions, cancels superseded runs on the same branch or pull
request, and reports each service suite as a separate required-check candidate.
