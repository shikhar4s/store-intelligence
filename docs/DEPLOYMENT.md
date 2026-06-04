# Deployment

## One-File Setup

Fresh Windows machine:

```powershell
.\setup.ps1
```

Fresh macOS/Linux machine:

```bash
sh setup.sh
```

The setup script creates `.env`, `data/`, `outputs/`, and `datasets/cctv_footage/`, then runs `docker compose up --build -d` and waits for `/health`.

## Default API Container

The default Docker image is API-only and CPU-safe. It starts:

- FastAPI application
- SQLite WAL database in the `store_data` Docker volume
- dashboard at `/dashboard`
- live viewer page at `/video-demo`
- health and OpenAPI docs

It intentionally does not install OpenCV/Ultralytics by default. That keeps acceptance startup fast and avoids model downloads on machines that only need the API.

## Optional CV Container

To run the detector in Docker:

```bash
INSTALL_CV=true docker compose --profile cv run --rm detector
```

Put CCTV clips in `datasets/cctv_footage/`. Generated events are written to `outputs/events.jsonl`.

To make the API container itself capable of live YOLO/RT-DETR preview:

```bash
INSTALL_CV=true docker compose up --build
```

Model weights are downloaded lazily by Ultralytics and are ignored by git.

## Git Hygiene

Do not commit:

- CCTV clips
- source PDFs/Excel/CSV challenge resources
- SQLite databases
- model weights
- generated event JSONL files
- `outputs/`
- virtual environments

`.gitignore` and `.dockerignore` are configured for these rules.

## Production Path

SQLite is intentionally used for challenge acceptance. For a 40-store production rollout, swap `STORE_DB_URL` to Postgres, keep SQLAlchemy models, add store/date partitioning, and add incremental rollup tables for queue depth, conversion, funnel, and heatmap metrics.
