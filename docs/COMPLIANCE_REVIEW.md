# Compliance Review

Review date: 2026-06-03.

This review re-checks the challenge PDFs and evaluation framework against the current implementation. A fuller rubric mapping is in `docs/SCORING_ALIGNMENT.md`.

## Acceptance Gate

| Requirement | Status | Evidence |
| --- | --- | --- |
| `docker compose up` starts API | Implemented; local image build not executed because Docker Desktop engine is not running in this workspace | `Dockerfile`, `docker-compose.yml`, `setup.ps1`, `setup.sh`; `docker-compose config` parses |
| API availability | Implemented | `app/main.py`, local uvicorn smoke test passed |
| `/metrics` returns valid response | Implemented as evaluator shorthand alias for default store | `tests/test_metrics.py`, `scripts/smoke_test.py` |
| Detection pipeline produces structured events | Implemented | `pipeline/detect.py`, `pipeline/validate_events.py`; two-store clip discovery validates Store 1 and Store 2 roles |
| `DESIGN.md` and `CHOICES.md` are non-trivial | Implemented | `docs/DESIGN.md`, `docs/CHOICES.md` |
| System stability | Implemented with caveats | 52 pytest tests pass, 76% coverage, structured 503 handling, smoke test passes |

## Endpoint Coverage

| Endpoint | Status |
| --- | --- |
| `POST /events/ingest` | Implemented with batch limit, idempotency, partial success, structured errors |
| `GET /stores` | Added for dashboard store discovery |
| `GET /stores/{id}/metrics` | Implemented |
| `GET /stores/{id}/funnel` | Implemented |
| `GET /stores/{id}/heatmap` | Implemented |
| `GET /stores/{id}/anomalies` | Implemented |
| `GET /metrics`, `/funnel`, `/heatmap`, `/anomalies` | Added as default-store reviewer shorthand aliases |
| `GET /health` | Implemented |
| `GET /dashboard` | Implemented with store menu, in-page navigation, explanations, and live polling |

## Detection Pipeline

Implemented:

- Recursive video discovery under `datasets/cctv_footage/`.
- Store-scoped video mapping for `datasets/cctv_footage/Store 1` and `datasets/cctv_footage/Store 2`.
- Camera inference from updated names: Store 1 `CAM 1/2 - zone`, `CAM 3 - entry`, `CAM 5 - billing`; Store 2 `entry 1/2`, `zone`, `billing_area`.
- JSON/Excel layout discovery.
- POS-based clip timestamp inference.
- RT-DETR-X/Ultralytics high-accuracy model path, with YOLO11/YOLOv8 fallback support.
- CPU/API-safe fallback when CV deps or model weights are unavailable.
- Normalized zones and entry line configuration.
- Schema-valid event emission with confidence, staff flag, queue depth, and session sequence.
- Reentry, staff, queue, zone, dwell, and abandonment event support at heuristic level.

Known limitation:

- Without optional `requirements-cv.txt`, fallback events are generated from clip metadata rather than real person detections. This is intentionally low confidence and documented in metadata.

## API and Business Logic

Implemented:

- Staff exclusion from metrics/funnel/heatmap/anomalies.
- Historical default date logic: latest event date is used when events are historical.
- Optional `date`, `start`, and `end` windows.
- POS correlation by store and 5-minute billing window.
- Session-based funnel with reentry deduplication.
- Heatmap including zero-visit known zones.
- Queue spike, conversion drop, dead zone, and stale feed handling.
- Empty-store and zero-purchase safety.
- Compatibility normalization for `resources/sample_eventsbe42122.jsonl`, including `store_1076`/`ST1076`, lower-case event names, queue events, and deterministic UUID-v4 ids.
- POS parsing for the new `resources/POS - sample transactions.csv`, using the CSV `store_id` column when present.

## Production Readiness

Implemented:

- Production-oriented Dockerfile and Compose services.
- One-file setup wrappers: `setup.ps1` and `setup.sh`.
- Default API-only image plus optional `INSTALL_CV=true` detector/CV build.
- `.gitignore` and `.dockerignore` guard raw videos, resources, DBs, generated outputs, and model weights.
- SQLite WAL default with SQLAlchemy boundary.
- JSON request logs with trace id, endpoint, method, store id, latency, event count, and status code.
- Global exception handlers with no raw stack traces.
- Health endpoint with DB status, last event by store, stale feed warnings, version, and uptime.
- Tests with required AI prompt/change headers.

Validation results from this workspace:

- `pytest --cov=app --cov=pipeline --cov=scripts --cov-report=term-missing`: 52 passed, 76% coverage.
- `scripts.smoke_test`: passed against local uvicorn.
- `resources/sample_eventsbe42122.jsonl`: 13 accepted, 0 rejected through `/events/ingest`.
- `pipeline.validate_events outputs/validation_samples/sample_eventsbe42122.normalized.jsonl`: 13 valid, 0 invalid.
- YOLO11n sampled start/middle/end frames from all 8 Store 1/Store 2 clips; contact sheets saved under `outputs/validation_samples/` (ignored by git).

## Dashboard Review

The previous dashboard required a user to know store ids and endpoints. It has been replaced with:

- Store selector populated by `GET /stores`.
- Store-scoped live video selector for Store 1 and Store 2 clips.
- Date selector and "Latest day" control.
- Side/top responsive navigation for Overview, Funnel, Heatmap, Anomalies, Health, and How it works.
- Short explanations for what each metric/page means.
- Live polling every two seconds.
- Link to OpenAPI docs for technical users.
- Live detection mask/SAM toggle defaults to off for speed; `auto`, MobileSAM, FastSAM, and SAM vit_b remain selectable when a camera benefits from masks.

## Remaining Improvements

- Calibrate polygons and entry lines from real camera screenshots.
- Install and benchmark `requirements-cv.txt` on the target RTX 4060 machine.
- Add Postgres and rollup tables for multi-store production load.
- Add richer ReID with OSNet/torchreid only if memory and licensing fit deployment.
