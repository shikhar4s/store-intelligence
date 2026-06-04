FROM python:3.12-slim

ARG INSTALL_CV=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    STORE_DB_URL=sqlite:////data/store_intelligence.db \
    DEFAULT_STORE_ID=STORE_BLR_002 \
    LAYOUT_CONFIG_PATH=/app/configs/store_layout.generated.json \
    ULTRALYTICS_CONFIG_DIR=/tmp/ultralytics \
    YOLO_CONFIG_DIR=/tmp/ultralytics

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && mkdir -p /data /app/outputs /tmp/ultralytics \
    && chown -R app:app /data /app /tmp/ultralytics

COPY requirements.txt requirements-cv.txt ./
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt \
    && if [ "$INSTALL_CV" = "true" ]; then pip install -r requirements-cv.txt; fi

COPY --chown=app:app app app
COPY --chown=app:app pipeline pipeline
COPY --chown=app:app dashboard dashboard
COPY --chown=app:app scripts scripts
COPY --chown=app:app configs configs
COPY --chown=app:app docs docs
COPY --chown=app:app README.md README.md

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.getenv('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:' + port + '/health', timeout=3).read()"

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
