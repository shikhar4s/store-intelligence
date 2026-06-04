from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_database_url() -> str:
    if os.getenv("STORE_DB_URL"):
        return str(os.getenv("STORE_DB_URL"))
    if os.getenv("VERCEL"):
        return f"sqlite:///{(Path(gettempdir()) / 'store_intelligence.db').as_posix()}"
    return "sqlite:///./data/store_intelligence.db"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Store Intelligence System"
    version: str = "0.1.0"
    environment: str = os.getenv("ENVIRONMENT", "local")
    database_url: str = _default_database_url()
    ingest_batch_limit: int = int(os.getenv("INGEST_BATCH_LIMIT", "500"))
    stale_feed_minutes: int = int(os.getenv("STALE_FEED_MINUTES", "10"))
    default_store_id: str = os.getenv("DEFAULT_STORE_ID", "STORE_BLR_002")
    pos_correlation_minutes: int = int(os.getenv("POS_CORRELATION_MINUTES", "5"))
    billing_abandon_minutes: int = int(os.getenv("BILLING_ABANDON_MINUTES", "5"))
    reentry_ttl_minutes: int = int(os.getenv("REENTRY_TTL_MINUTES", "30"))
    seed_demo_on_startup: bool = _env_bool("SEED_DEMO_ON_STARTUP", default=bool(os.getenv("VERCEL")))
    layout_config_path: Path = Path(
        os.getenv("LAYOUT_CONFIG_PATH", str(PROJECT_ROOT / "configs" / "store_layout.generated.json"))
    )


def get_settings() -> Settings:
    return Settings()
