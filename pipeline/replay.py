from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List


def load_events(path: Path) -> List[dict]:
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    return sorted(events, key=lambda item: item["timestamp"])


def post_batch(url: str, events: List[dict]) -> dict:
    data = json.dumps({"events": events}).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay JSONL events into the ingest API.")
    parser.add_argument("path", help="JSONL event path")
    parser.add_argument("--url", default="http://localhost:8000/events/ingest", help="Ingest URL")
    parser.add_argument("--speed", type=float, default=5.0, help="Replay speed multiplier")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size; 1 gives visible live dashboard updates")
    args = parser.parse_args()

    events = load_events(Path(args.path))
    previous_ts = None
    accepted = duplicates = rejected = 0
    for index in range(0, len(events), args.batch_size):
        batch = events[index : index + args.batch_size]
        current_ts = datetime.fromisoformat(batch[0]["timestamp"].replace("Z", "+00:00"))
        if previous_ts is not None:
            delay = max(0.0, (current_ts - previous_ts).total_seconds() / max(args.speed, 0.1))
            time.sleep(min(delay, 10.0))
        result = post_batch(args.url, batch)
        accepted += result.get("accepted_count", 0)
        duplicates += result.get("duplicate_count", 0)
        rejected += result.get("rejected_count", 0)
        previous_ts = current_ts
    print(json.dumps({"accepted_count": accepted, "duplicate_count": duplicates, "rejected_count": rejected}))


if __name__ == "__main__":
    main()
