# Scoring Alignment Audit

Review date: 2026-05-31.

Sources reviewed page by page:

- `resources/Purplle Tech Challenge 2026 _ Round 2 Problem Statement480e74e.pdf` (12 pages)
- `resources/Assessment  Evaluation Framework.pdf` (4 pages)

This document maps the challenge rubric to the current implementation and records gaps, caveats, and reviewer-facing evidence.

## Acceptance Gate

| PDF Requirement | Status | Implementation Evidence | Notes |
| --- | --- | --- | --- |
| `docker compose up` starts the API with no manual steps beyond clone | Covered | `Dockerfile`, `docker-compose.yml`, `setup.ps1`, `setup.sh`, `requirements.txt`, `app/main.py` | API container does not require GPU/CV model weights; CV image is opt-in with `INSTALL_CV=true`. |
| Detection pipeline produces structured events | Covered | `pipeline/detect.py`, `pipeline/emit.py`, `pipeline/validate_events.py` | Model path emits real detections when CV deps/weights exist; fallback emits low-confidence deterministic events so the repo remains runnable. |
| README explains how to process clips and feed output into API | Covered | `README.md` quickstart, detection, replay, curl sections | Includes `pipeline.detect`, `pipeline.validate_events`, and `pipeline.replay`. |
| `POST /events/ingest` accepts events without 5xx | Covered | `app/ingestion.py`, `app/main.py`, `tests/test_ingest.py` | Batch limit, partial success, idempotency, structured errors. |
| `GET /stores/STORE_BLR_002/metrics` returns valid JSON | Covered | `app/metrics.py`, `app/main.py`, `tests/test_metrics.py` | Added `/metrics` shorthand alias too because the evaluation framework uses shorthand wording. |
| `DESIGN.md` and `CHOICES.md` exist and are non-trivial | Covered | `docs/DESIGN.md`, `docs/CHOICES.md` | Both are challenge-specific and include tradeoffs. |

## Point Breakdown

| Part | PDF Rubric Item | Points | Coverage | How The Code Covers It | Residual Risk |
| --- | --- | ---: | --- | --- | --- |
| A | Entry/exit count accuracy vs ground truth | 10 | Covered with calibration caveat | `pipeline.detect.yolo_events_for_video` detects people, tracks IDs, uses footpoint/centroid crossing over configurable entry line, and emits one `ENTRY`/`EXIT` per track. Camera inference and normalized entry line are in `pipeline/detect.py`; editable example is `configs/cameras.example.yaml`. | Accuracy depends on calibrated entry line and detector performance on held-out clips. No ground-truth labels are provided locally. |
| A | Staff exclusion, re-entry, group handling | 10 | Covered with heuristic caveat | Staff flags are carried in every event and excluded in `app/metrics.py`, `app/funnel.py`, `app/heatmap.py`, and `app/anomalies.py`. Re-entry uses `pipeline/reid.py` gallery and emits `REENTRY`. Group handling is per tracked detection, not per frame group. Live viewer adds segmentation-mask uniform sampling, optional SAM/FastSAM refinement, strict black-uniform scoring for the provided CAM 1 staff clothing, blur-as-real-person evidence, optional staff-area controls, and poster suppression in `app/video_demo.py`. | Staff detection is heuristic unless uniforms and staff areas are calibrated; full cross-camera ReID is lightweight/time-trajectory based. |
| A | Schema compliance and event quality | 10 | Covered | `app/schemas.py` validates event fields, UUIDs, event types, confidence range, UTC timestamps. `pipeline/emit.py` creates schema-shaped events. `pipeline/validate_events.py` validates JSONL output. | Event quality depends on upstream camera/layout calibration. |
| B | API endpoint correctness on held-out event set | 20 | Covered | Required endpoints: `/events/ingest`, `/stores/{id}/metrics`, `/stores/{id}/funnel`, `/stores/{id}/heatmap`, `/stores/{id}/anomalies`, `/health`. Compatibility aliases: `/metrics`, `/funnel`, `/heatmap`, `/anomalies`. Tests cover empty store, staff exclusion, POS correlation, queue abandon, stale feed, DB errors. | Held-out tests may exercise edge windows not represented in fixtures, but core contracts are implemented. |
| B | Funnel accuracy and session deduplication | 10 | Covered | `app/funnel.py` computes session-based stages: Entry, Zone Visit, Billing Queue, Purchase. Reentry does not create a second unique session. POS correlation uses store + timestamp window through `app/metrics.converted_visitor_ids`. | POS has no customer ID, so purchases are necessarily approximate by time window. |
| B | Anomaly detection correctness | 5 | Covered | `app/anomalies.py` detects `BILLING_QUEUE_SPIKE`, `CONVERSION_DROP`, `DEAD_ZONE`, and stale-feed style health warnings. Each anomaly includes severity, evidence, suggested action, and detected timestamp. | Conversion-drop certainty is lower with sparse history, documented via data confidence. |
| C | Containerisation + README | 5 | Covered | `Dockerfile`, `docker-compose.yml`, `.env.example`, `setup.ps1`, `setup.sh`, `Makefile`, `README.md`, `docs/DEPLOYMENT.md`. | Docker engine availability is environment-dependent, but compose config is valid. |
| C | Structured logs + health endpoint | 5 | Covered | Request middleware in `app/main.py` logs JSON with `trace_id`, endpoint, method, store_id, latency_ms, event_count, status_code. `app/health.py` reports DB status, last event per store, stale warnings, version/build, uptime. | None known. |
| C | Test coverage and edge case handling | 10 | Covered | Tests include required prompt headers. Current suite covers ingest, duplicate ids, malformed rows, >500 batch, empty store, all-staff, zero purchases, POS conversion, abandonment, reentry, heatmap confidence, anomalies, health stale feed, DB unavailable, pipeline schema, dashboard, and video-demo role filtering. | Coverage is above threshold, not exhaustive of every real CV failure mode. |
| D | AI usage depth, prompts, `DESIGN.md`, `CHOICES.md` | 15 | Covered | Test files begin with `# PROMPT:` and `# CHANGES MADE:`. `docs/DESIGN.md` has exact `AI-Assisted Decisions` section. `docs/CHOICES.md` covers model/tracker, schema, API/storage tradeoffs. `docs/MODEL_RESEARCH.md` documents model research. | Follow-up answers must be grounded in current code; this doc helps prepare. |
| E | Live dashboard bonus | +10 | Covered | `/dashboard` is a web dashboard polling live API endpoints. `dashboard/terminal_dashboard.py` is a terminal option. `pipeline/replay.py` simulates real-time event flow into `/events/ingest`. `/video-demo` visually demonstrates live detection. | The bonus requires proof during demo: run replay while dashboard is open. |

