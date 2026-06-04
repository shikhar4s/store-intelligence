#!/usr/bin/env sh
set -eu
python -m pipeline.detect --input "${1:-datasets/cctv_footage}" --output "${2:-outputs/events.jsonl}"
