#!/usr/bin/env sh
set -eu

WITH_CV="${1:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required. Install Docker Desktop or Docker Engine first." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  use_legacy_compose=false
elif command -v docker-compose >/dev/null 2>&1; then
  use_legacy_compose=true
else
  echo "Docker Compose is required. Install Docker Desktop with Compose support." >&2
  exit 1
fi

compose() {
  if [ "$use_legacy_compose" = "true" ]; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if [ "$WITH_CV" = "--with-cv" ]; then
  export INSTALL_CV=true
  echo "CV dependencies enabled for this Docker build."
fi

mkdir -p data outputs datasets/cctv_footage

compose up --build -d

api_port="${API_PORT:-}"
if [ -z "$api_port" ] && [ -f ".env" ]; then
  api_port="$(grep '^API_PORT=' .env | head -n 1 | cut -d= -f2- || true)"
fi
api_port="${api_port:-8000}"

i=0
while [ "$i" -lt 60 ]; do
  if compose exec -T api python - <<'PY'
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
    print(response.read().decode())
PY
  then
    echo "API is ready."
    echo "Dashboard: http://127.0.0.1:${api_port}/dashboard"
    echo "Live detection viewer: http://127.0.0.1:${api_port}/video-demo"
    echo "OpenAPI docs: http://127.0.0.1:${api_port}/docs"
    exit 0
  fi
  i=$((i + 1))
  sleep 2
done

compose logs --tail=80 api
echo "API did not become healthy within 120 seconds." >&2
exit 1
