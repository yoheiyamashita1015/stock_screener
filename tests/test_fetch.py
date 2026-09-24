import pickle
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from common.config import BatchConfig
from common.storage import Storage
from src.data_fetcher import DataFetcher
from src.fetch import fetch_one_ticker, run_batch


def complete_raw(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "info": {
            "symbol": ticker,
            "quoteType": "EQUITY",
            "longName": f"{ticker} Inc.",
            "marketCap": 1_000_000_000,
        },
        "financials": {
            "income_stmt": pd.DataFrame(
                [[1.0]], index=["Basic EPS"], columns=["2024"]
            )
        },
        "history": pd.DataFrame({"Close": [100.0]}),
    }


class FakeFetcher:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_stock_info(self, ticker, force_refresh=False):
        return self.raw["info"]

    def get_financials(self, ticker, force_refresh=False):
        return self.raw["financials"]

    def get_stock_history(self, ticker, period="1y", force_refresh=False):
        return self.raw["history"]


class MemoryStorage(Storage):
    def __init__(self):
        self.data = {}
        self.modified = {}

    def exists(self, key):
        return key in self.data

    def read_bytes(self, key):
        return self.data[key]

    def write_bytes(self, key, data):
        self.data[key] = data
        self.modified[key] = datetime.now(timezone.utc)

    def list_keys(self, prefix):
        return sorted(key for key in self.data if key.startswith(prefix))

    def last_modified(self, key):
        return self.modified.get(key)


class FetchOneTickerTest(unittest.TestCase):
    def test_accepts_complete_data(self):
        raw = fetch_one_ticker("AAPL", FakeFetcher(complete_raw()))

        self.assertEqual(raw["ticker"], "AAPL")

    def test_rejects_missing_income_statement(self):
        raw = complete_raw()
        raw["financials"] = {"income_stmt": pd.DataFrame()}

        with self.assertRaisesRegex(RuntimeError, "年次損益計算書"):
            fetch_one_ticker("AAPL", FakeFetcher(raw))

    def test_rejects_missing_history(self):
        raw = complete_raw()
        raw["history"] = pd.DataFrame()

        with self.assertRaisesRegex(RuntimeError, "株価履歴"):
            fetch_one_ticker("AAPL", FakeFetcher(raw))


class BatchResumeTest(unittest.TestCase):
    def test_reacquires_fresh_but_incomplete_raw(self):
        storage = MemoryStorage()
        invalid_raw = complete_raw()
        invalid_raw["info"] = {"symbol": "AAPL", "quoteType": "NONE"}
        storage.write_bytes("raw/AAPL.pkl", pickle.dumps(invalid_raw))
        replacement = complete_raw()
        config = BatchConfig(
            storage_mode="local",
            local_data_dir=None,
            s3_bucket_name="",
            s3_prefix="",
            ticker_file="",
            request_delay_seconds=3,
            request_jitter_seconds=0,
            yahoo_max_requests_per_minute=60,
            raw_max_age_hours=24 * 28,
            log_level="INFO",
        )

        with (
            patch("src.fetch.DataFetcher"),
            patch("src.fetch.fetch_one_ticker", return_value=replacement) as fetch,
        ):
            result = run_batch(
                ["AAPL"], config, storage, include_technicals=False
            )

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["count"], 1)
        fetch.assert_called_once()


class DataFetcherCacheTest(unittest.TestCase):
    def test_redirects_yfinance_internal_cache(self):
        with (
            patch("src.data_fetcher.CACHE_DIR", ".tmp/test-yfinance-cache"),
            patch("src.data_fetcher.yf.set_tz_cache_location") as set_location,
        ):
            fetcher = DataFetcher()

        set_location.assert_called_once_with(fetcher.yfinance_cache_dir)
        self.assertEqual(
            Path(fetcher.yfinance_cache_dir),
            Path(__file__).resolve().parent.parent
            / ".tmp"
            / "test-yfinance-cache"
            / "yfinance",
        )


class StockListFilterTest(unittest.TestCase):
    def setUp(self):
        with patch("src.data_fetcher.yf.set_tz_cache_location"):
            self.fetcher = DataFetcher()

    def test_keeps_common_stock_and_adr(self):
        stocks = pd.DataFrame(
            [
                {"symbol": "AAPL", "name": "Apple Inc. - Common Stock"},
                {
                    "symbol": "BABA",
                    "name": "Alibaba Group Holding Limited American Depositary Shares",
                },
            ]
        )

        result = self.fetcher._filter_supported_stock_list(stocks)

        self.assertEqual(result["symbol"].tolist(), ["AAPL", "BABA"])

    def test_excludes_warrants_units_and_rights_by_name(self):
        stocks = pd.DataFrame(
            [
                {"symbol": "AAA", "name": "Example Corp. Warrants"},
                {"symbol": "BBB", "name": "Example Corp. Units"},
                {"symbol": "CCC", "name": "Example Corp. Rights"},
                {"symbol": "UNIT", "name": "Unitil Corporation Common Stock"},
            ]
        )

        result = self.fetcher._filter_supported_stock_list(stocks)

        self.assertEqual(result["symbol"].tolist(), ["UNIT"])

    def test_excludes_nasdaq_fifth_character_identifiers_without_name(self):
        stocks = pd.DataFrame(
            [
                {"symbol": "ADACW", "name": ""},
                {"symbol": "TESTU", "name": ""},
                {"symbol": "TESTR", "name": ""},
                {"symbol": "GOOGL", "name": ""},
            ]
        )

        result = self.fetcher._filter_supported_stock_list(stocks)

        self.assertEqual(result["symbol"].tolist(), ["GOOGL"])


if __name__ == "__main__":
    unittest.main()
