# Store Intelligence System

End-to-end Purplle/Apex Retail challenge implementation: raw CCTV clips to structured events, idempotent FastAPI ingest, real-time metrics, funnel, heatmap, anomalies, health, replay, and a live dashboard.

## Resources Found

The repo was initialized from these local resources:

- Problem statement PDF: `resources/Purplle Tech Challenge 2026 _ Round 2 Problem Statement480e74e.pdf`
- Evaluation PDF: `resources/Assessment  Evaluation Framework.pdf`
- POS CSV: `resources/Brigade_Bangalore_10_April_26.csv`
- POS sample CSV: `resources/POS - sample transactions.csv`
- Sample event JSONL: `resources/sample_eventsbe42122.jsonl`
- Layout workbook: `resources/Brigade Road - Store layout.xlsx`
- CCTV clips:
  - `datasets/cctv_footage/Store 1/CAM 1 - zone.mp4`, `CAM 2 - zone.mp4`, `CAM 3 - entry.mp4`, `CAM 5 - billing.mp4`
  - `datasets/cctv_footage/Store 2/entry 1.mp4`, `entry 2.mp4`, `zone.mp4`, `billing_area.mp4`

The layout workbook and layout images are visual assets rather than machine-readable polygons. I generated normalized default zones in `configs/store_layout.generated.json` and kept editable two-store camera/zone examples in `configs/cameras.example.yaml`. Store aliases are canonicalized: `ST1008`/`Store 1` -> `STORE_BLR_002`, and `ST1076`/`store_1076`/`Store 2` -> `STORE_MUM_1076`.

## Five-Command Quickstart

One-file Docker setup on a fresh Windows PC:

```powershell
.\setup.ps1
```

This Windows setup downloads the Store 1 and Store 2 CCTV zip archives, extracts clips into `datasets/cctv_footage/Store 1` and `datasets/cctv_footage/Store 2`, builds/runs Docker with the CV stack enabled, verifies OpenCV plus the `lap` tracker dependency, warms `yolo11n.pt` and `rtdetr-x.pt`, checks the same `/video-demo/stream` route used by the browser, waits for `/health`, and seeds dashboard data from discovered clips when the database is empty. If you only want the lightweight API without CV/model warm-up, run:

```powershell
.\setup.ps1 -ApiOnly
```

Useful setup flags:

```powershell
.\setup.ps1 -SkipResourceDownload
.\setup.ps1 -SkipDataSeed
.\setup.ps1 -SkipModelWarmup
.\setup.ps1 -ForceResourceRefresh
```

Basic one-file Docker setup on macOS/Linux:

```bash
sh setup.sh
```

The shell setup creates `.env`, required local folders, builds the image, starts the API, waits for `/health`, and prints the dashboard/API URLs. For the heavier OpenCV + Ultralytics image on macOS/Linux, run `sh setup.sh --with-cv`.

Manual equivalent:

```bash
cp .env.example .env
docker compose up --build
python -m scripts.load_pos --csv "resources/Brigade_Bangalore_10_April_26.csv"
python -m scripts.load_pos --csv "resources/POS - sample transactions.csv"
python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl
python -m pipeline.replay outputs/events.jsonl --url http://localhost:8000/events/ingest --speed 10
```

Dashboard: http://localhost:8000/dashboard

Live model detection viewer: http://localhost:8000/video-demo

API docs: http://localhost:8000/docs

## Local Python Setup

