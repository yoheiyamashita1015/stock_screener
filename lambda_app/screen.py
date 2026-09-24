"""Yahoo Financeへ接続せず、processedデータだけを絞り込む。"""

import argparse
from dataclasses import dataclass, field, fields
import json
import logging
from typing import Any, Optional

from common.config import BatchConfig, configure_logging
from common.storage import create_storage


logger = logging.getLogger(__name__)


@dataclass
class ScreeningCriteria:
    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    min_per: Optional[float] = None
    max_per: Optional[float] = None
    min_pbr: Optional[float] = None
    max_pbr: Optional[float] = None
    min_dividend_yield: Optional[float] = None
    max_dividend_yield: Optional[float] = None
    min_roe: Optional[float] = None
    min_roa: Optional[float] = None
    min_revenue_growth: Optional[float] = None
    min_eps_growth: Optional[float] = None
    min_eps_consecutive_years: Optional[int] = None
    min_insider_hold: Optional[float] = None
    max_insider_hold: Optional[float] = None
    min_fcf_yield: Optional[float] = None
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    above_sma_20: Optional[bool] = None
    above_sma_50: Optional[bool] = None
    above_sma_200: Optional[bool] = None
    min_pct_from_52w_high: Optional[float] = None
    max_pct_from_52w_high: Optional[float] = None
    trend_signals: list = field(default_factory=list)
    sectors: list = field(default_factory=list)
    exclude_sectors: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, values: dict) -> "ScreeningCriteria":
        if not isinstance(values, dict):
            raise ValueError("conditionsはJSONオブジェクトで指定してください")
        allowed = {item.name for item in fields(cls)}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"未対応の条件です: {', '.join(sorted(unknown))}")
        return cls(**values)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def check_range(value: Any, minimum: Any, maximum: Any) -> bool:
    value = to_float(value)
    if value is None:
        return minimum is None
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def matches_criteria(
    stock: dict, criteria: ScreeningCriteria, include_technicals: bool = True
) -> bool:
    """既存StockScreenerと同じ条件判定を行う。"""
    ranges = (
        ("market_cap", criteria.min_market_cap, criteria.max_market_cap),
        ("per", criteria.min_per, criteria.max_per),
        ("pbr", criteria.min_pbr, criteria.max_pbr),
        ("dividend_yield", criteria.min_dividend_yield, criteria.max_dividend_yield),
        ("insider_hold", criteria.min_insider_hold, criteria.max_insider_hold),
    )
    if any(not check_range(stock.get(key), low, high) for key, low, high in ranges):
        return False

    minimums = (
        ("roe", criteria.min_roe),
        ("roa", criteria.min_roa),
        ("revenue_growth", criteria.min_revenue_growth),
        ("eps_growth_rate", criteria.min_eps_growth),
        ("eps_consecutive_years", criteria.min_eps_consecutive_years),
        ("fcf_yield", criteria.min_fcf_yield),
    )
    for key, minimum in minimums:
        if minimum is not None:
            value = to_float(stock.get(key))
            if value is None or value < minimum:
                return False

    if include_technicals:
        if not check_range(stock.get("rsi"), criteria.min_rsi, criteria.max_rsi):
            return False
        for period, expected in (
            (20, criteria.above_sma_20),
            (50, criteria.above_sma_50),
            (200, criteria.above_sma_200),
        ):
            difference = stock.get(f"pct_from_sma_{period}")
            if expected is not None and difference is not None:
                if (difference > 0) != expected:
                    return False
        if not check_range(
            stock.get("pct_from_high"),
            criteria.min_pct_from_52w_high,
            criteria.max_pct_from_52w_high,
        ):
            return False
        if criteria.trend_signals and stock.get("trend_signal") not in criteria.trend_signals:
            return False

    sector = stock.get("sector", "")
    if criteria.sectors and sector not in criteria.sectors:
        return False
    if criteria.exclude_sectors and sector in criteria.exclude_sectors:
        return False
    return True


def screen_stocks(
    data: list[dict] | dict,
    conditions: ScreeningCriteria | dict,
    include_technicals: bool = True,
) -> list[dict]:
    """processedデータを絞り込む純粋関数。外部I/Oは行わない。"""
    stocks = data.get("stocks", []) if isinstance(data, dict) else data
    criteria = (
        conditions
        if isinstance(conditions, ScreeningCriteria)
        else ScreeningCriteria.from_dict(conditions)
    )
    return [
        stock for stock in stocks
        if matches_criteria(stock, criteria, include_technicals)
    ]


def lambda_handler(event, context):
    """API Gateway/Lambda向けの薄いラッパー。"""
    try:
        payload = event or {}
        if not isinstance(payload, dict):
            raise ValueError("リクエストはJSONオブジェクトで指定してください")
        if isinstance(payload.get("body"), str):
            payload = json.loads(payload["body"] or "{}")
        if not isinstance(payload, dict):
            raise ValueError("リクエストはJSONオブジェクトで指定してください")
        config = BatchConfig.from_env()
        storage = create_storage(config)
        if payload.get("metadata_only") is True:
            updated_at = storage.last_modified("processed/stocks.json")
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps(
                    {
                        "generated_at": updated_at.isoformat()
                        if updated_at is not None
                        else None
                    },
                    ensure_ascii=False,
                ),
            }

        data = storage.read_json("processed/stocks.json")
        results = screen_stocks(
            data,
            payload.get("conditions", {}),
            payload.get("include_technicals", True),
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(
                {
                    "generated_at": data.get("generated_at")
                    if isinstance(data, dict)
                    else None,
                    "count": len(results),
                    "stocks": results,
                },
                ensure_ascii=False,
            ),
        }
    except (ValueError, json.JSONDecodeError) as error:
        return {"statusCode": 400, "body": json.dumps({"error": str(error)}, ensure_ascii=False)}
    except Exception:
        logger.exception("Lambdaスクリーニングで予期しないエラーが発生しました")
        return {"statusCode": 500, "body": json.dumps({"error": "internal server error"})}


def main() -> None:
    parser = argparse.ArgumentParser(description="保存済みデータをスクリーニング")
    parser.add_argument("--conditions", default="{}", help="条件を表すJSON文字列")
    parser.add_argument("--no-technicals", action="store_true")
    args = parser.parse_args()

    config = BatchConfig.from_env()
    configure_logging(config.log_level)
    data = create_storage(config).read_json("processed/stocks.json")
    results = screen_stocks(data, json.loads(args.conditions), not args.no_technicals)
    print(json.dumps({"count": len(results), "stocks": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
