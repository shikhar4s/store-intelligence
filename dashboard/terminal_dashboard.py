from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Polling terminal dashboard for Store Intelligence.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--store-id", default="STORE_BLR_002")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    while True:
        metrics = fetch(f"{base}/stores/{args.store_id}/metrics")
        os.system("cls" if os.name == "nt" else "clear")
        print("Store Intelligence Dashboard")
        print("=" * 34)
        print(f"Store:             {args.store_id}")
        print(f"Unique visitors:   {metrics.get('unique_visitors', 0)}")
        print(f"Conversion rate:   {metrics.get('conversion_rate', 0) * 100:.1f}%")
        print(f"Queue depth:       {metrics.get('current_queue_depth', 0)}")
        print(f"Last event:        {metrics.get('last_event_timestamp') or '-'}")
        print(f"Confidence:        {metrics.get('data_confidence', {}).get('reason')}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