Docker is the recommended setup for another PC. For local development without Docker, create a Python 3.12 virtual environment and install development requirements:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Optional CV stack for real model-backed detection:

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
```

If `ultralytics` or model weights are unavailable, the detector falls back to low-confidence deterministic events so the pipeline remains runnable. The high-accuracy default is RT-DETR-X; YOLO models remain supported as lighter alternatives.

## Docker Deployment

Default API-only startup:

```bash
docker compose up --build
```

The default image intentionally excludes OpenCV/Ultralytics so the API, dashboard, ingest, metrics, funnel, heatmap, anomalies, and health endpoints run on CPU-only machines without downloading model weights. Data is persisted in the named Docker volume `store-intelligence_store_data`.

On Windows, prefer `.\setup.ps1` for first-time setup because it also downloads Store 1/Store 2 clips and seeds dashboard events. If you use raw `docker compose up --build`, the API will start but the dashboard will stay empty until events are ingested.

If another PC was built before the latest CV dependency changes and Start live view fails, rebuild the image so tracker dependencies are installed before the API starts:

```powershell
docker compose down
docker compose build --no-cache api
.\setup.ps1
```

The setup script now imports `cv2` and `lap`, runs a BoT-SORT tracker check, and performs a browser-route MJPEG smoke test. If BoT-SORT still cannot load at runtime, the live viewer falls back to internal centroid tracking and shows a notification instead of silently stopping.

Optional CV detector image:

```bash
INSTALL_CV=true docker compose --profile cv run --rm detector
```

On Windows PowerShell:

```powershell
$env:INSTALL_CV="true"; docker compose --profile cv run --rm detector
```

Put clips in `datasets/cctv_footage/` before running the detector. The output goes to `outputs/events.jsonl`, which is ignored by git.

Stop the stack:

```bash
docker compose down
```

Do not push local CCTV clips, POS/layout source resources, SQLite DBs, generated JSONL files, model weights, or `outputs/`. `.gitignore` and `.dockerignore` are set up for this.

More deployment notes are in `docs/DEPLOYMENT.md`.

### Vercel Deployment

Vercel does not run this repository's Dockerfile directly. The repo includes a Vercel-safe Python Function entrypoint at `api/index.py`, route config in `vercel.json`, and upload exclusions in `.vercelignore` so the FastAPI API and dashboard can deploy without CCTV clips or model weights. See `docs/VERCEL.md` for the exact steps and limitations. The full YOLO/RT-DETR live CCTV demo remains a Docker/local runtime feature because it needs OpenCV, model weights, local videos, and long-running MJPEG streaming.

## API Endpoints

```bash
curl http://localhost:8000/health
curl http://localhost:8000/stores
curl http://localhost:8000/stores/STORE_BLR_002/metrics
curl http://localhost:8000/stores/STORE_BLR_002/funnel
curl http://localhost:8000/stores/STORE_BLR_002/heatmap
curl http://localhost:8000/stores/STORE_BLR_002/anomalies
curl http://localhost:8000/stores/STORE_MUM_1076/metrics
```

Evaluator shorthand aliases also work for the default store:

```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/funnel
curl http://localhost:8000/heatmap
curl http://localhost:8000/anomalies
```

Ingest events:

```bash
curl -X POST http://localhost:8000/events/ingest ^
  -H "Content-Type: application/json" ^
  -d "{\"events\":[]}"
