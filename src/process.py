"""取得済みrawデータを既存ロジックで加工する。"""

from datetime import datetime, timezone
import logging
import math
import pickle
from typing import Any

import numpy as np
import pandas as pd

from .fundamental import FundamentalAnalyzer
from common.storage import Storage
from .technical import TechnicalAnalyzer, get_trend_signal
from .validation import raw_validation_errors


logger = logging.getLogger(__name__)


def _json_value(value: Any) -> Any:
    """numpy/pandas値を標準JSONで表現できる値へ変換する。"""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def process_stock(raw: dict, include_technicals: bool = True) -> dict:
    """1銘柄のrawデータからスクリーニング用レコードを作る。"""
    ticker = raw["ticker"]
    info = raw.get("info") or {}
    financials = raw.get("financials") or {}

    result = FundamentalAnalyzer().get_all_fundamentals(info, financials)
    result["ticker"] = ticker

    history = raw.get("history")
    if include_technicals and isinstance(history, pd.DataFrame) and not history.empty:
        technicals = TechnicalAnalyzer(history).get_all_technicals()
        result.update(technicals)
        result["trend_signal"] = get_trend_signal(technicals)

    return _json_value(result)


def build_processed_dataset(
    storage: Storage, include_technicals: bool = True
) -> dict:
    """保存済みrawを全件加工し、processed/stocks.jsonへ保存する。"""
    stocks = []
    for key in storage.list_keys("raw"):
        if not key.endswith(".pkl"):
            continue
        try:
            raw = pickle.loads(storage.read_bytes(key))
            errors = raw_validation_errors(raw)
            if errors:
                logger.warning(
                    "不完全なrawをprocessedから除外 key=%s 不足=%s",
                    key,
                    ", ".join(errors),
                )
                continue
            stocks.append(process_stock(raw, include_technicals=include_technicals))
        except Exception:
            logger.exception("rawデータの加工失敗 key=%s（次のデータへ継続）", key)

    stocks.sort(key=lambda item: item.get("ticker", ""))
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(stocks),
        "stocks": stocks,
    }
    storage.write_json("processed/stocks.json", dataset)
    return dataset
