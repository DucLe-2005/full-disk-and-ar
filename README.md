# Solar Flare Forecasting
This repo presents the web application and deep learning pipeline that integrates full-disk solar flare prediction model and active region prediction models. Using three explainability methods (i) Guided Gradient=weighted Class Activation Mapping, (ii) Deep Shapley Additive Exaplantions, and (iii) Integrated Gradients.

## Architecture

![Solar flare forecasting system architecture](architecture.png)

### Docker containers

<img src="docker-containers.png" width="480" alt="The browser opens the Next.js dashboard, which reads forecasts through FastAPI and images from MinIO. FastAPI reads forecasts from PostgreSQL and requests observed flares from the solar-events API backed by MongoDB.">

The one-shot predictor fetches a Helioviewer magnetogram, uploads forecast
images to MinIO, and saves the forecast in PostgreSQL.

## Demo

[Watch the demo video on YouTube](https://youtu.be/VvdGnm-D_tU)

## Structure

- `app/`: backend server
- `web/`: dashboard for live forecasts and prediction history.
- `solar-events-service/`: observed flare catalog and API for overlays.
- `deploy/systemd/`: optional hourly forecast timer and service for Linux hosts.
- `prediction/pipeline/`: inference stages used by the application.
- `prediction/run_forecast.py`: publish one forecast or replay a UTC date range.
- `prediction/modeling/`: model architectures and trained weights.
- `prediction/evaluation/`: Offline dataset preparation, model evaluation, and
  localization analysis. These utilities reuse selected production pipeline
  stages but are not imported by the production forecast runner.

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

## Pipeline

The pipeline in `prediction/pipeline/run_pipeline.py`:

1. Downloads an HMI JP2 and converts it to a full-disk JPG.
2. Runs the fold-1 full-disk classifier.
3. Generates Guided Grad-CAM, Integrated Gradients, and DeepLiftShap maps in memory.
4. Extracts buffered bounding regions from each attribution map and intersects
   their masks, retaining only pixels covered by all three attribution methods.
5. Discards every non-shared portion and applies the solar-disk mask to the
   retained intersection regions.
6. Saves the buffered solar mask.
7. Produces padded fixed-size `512x512` active-region crops.
8. Runs active-region model inference.

Every retained merged region is an active-region proposal. Proposals are ranked by a normalized area-weighted consensus score: mean fused heatmap intensity inside the polygon multiplied by `log1p(region_area) / log1p(max_region_area)`.

The predictor passes the requested slot to the pipeline. Model selections,
thresholds, crop size,
clustering settings, and proposal buffers are named constants in
`run_pipeline.py` and `region_proposal.py`.

## Quick Start

### Development

From the repository root with Docker running:

```sh
test -f .env || cp .env.example .env
git lfs pull
make up
```

Open the [dashboard](http://localhost:3000). Startup syncs observed flare
locations and missing forecasts for the last 24 completed UTC hours.
Hours awaiting a magnetogram are logged and can be retried on the next run.

### Production deployment

**CI builds and publishes the application images, and the production host
pulls and runs them.** Push a version tag such as `v1.0.0` to publish the
Linux x86-64 images to GHCR after tests pass.

On the host, place `docker-compose.prod.yml`, `Makefile`, `.env.prod.example`,
and `deploy/systemd/` in `/opt/flare-dashboard`. Create `.env` from
`.env.prod.example` and set `IMAGE_TAG`, `POSTGRES_PASSWORD`, and
`MINIO_ROOT_PASSWORD`. Use a URL-safe PostgreSQL password. Authenticate to GHCR
before pulling private images.

```sh
cd /opt/flare-dashboard
make prod-pull
make prod-up
```

### Hourly deployment

On the Linux production host, install the scheduler from
`/opt/flare-dashboard`. It runs the predictor at five minutes past each UTC hour.

```sh
sudo install -m 0644 deploy/systemd/flare-forecast.service deploy/systemd/flare-forecast.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flare-forecast.timer
```

### Backfill

Fetch observed flare locations and generate missing hourly forecasts for the
chosen UTC date range. Date-only end values include the full final day.

```sh
# Development
make backfill START_TIME=2026-01-01 END_TIME=2026-01-07

# Production
make prod-backfill START_TIME=2026-01-01 END_TIME=2026-01-07
```