```

Windowing examples:

```bash
curl "http://localhost:8000/stores/STORE_BLR_002/metrics?date=2026-04-10"
curl "http://localhost:8000/stores/STORE_BLR_002/funnel?start=2026-04-10T10:00:00Z&end=2026-04-10T22:00:00Z"
```

## Detection Pipeline

Put CCTV clips under:

```text
datasets/cctv_footage/
```

Process all clips:

```bash
python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl
```

Validate output:

```bash
python -m pipeline.validate_events outputs/events.jsonl
```

Emit directly to the API in simulated real time:

```bash
python -m pipeline.detect --input datasets/cctv_footage --emit-url http://localhost:8000/events/ingest --realtime --speed 5
```

Tune detection:

```bash
python -m pipeline.detect --input datasets/cctv_footage --model rtdetr-x.pt --sample-fps 5 --confidence 0.10 --imgsz 960 --device 0
python -m pipeline.detect --input datasets/cctv_footage --model yolo11x.pt --tracker botsort.yaml --sample-fps 5 --confidence 0.10 --imgsz 960 --device 0
```

## POS and Layout Loading

Load POS CSV:

```bash
python -m scripts.load_pos --csv "resources/Brigade_Bangalore_10_April_26.csv"
python -m scripts.load_pos --csv "resources/POS - sample transactions.csv"
```

The loader aggregates POS line items by invoice/transaction id, reads the CSV `store_id` column when present, maps resource store `ST1008` to challenge store `STORE_BLR_002`, and stores UTC timestamps. You can still pass `--store-id STORE_X` to override the CSV store id.

Replay the newly provided sample event JSONL directly through the API:

```bash
python -m pipeline.replay "resources/sample_eventsbe42122.jsonl" --url http://localhost:8000/events/ingest --speed 10
```

The API normalizes the sample's alternate fields (`entry`, `zone_entered`, `queue_completed`, `store_1076`, `ST1076`) into the canonical challenge event schema before validation.

Layout handling:

- JSON layout files are preferred when present.
- Excel layout files are inspected with `openpyxl`.
- If polygons are not available, normalized defaults are generated and documented.
- Edit `configs/cameras.example.yaml` or `configs/store_layout.generated.json` to calibrate real entry lines and zones.

## Dashboard

Web dashboard:

```bash
open http://localhost:8000/dashboard
```

The dashboard has a store selector, date selector, in-page navigation, and short explanations for Overview, Funnel, Heatmap, Anomalies, Health, and How it works. You do not need to remember store ids or endpoint URLs.

Live detection viewer:

```bash
open http://localhost:8000/video-demo
```

Use this page to watch YOLO/RT-DETR person detections on a CCTV clip with annotated boxes, confidence, track IDs, optional mask overlays, and live role labels. It has a store selector, so Store 1 and Store 2 clips are filtered without memorizing filenames or URLs. The live-view default is `yolo11n.pt` with Mask refinement `off`, which is faster and avoids unnecessary SAM downloads. If a camera benefits from masks, choose `auto` for native segmentation-model masks, or select `MobileSAM`, `FastSAM-s`, or `SAM vit_b`; those weights download lazily on first use and are ignored by git. New tracks start as `customer_candidate`; optional masks refine the calibrated floor-contact band and uniform sampling; blur is treated as customer evidence unless uniform and staff-area signals agree; and `staff` requires repeated configurable uniform-color matches. The clips have no audio, so interaction is a visual proximity heuristic. Use the Stop live preview button to end the stream cleanly.

For the live viewer, customer recall is intentionally favored over aggressive static filtering. The default `Static after frames` is 16 and `Static motion threshold` is 0.006, so slow browsing customers are counted instead of being ignored. Raise static filtering only when poster detections dominate; lower `Min human bottom Y` if distant real customers are being ignored.

Terminal dashboard:

```bash
python -m dashboard.terminal_dashboard --url http://localhost:8000 --store-id STORE_BLR_002
```

Replay events while the dashboard is open:

```bash
python -m pipeline.replay outputs/events.jsonl --url http://localhost:8000/events/ingest --speed 5
```

## Tests and Smoke

```bash
python -m pytest
python -m pytest --cov=app --cov=pipeline --cov=scripts --cov-report=term-missing
python -m scripts.seed_demo --output outputs/demo_events.jsonl
python -m pipeline.validate_events outputs/demo_events.jsonl
python -m scripts.smoke_test --url http://localhost:8000
```

Make targets:

```bash
make run
make up
make down
make logs
make test
make coverage
make detect
make replay
make smoke
make cv-detect
```

## Known Limitations

- The supplied layout workbook is image-based, so default polygons must be calibrated from camera screenshots for production accuracy.
- Re-ID is heuristic by default. OSNet/torchreid is documented as a future optional upgrade, not required for acceptance.
- SQLite WAL is the challenge default. For 40 stores, move to Postgres plus rollups.
- Fallback detection emits low-confidence events from clip metadata when CV dependencies are absent. Install `requirements-cv.txt` for real RT-DETR/YOLO person detection.

## Key Tuning Knobs

- `--sample-fps`: lower for CPU or long clips; 3-5 FPS is the intended 1080p range.
- `--confidence`: default 0.10 to avoid silently dropping occluded people.
- `--model`: `rtdetr-x.pt` default for highest official COCO AP among checked practical options; use `yolo11x.pt` or `yolov8x.pt` when built-in tracker IDs matter more.
- `--tracker`: `botsort.yaml` default for YOLO models; RT-DETR uses centroid association because the detector path is prediction-first.
- `--imgsz`: default 960 for better small-person recall at higher memory cost.
- `--min-human-bottom-y`: normalized floor-contact calibration for floor/billing cameras. Increase it if wall posters are still counted; decrease it only if distant real customers are being ignored.
- `--static-after-frames` and `--static-motion-threshold`: secondary static-track filtering for unvalidated poster/display detections.
- `POS_CORRELATION_MINUTES`: default 5.
- `STALE_FEED_MINUTES`: default 10.
