"""ECS RunTask/Fargateで実行するデータ取得バッチ。"""

import argparse
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import pickle
import re

import pandas as pd

from common.config import BatchConfig, configure_logging
from .data_fetcher import DataFetcher
from .process import build_processed_dataset
from .validation import raw_validation_errors
from common.storage import Storage, create_storage


logger = logging.getLogger(__name__)
TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.^=-]+$")


def _read_ticker_file(path: str) -> list[str]:
    file_path = Path(path)
    if file_path.suffix.lower() == ".csv":
        frame = pd.read_csv(file_path)
        column = "ticker" if "ticker" in frame.columns else "symbol"
        if column not in frame.columns:
            raise ValueError("ticker CSVには ticker または symbol 列が必要です")
        return frame[column].dropna().astype(str).tolist()
    return [
        line.strip()
        for line in file_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def load_tickers(
    fetcher: DataFetcher,
    config: BatchConfig,
    command_tickers: str = "",
    limit: int | None = None,
) -> list[str]:
    if command_tickers:
        values = command_tickers.split(",")
    elif config.ticker_file:
        values = _read_ticker_file(config.ticker_file)
    else:
        stocks = fetcher.get_us_stock_list()
        values = stocks["symbol"].tolist() if "symbol" in stocks.columns else []

    tickers = []
    seen = set()
    for value in values:
        ticker = str(value).strip().upper()
        if not ticker or ticker in seen:
            continue
        if not TICKER_PATTERN.fullmatch(ticker):
            logger.warning("不正なtickerを除外します: %s", ticker)
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers[:limit] if limit is not None else tickers


def fetch_one_ticker(
    ticker: str,
    fetcher: DataFetcher,
    force_refresh: bool = False,
) -> dict:
    """既存DataFetcherを逐次利用し、1銘柄分のrawデータを返す。"""
    info = fetcher.get_stock_info(ticker, force_refresh=force_refresh)
    if not info:
        raise RuntimeError("基本情報を取得できませんでした")

    financials = fetcher.get_financials(ticker, force_refresh=force_refresh)
    history = fetcher.get_stock_history(
        ticker, period="1y", force_refresh=force_refresh
    )
    raw = {
        "ticker": ticker,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "info": info,
        "financials": financials,
        "history": history,
    }
    errors = raw_validation_errors(raw)
    if errors:
        raise RuntimeError(f"必須データが不足しています: {', '.join(errors)}")
    return raw


def run_batch(
    tickers: list[str],
    config: BatchConfig,
    storage: Storage,
    force: bool = False,
    include_technicals: bool = True,
) -> dict:
    """tickerを逐次取得する。各成功直後にrawを保存するため再開可能。"""
    fetcher = DataFetcher()
    success = 0
    failed = 0
    skipped = 0
    total = len(tickers)

    logger.info("バッチ開始")
    logger.info(
        "対象ticker数=%d storage_mode=%s Yahoo上限=%.1f回/分 最小間隔=%.2f秒 ゆらぎ最大=%.2f秒",
        total,
        config.storage_mode,
        config.yahoo_max_requests_per_minute,
        config.request_delay_seconds,
        config.request_jitter_seconds,
    )
    freshness_limit = datetime.now(timezone.utc) - timedelta(
        hours=config.raw_max_age_hours
    )

    for position, ticker in enumerate(tickers, start=1):
        raw_key = f"raw/{ticker}.pkl"
        logger.info("現在のticker=%s (%d/%d)", ticker, position, total)
        if not force:
            modified_at = storage.last_modified(raw_key)
            if modified_at is not None and modified_at >= freshness_limit:
                try:
                    saved_raw = pickle.loads(storage.read_bytes(raw_key))
                    errors = raw_validation_errors(saved_raw)
                except Exception as error:
                    errors = [f"読み込みエラー: {error}"]
                if not errors:
                    skipped += 1
                    logger.info("取得済みrawが有効なためスキップ ticker=%s", ticker)
                    continue
                logger.warning(
                    "取得済みrawが不完全なため再取得 ticker=%s 不足=%s",
                    ticker,
                    ", ".join(errors),
                )
            elif modified_at is not None:
                logger.info("rawの有効期間切れのため再取得 ticker=%s", ticker)

        try:
            raw = fetch_one_ticker(
                ticker,
                fetcher,
                force_refresh=force,
            )
            storage.write_bytes(raw_key, pickle.dumps(raw, protocol=pickle.HIGHEST_PROTOCOL))
            success += 1
            logger.info("取得成功・途中保存 ticker=%s key=%s", ticker, raw_key)
        except Exception:
            failed += 1
            logger.exception("取得失敗 ticker=%s（次のtickerへ継続）", ticker)

    dataset = build_processed_dataset(storage, include_technicals=include_technicals)
    logger.info("最終保存 key=processed/stocks.json count=%d", dataset["count"])
    logger.info(
        "バッチ終了 合計成功数=%d 合計失敗数=%d スキップ数=%d",
        success,
        failed,
        skipped,
    )
    return {"success": success, "failed": failed, "skipped": skipped, **dataset}


def main() -> None:
    parser = argparse.ArgumentParser(description="Yahoo Financeデータ取得バッチ")
    parser.add_argument("--tickers", default="", help="カンマ区切りticker（例: AAPL,MSFT）")
    parser.add_argument("--limit", type=int, default=None, help="先頭から処理する最大銘柄数")
    parser.add_argument("--force", action="store_true", help="保存済みrawも再取得する")
    parser.add_argument("--no-technicals", action="store_true", help="テクニカル指標を加工しない")
    parser.add_argument("--process-only", action="store_true", help="取得せずrawからprocessedを再生成する")
    args = parser.parse_args()

    config = BatchConfig.from_env()
    configure_logging(config.log_level)
    storage = create_storage(config)

    if args.process_only:
        dataset = build_processed_dataset(storage, include_technicals=not args.no_technicals)
        logger.info("加工完了 key=processed/stocks.json count=%d", dataset["count"])
        return

    fetcher = DataFetcher()
    tickers = load_tickers(fetcher, config, args.tickers, args.limit)
    if not tickers:
        raise RuntimeError("対象tickerがありません")
    run_batch(
        tickers,
        config,
        storage,
        force=args.force,
        include_technicals=not args.no_technicals,
    )


if __name__ == "__main__":
    main()
