"""AWSバッチ用の環境変数設定。"""

from dataclasses import dataclass
import os
from pathlib import Path

from config import (
    REQUEST_DELAY_SECONDS,
    REQUEST_JITTER_SECONDS,
    YAHOO_MAX_REQUESTS_PER_MINUTE,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BatchConfig:
    storage_mode: str
    local_data_dir: Path
    s3_bucket_name: str
    s3_prefix: str
    ticker_file: str
    request_delay_seconds: float
    request_jitter_seconds: float
    yahoo_max_requests_per_minute: float
    raw_max_age_hours: int
    log_level: str

    @classmethod
    def from_env(cls) -> "BatchConfig":
        mode = os.getenv("STORAGE_MODE", "local").strip().lower()
        if mode not in {"local", "s3"}:
            raise ValueError("STORAGE_MODE は local または s3 を指定してください")

        bucket = os.getenv("S3_BUCKET_NAME", "").strip()
        if mode == "s3" and not bucket:
            raise ValueError("STORAGE_MODE=s3 の場合は S3_BUCKET_NAME が必要です")

        data_dir = Path(os.getenv("LOCAL_DATA_DIR", str(PROJECT_ROOT / "data")))
        return cls(
            storage_mode=mode,
            local_data_dir=data_dir,
            s3_bucket_name=bucket,
            s3_prefix=os.getenv("S3_PREFIX", "stock-screener").strip("/"),
            ticker_file=os.getenv("TICKER_FILE", "").strip(),
            request_delay_seconds=REQUEST_DELAY_SECONDS,
            request_jitter_seconds=REQUEST_JITTER_SECONDS,
            yahoo_max_requests_per_minute=YAHOO_MAX_REQUESTS_PER_MINUTE,
            raw_max_age_hours=int(os.getenv("RAW_MAX_AGE_HOURS", str(24 * 28))),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


def configure_logging(level: str) -> None:
    import logging

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
