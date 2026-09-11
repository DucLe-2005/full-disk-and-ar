# Solar Events REST API
 
A MongoDB-backed FastAPI service for LMSAL (Lockheed Martin Solar and
Astrophysics Laboratory) solar flare events, including NOAA quality matching
and active-region evaluation queries.
 
---
 
## Project Structure
 
```
LMSAL/
├── scraper.py            # One-time full scrape of all events from 2015 to present
├── daily_scraper.py      # Scrapes only today and yesterday's new events (run daily)
├── scrape_window.py      # Scrapes events for one requested development window
├── noaa_downloader.py    # Downloads NOAA event txt files via FTP
├── noaa_matcher.py       # Parses NOAA data + assigns quality flags
├── coordinates.py        # Converts derived position to pixel coordinates
├── noaa_data/            # Downloaded NOAA txt files
├── requirements.txt      # Python dependencies
├── app/
│   ├── main.py           # FastAPI application setup
│   ├── config.py         # Environment configuration
│   ├── db/               # MongoDB client and indexes
│   ├── dto/              # Request/response DTOs
│   ├── models/           # Event document normalization
│   ├── repositories/     # MongoDB queries and updates
│   ├── routes/           # REST endpoint definitions
│   └── services/         # Scraping, event queries, NOAA, and coordinates
└── Dockerfile             # REST API container image
```
 
---
 
## Installation
 
### Python Dependencies
 
```bash
pip install -r requirements.txt
```
 
Or manually:
 
```bash
pip install httpx beautifulsoup4 fastapi uvicorn python-multipart pymongo
```
 
---
 
## How to Run
 
The root repository Compose stack provides both MongoDB and this API. From the
repository root, start just the solar-events services with Docker:

```bash
docker compose up --build -d solar-events-db solar-events-api
```

The MongoDB volume persists across container restarts. The service API is
exposed at `http://localhost:8001`; MongoDB is exposed at
`mongodb://localhost:27017`.

No JSON migration is performed or needed. A new database starts empty; build
its event collection directly from LMSAL by running the scraper inside the API
container:

```bash
docker compose exec solar-events-api python scraper.py
```

For development with automatic reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build \
  solar-events-db solar-events-api
```
 
- API runs at: `http://localhost:8001`
---
 
## Scripts — Run in Order

### Targeted development scrape

Populate only the next 24 hours for a prediction timestamp instead of running
the full historical scraper:

```bash
docker compose exec solar-events-api python scrape_window.py \
  --timestamp "2026-03-27T00:00:00Z"
```

`scrape_window.py` inspects LMSAL snapshots through two days after the target
window, then writes only events whose start time is in
`[timestamp, timestamp + 24 hours)`. Override the window with
`--window-hours 48` when needed.

The API equivalent is a background `POST` request:

```text
POST /scrape/window?prediction_timestamp=2026-03-27T00:00:00Z&window_hours=24
```

### 1. Scrape All Historical LMSAL Events (run once)
```bash
/opt/miniconda3/bin/python scraper.py
```
Scrapes all solar flare events from the LMSAL archive starting from July 1, 2015 up to today. Events are upserted into MongoDB by `event_id`; snapshot URLs are merged without duplicates. Run this only when a full historical refresh is needed.
 
### 2. Update with New Events (run daily)
```bash
/opt/miniconda3/bin/python daily_scraper.py
```
Scrapes only today's and yesterday's new events from LMSAL and upserts them into MongoDB.
 
To automate daily updates using macOS crontab:
```bash
# Open crontab editor
crontab -e
 
# Add this line to run at midnight every day
0 0 * * * /opt/miniconda3/bin/python /path/to/LMSAL/daily_scraper.py
```
 
### 3. Download NOAA Data
```bash
/opt/miniconda3/bin/python noaa_downloader.py
```
Connects to the NOAA FTP server (`ftp.swpc.noaa.gov`) and downloads event txt files for each unique event date in MongoDB. Files are saved to `noaa_data/`. Automatically skips dates where NOAA has no data.
 
### 4. Match & Assign Quality Flags
```bash
/opt/miniconda3/bin/python noaa_matcher.py
```
Parses NOAA txt files and compares each LMSAL event against NOAA data. Assigns a `quality_flag` to each event based on time difference and GOES class matching:
 
| Flag | Condition |
|------|-----------|
| `HIGH` | Match found within ±10 minutes with same GOES class |
| `LOW` | No matching event found, or missing data |
 
Only `XRA` (X-Ray Activity) type NOAA events are used since those are the only ones with GOES classifications.
 
### 5. Calculate Pixel Coordinates
```bash
/opt/miniconda3/bin/python coordinates.py
```
Scraping now stores each event's pixel coordinates (`pix_x`, `pix_y`) together
with its derived position. This command remains available to backfill or repair
older records. It uses the same heliographic coordinate transformation as the
scraper:
 
```
HGS (lat/lon degrees)
    → HCC (Heliocentric, meters)
    → HPC (Helioprojective, arcseconds)
    → Pixel coordinates (512x512 space)
```
 
---
 
## Keeping the Database Up To Date
 
