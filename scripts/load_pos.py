from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from app.database import get_db, init_db
from app.pos import ingest_pos_payload
from pipeline.pos_loader import parse_pos_csv


def post_transactions(url: str, transactions: list[dict]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps({"transactions": transactions}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def direct_load(transactions: list[dict]) -> dict:
    init_db()
    db = next(get_db())
    try:
        return ingest_pos_payload(db, {"transactions": transactions})
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load POS CSV transactions into the API or local SQLite DB.")
    parser.add_argument("--csv", required=True, help="POS CSV path")
    parser.add_argument(
        "--store-id",
        default=None,
        help="Optional canonical store id override. When omitted, the CSV store_id column is used if present.",
    )
    parser.add_argument("--url", default="http://localhost:8000/pos/ingest", help="API POS ingest URL")
    parser.add_argument("--direct-db", action="store_true", help="Skip HTTP and write to configured SQLite DB directly")
    args = parser.parse_args()

    transactions = parse_pos_csv(Path(args.csv), store_id=args.store_id)
    if args.direct_db:
        result = direct_load(transactions)
    else:
        try:
            result = post_transactions(args.url, transactions)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            result = direct_load(transactions)
            result["fallback"] = "api_unavailable_direct_db"
    print(json.dumps(result, sort_keys=True))
    if result.get("rejected_count", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