## Page-by-Page Requirement Mapping

| Problem PDF Page | Requirement Theme | Current Alignment |
| --- | --- | --- |
| 1 | End-to-end raw CCTV to containerized API with live metrics; explain decisions | Implemented via pipeline, FastAPI app, Docker, docs. |
| 2 | Four-stage system: detection, event stream, intelligence API, live dashboard | All four stages implemented. |
| 3 | Dataset edge cases: groups, staff, re-entry, occlusion, billing queue | Handled with tracking, staff flags, ReID gallery, confidence retention, queue events. |
| 4 | Empty periods, camera overlap, POS time-window correlation | Empty stores safe; POS correlation implemented; cross-camera dedup is heuristic. |
| 5 | Event schema and event type catalogue | Implemented in schemas/emitter and validator. |
| 6 | Detection scoring and required API endpoints | Required endpoints implemented; shorthand aliases added for evaluator convenience. |
| 7 | Production readiness, tests, AI engineering, live dashboard | Implemented and tested; docs updated. |
| 8 | Scoring table and acceptance gate | Covered; this document maps each scoring row. |
| 9 | Follow-up questions require code-specific reasoning | Choices/design docs and this audit explain tradeoffs. |
| 10 | Suggested repo structure | Repo follows suggested structure with additional modules. |
| 11 | Submission checklist and north-star conversion metric | README/docs include commands and dashboard URL; metrics center conversion rate. |
| 12 | FAQ: model choice, VLM optional, storage choice, imperfect detection expected, replay allowed | Model/storage/replay choices documented; detection limits are explicit. |

## Changes Made During This Audit

- Added evaluator shorthand aliases:
  - `GET /metrics`
  - `GET /funnel`
  - `GET /heatmap`
  - `GET /anomalies`
- Added tests for `/metrics` and `/funnel` aliases.
- Updated `README.md` to document the shorthand aliases.
- Added this scoring alignment document.

## Highest-Risk Items To Demo Clearly

1. Run the API with Docker or local uvicorn, then call `/health` and `/stores/STORE_BLR_002/metrics`.
2. Run `python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl`.
3. Validate `outputs/events.jsonl` with `python -m pipeline.validate_events outputs/events.jsonl`.
4. Open `/dashboard`, then replay events with `python -m pipeline.replay outputs/events.jsonl --url http://localhost:8000/events/ingest --speed 10`.
5. Explain that detection accuracy is calibration-dependent, but the system keeps confidence, excludes staff, handles reentry, and avoids hardcoded outputs.
