# Vercel Deployment

Vercel can host the FastAPI API and dashboard through its Python Runtime. It does not run this repository's `Dockerfile` or `docker-compose.yml` directly. Keep Docker for local judging setup and container platforms such as Railway, Render, Fly.io, Azure Container Apps, or a VM.

## What Works On Vercel

- `/dashboard`
- `/stores`
- `/events/ingest`
- `/stores/{id}/metrics`
- `/stores/{id}/funnel`
- `/stores/{id}/heatmap`
- `/stores/{id}/anomalies`
- `/health`
- `/docs`

The Vercel deployment uses `api/index.py` as the Python Function entrypoint and `vercel.json` to rewrite all routes to the FastAPI app.

## What Is Limited On Vercel

- Docker images are not run by Vercel.
- `docker compose` services and named volumes are not available.
- SQLite is stored in `/tmp` unless `STORE_DB_URL` points to an external database. `/tmp` is ephemeral per serverless instance.
- CCTV clips, model weights, raw resources, and generated outputs are excluded from the Vercel upload.
- The `/video-demo` page can render, but real YOLO/RT-DETR live CCTV streaming is intended for the Docker/local runtime because model weights, OpenCV, GPU acceleration, and long-running MJPEG streams are not reliable serverless workloads.

## First Deployment

1. Push the repository to GitHub.
2. Import `https://github.com/shikhar4s/store-intelligence` in Vercel.
3. Use the project root as the root directory.
4. Leave Framework Preset as Other or let Vercel auto-detect Python.
5. Leave Build Command blank.
6. Leave Output Directory blank.
7. Deploy.

The checked-in `vercel.json` routes every path to `api/index.py`. `requirements.txt` is intentionally lightweight and excludes OpenCV/Ultralytics. `requirements-cv.txt` is only for Docker/local CV runs.

## Recommended Environment Variables

For a simple public demo:

```text
ENVIRONMENT=production
SEED_DEMO_ON_STARTUP=true
DEFAULT_STORE_ID=STORE_BLR_002
```

`SEED_DEMO_ON_STARTUP` defaults to true when Vercel sets the `VERCEL` environment variable. This seeds small synthetic events for both stores when the ephemeral SQLite database is empty, so the dashboard is not blank after cold start.

For a real persistent deployment, use an external database:

```text
STORE_DB_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
SEED_DEMO_ON_STARTUP=false
```

If you use Postgres, add the matching driver to `requirements.txt` before deploying. SQLite on Vercel is acceptable only for demo data because it is ephemeral.

## Verify After Deploy

Replace `<deployment-url>` with the URL returned by Vercel:

```bash
curl https://<deployment-url>/health
curl https://<deployment-url>/stores
curl https://<deployment-url>/stores/STORE_BLR_002/metrics
```

Then open:

```text
https://<deployment-url>/dashboard
https://<deployment-url>/docs
```

## Docker Deployment Remains Available

For the full challenge demo with downloaded CCTV clips, YOLO/RT-DETR model warm-up, live video detection, dashboard seed from clips, and tracker smoke checks, use:

```powershell
.\setup.ps1
```

That path uses Docker because it needs local media files, model weights, OpenCV runtime libraries, and long-running video streams.
