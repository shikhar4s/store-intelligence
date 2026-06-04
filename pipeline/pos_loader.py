from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from app.layout_store import canonical_store_id


def discover_pos_file(root: Path = Path(".")) -> Optional[Path]:
    candidates = []
    for pattern in ("**/*pos*.csv", "**/*transaction*.csv", "**/Brigade*.csv"):
        candidates.extend(root.glob(pattern))
    filtered = [path for path in candidates if ".venv" not in path.parts and path.is_file()]
    return sorted(filtered, key=lambda p: len(str(p)))[0] if filtered else None


def parse_pos_csv(path: Path, store_id: Optional[str] = None) -> List[Dict]:
    import pandas as pd

    df = pd.read_csv(path)
    transactions: dict[str, dict] = {}
    local_tz = ZoneInfo("Asia/Kolkata")
    for _, row in df.iterrows():
        tx_id = str(row.get("invoice_number") or row.get("transaction_id") or row.get("order_id"))
        raw_store_id = store_id or row.get("store_id") or row.get("store_code")
        canonical = canonical_store_id(raw_store_id)
        date_raw = str(row.get("order_date") or row.get("date") or "").strip()
        time_raw = str(row.get("order_time") or row.get("time") or "00:00:00").strip()
        timestamp = _parse_pos_datetime(date_raw, time_raw, local_tz)
        amount = float(row.get("total_amount") or row.get("basket_value_inr") or row.get("NMV") or 0.0)
        tx_key = f"{canonical}:{tx_id}"
        item = transactions.setdefault(
            tx_key,
            {
                "store_id": canonical,
                "transaction_id": tx_id,
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "amount": 0.0,
                "source_file": str(path),
            },
        )
        item["amount"] += amount
    return list(transactions.values())


def _parse_pos_datetime(date_raw: str, time_raw: str, local_tz: ZoneInfo) -> datetime:
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            local = datetime.strptime(f"{date_raw} {time_raw}", fmt).replace(tzinfo=local_tz)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def infer_clip_start(pos_path: Optional[Path], default: datetime) -> datetime:
    if pos_path is None:
        return default
    transactions = parse_pos_csv(pos_path)
    if not transactions:
        return default
    first = min(datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00")) for tx in transactions)
    return first - timedelta(minutes=30)