```
First time setup:
1. Run scraper.py          → builds full historical database (2015 to now)
2. Run noaa_downloader.py  → downloads NOAA comparison files
3. Run noaa_matcher.py     → assigns quality flags
4. Run coordinates.py      → backfills pixel coordinates on older records
 
Daily maintenance:
1. Run daily_scraper.py    → adds yesterday and today's new events
2. Run noaa_downloader.py  → downloads any new NOAA files
3. Run noaa_matcher.py     → updates quality flags
4. No coordinate step      → each scrape upsert refreshes pixel coordinates
```
 
---
 
## API Endpoints
 
### `GET /events`
Returns filtered list of solar events.
 
**Query Parameters:**
| Parameter | Format | Example |
|-----------|--------|---------|
| `start_date` | YYYY-MM-DD | `2026-02-16` |
| `end_date` | YYYY-MM-DD | `2026-02-19` |
| `goes_class` | Letter prefix | `C` or `M` |
 
**Examples:**
```
http://localhost:8001/events
http://localhost:8001/events?goes_class=C
http://localhost:8001/events?start_date=2026-02-16&end_date=2026-02-19
http://localhost:8001/events?start_date=2026-02-16&goes_class=M
```
 
### `GET /events/{event_id}`
Returns a single event by ID.
 
```
http://localhost:8001/events/gev_20260216_1224
```
 
### `GET /events/download/`
Same filtering as `/events` but returns a downloadable `events.json` file.
 
```
http://localhost:8001/events/download/?goes_class=C
```
 
### `GET /scrape`
Triggers the daily scraper to run in the background and fetch new events.
 
```
http://localhost:8001/scrape
```
 
---
 
## Event Data Fields
 
Each document in the MongoDB `solar_events.events` collection retains these public fields:
 
| Field | Description | Example |
|-------|-------------|---------|
| `event_id` | Unique event identifier | `gev_20260216_1224` |
| `event_start` | Start date and time | `2026/02/16 12:24:00` |
| `event_stop` | Stop time | `13:42:00` |
| `event_peak` | Peak time | `13:07:00` |
| `event_GOES` | GOES classification | `C1.0` |
| `event_position` | Derived heliographic position | `S18E10` |
| `seen_in_dates` | LMSAL snapshot URLs where event appeared | `[...]` |
| `quality_flag` | NOAA comparison result | `HIGH` or `LOW` |
| `pix_x` | X pixel coordinate on 512x512 image | `300.5` |
| `pix_y` | Y pixel coordinate on 512x512 image | `210.3` |

MongoDB also stores indexed `event_start_at`, `event_peak_at`, and `event_stop_at`
UTC timestamps. They are persistence/query fields and are deliberately omitted from
the legacy `/events` response shape.

### Actual active regions for a prediction window

`GET /active-regions` returns the actual heliographic regions that produced M- or
X-class events whose **peak** falls in `[prediction_timestamp,
prediction_timestamp + 24 hours)`. This is the evaluation window used by the
full-disk and active-region dashboard.

```text
http://localhost:8001/active-regions?prediction_timestamp=2026-03-27T00:00:00Z
```

The response groups matching events by `region_id`, which is the NOAA active-region
number in parentheses in the LMSAL position (for example, `S22E79( 4525 )` becomes
`4525`). Each region is returned once even when several events in the window came
from that NOAA region. Its original `event_position` remains available for map
placement. Events without a parenthesized NOAA region number are not returned as an
active region because they cannot be reliably deduplicated. `window_hours` defaults
to `24`; `goes_classes` defaults to `M,X` and can be broadened, for example
`goes_classes=C,M,X`.
 
---
 
## Data Sources
 
| Source | URL | Description |
|--------|-----|-------------|
| LMSAL Archive | `https://www.lmsal.com/solarsoft/latest_events_archive.html` | Solar flare event snapshots |
| NOAA FTP | `ftp://ftp.swpc.noaa.gov/pub/indices/events` | Daily solar event reports |
| ISWA Images | `https://iswa.ccmc.gsfc.nasa.gov/iswa_data_tree/observation/solar/sdo/hmi-magnetogram_2048x2048/` | SDO/HMI magnetogram images |
 
---
 
## Quality Flag Logic
 
Each LMSAL event is compared against NOAA/GOES XRA events for the same date:
 
```
HIGH quality → same date + begin time within ±10 minutes + same GOES class
LOW quality  → no match found, or missing GOES class or timestamps
```
 
NOAA data only includes `XRA` (X-Ray Activity) type events since those are the only ones with GOES classifications. Events with `////` (missing data) are automatically assigned `LOW` quality.
 
---
 
## Coordinate Conversion
 
Derived positions like `S11W04` mean:
- `S11` → 11 degrees south (negative latitude)
- `W04` → 4 degrees west (positive longitude)
These are converted to image pixel coordinates using heliographic coordinate transformation based on conversion code provided by the course instructor (Dr. Chetraj Pandey).
 
---
 
## Git Branches
 
| Branch | Description |
|--------|-------------|
| `main` | Stable base version |
| `imageFeature` | Helioviewer image integration (paused — API down) |
| `iswaImage` | ISWA image integration with position plotting |
| `asyncScraper` | Async scraping for faster data collection |
| `optimal_time_range` | Optimal window analysis for quality flags |
| `old_time_range` | Latest working branch with daily scraper |

 
