import unittest

import pandas as pd

from src.validation import (
    has_required_financial_data,
    is_valid_stock_info,
    raw_validation_errors,
)


def valid_info() -> dict:
    return {
        "symbol": "AAPL",
        "quoteType": "EQUITY",
        "longName": "Apple Inc.",
        "marketCap": 1_000_000_000,
    }


def valid_financials() -> dict:
    return {
        "income_stmt": pd.DataFrame(
            [[1.0]], index=["Basic EPS"], columns=["2024"]
        )
    }


class StockInfoValidationTest(unittest.TestCase):
    def test_accepts_equity_with_name_and_market_cap(self):
        self.assertTrue(is_valid_stock_info(valid_info()))

    def test_rejects_quote_type_none_response(self):
        info = {
            "symbol": "MMC",
            "quoteType": "NONE",
            "tradeable": False,
        }

        self.assertFalse(is_valid_stock_info(info))

    def test_requires_annual_income_statement(self):
        self.assertFalse(has_required_financial_data({"income_stmt": pd.DataFrame()}))


class RawValidationTest(unittest.TestCase):
    def test_accepts_complete_raw(self):
        raw = {
            "ticker": "AAPL",
            "info": valid_info(),
            "financials": valid_financials(),
            "history": pd.DataFrame({"Close": [100.0]}),
        }

        self.assertEqual(raw_validation_errors(raw), [])

    def test_reports_all_missing_required_sections(self):
        raw = {
            "ticker": "MMC",
            "info": {"symbol": "MMC", "quoteType": "NONE"},
            "financials": {"income_stmt": pd.DataFrame()},
            "history": pd.DataFrame(),
        }

        self.assertEqual(
            raw_validation_errors(raw),
            ["基本情報", "年次損益計算書", "株価履歴"],
        )


if __name__ == "__main__":
    unittest.main()
