"""取得データを保存・加工してよいか判定する共通処理。"""

import math
from typing import Any


def is_valid_stock_info(info: Any) -> bool:
    """米国株スクリーニングに必要な基本情報が揃っているか判定する。"""
    if not isinstance(info, dict):
        return False
    if str(info.get("quoteType", "")).upper() != "EQUITY":
        return False
    if not (info.get("longName") or info.get("shortName")):
        return False

    try:
        market_cap = float(info.get("marketCap"))
    except (TypeError, ValueError):
        return False
    return math.isfinite(market_cap) and market_cap > 0


def has_required_financial_data(financials: Any) -> bool:
    """EPS計算に必要な年次損益計算書が取得できているか判定する。"""
    if not isinstance(financials, dict):
        return False
    income_statement = financials.get("income_stmt")
    return income_statement is not None and not getattr(
        income_statement, "empty", True
    )


def has_history_data(history: Any) -> bool:
    """株価履歴が1行以上あるか判定する。"""
    return history is not None and not getattr(history, "empty", True)


def raw_validation_errors(raw: Any) -> list[str]:
    """rawデータの不足項目名を返す。空なら保存・加工可能。"""
    if not isinstance(raw, dict):
        return ["raw形式"]

    errors = []
    if not raw.get("ticker"):
        errors.append("ticker")
    if not is_valid_stock_info(raw.get("info")):
        errors.append("基本情報")
    if not has_required_financial_data(raw.get("financials")):
        errors.append("年次損益計算書")
    if not has_history_data(raw.get("history")):
        errors.append("株価履歴")
    return errors
