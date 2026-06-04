PYTHON ?= python
API_URL ?= http://localhost:8000
EVENTS ?= outputs/events.jsonl
COMPOSE ?= docker compose

.PHONY: run up down logs test coverage detect replay smoke cv-detect

run:
	$(COMPOSE) up --build

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=app --cov=pipeline --cov=scripts --cov-report=term-missing

detect:
	$(PYTHON) -m pipeline.detect --input datasets/cctv_footage --output $(EVENTS)

replay:
	$(PYTHON) -m pipeline.replay $(EVENTS) --url $(API_URL)/events/ingest --speed 5

smoke:
	$(PYTHON) -m scripts.smoke_test --url $(API_URL)

cv-detect:
	$(COMPOSE) --profile cv run --rm detector
