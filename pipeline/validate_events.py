from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.schemas import EventIn


def validate_file(path: Path) -> tuple[int, int]:
    ok = 0
    failed = 0
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = EventIn.model_validate_json(line)
                if event.event_id in seen:
                    raise ValueError("duplicate event_id")
                seen.add(event.event_id)
                ok += 1
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                print(f"{path}:{line_number}: {exc}", file=sys.stderr)
                failed += 1
    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate pipeline JSONL events against the event schema.")
    parser.add_argument("path", help="JSONL event file")
    args = parser.parse_args()
    ok, failed = validate_file(Path(args.path))
    print(json.dumps({"valid_events": ok, "invalid_events": failed}))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
