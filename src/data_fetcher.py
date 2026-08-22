"""データ取得モジュール - Yahoo Financeからの株価データ取得"""

import os
import json
import logging
import random
import threading
import time
import pickle
from datetime import datetime, timedelta
from typing import Optional, Callable, TypeVar

import pandas as pd
import yfinance as yf
import requests

from .validation import has_required_financial_data, is_valid_stock_info

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    CACHE_DIR, REQUEST_DELAY_SECONDS,
    REQUEST_JITTER_SECONDS,
    CACHE_EXPIRY_STOCK_LIST_HOURS, CACHE_EXPIRY_INFO_HOURS,
    CACHE_EXPIRY_FINANCIALS_HOURS, CACHE_EXPIRY_HISTORY_HOURS,
    RETRY_WAIT_SECONDS, RETRY_MAX_ATTEMPTS,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)


class YahooRateLimiter:
    """同一プロセス内のYahoo Finance呼び出し開始間隔を制御する。"""

    def __init__(self, min_interval_seconds: float, jitter_seconds: float = 0):
        self.min_interval_seconds = min_interval_seconds
        self.jitter_seconds = jitter_seconds
        self._last_started_at: Optional[float] = None
        self._lock = threading.Lock()

    def wait(self, ticker: str = "", operation: str = "") -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_started_at is not None:
                interval = self.min_interval_seconds + random.uniform(
                    0, self.jitter_seconds
                )
                wait_seconds = self._last_started_at + interval - now
                if wait_seconds > 0:
                    logger.debug(
                        "Yahoo Finance呼び出し待機 %.2f秒 ticker=%s operation=%s",
                        wait_seconds,
                        ticker,
                        operation,
                    )
                    time.sleep(wait_seconds)
            self._last_started_at = time.monotonic()


YAHOO_RATE_LIMITER = YahooRateLimiter(
    REQUEST_DELAY_SECONDS, REQUEST_JITTER_SECONDS
)


def _is_rate_limit_error(e: Exception) -> bool:
    """429 / レート制限エラーかどうかを判定"""
    msg = str(e).lower()
    return (
        "429" in msg
        or "too many requests" in msg
        or "rate limit" in msg
        or "ratelimit" in msg
        or type(e).__name__ in ("YFRateLimitError", "YFTooManyRequestsError")
    )


def with_retry(func: Callable[..., T], *args, ticker: str = "", **kwargs) -> T:
    """
    レート制限エラー時に指数バックオフでリトライする汎用ラッパー

    待機時間: RETRY_WAIT_SECONDS × 2 ** (試行回数 - 1) 秒
    最大3試行の既定値では、失敗後に60秒、120秒待機します。
    """
    last_error = None

    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                label = f"[{ticker}] " if ticker else ""
                logger.warning(
                    "%sレート制限エラー（試行 %d/%d）: %s",
                    label, attempt, RETRY_MAX_ATTEMPTS, e,
                )
                if attempt >= RETRY_MAX_ATTEMPTS:
                    break
                wait = RETRY_WAIT_SECONDS * (2 ** (attempt - 1))
                logger.info("%s%d秒待機後にリトライします", label, wait)
                time.sleep(wait)
            else:
                raise  # レート制限以外のエラーはそのまま再送出

    # 全試行失敗
    raise last_error


class DataFetcher:
    """株価データ取得クラス"""

    def __init__(self):
        self.cache_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            CACHE_DIR
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self.yfinance_cache_dir = os.path.join(self.cache_dir, "yfinance")
        os.makedirs(self.yfinance_cache_dir, exist_ok=True)
        # Cookie・タイムゾーンDBもOSのユーザーディレクトリではなく、
        # 明示したキャッシュ領域へ保存する。
        yf.set_tz_cache_location(self.yfinance_cache_dir)

    def get_us_stock_list(self) -> pd.DataFrame:
        """米国株のティッカーリストを取得"""
        cache_file = os.path.join(self.cache_dir, "us_stocks_list.pkl")

        # キャッシュが有効かチェック
        if self._is_cache_valid(cache_file, hours=CACHE_EXPIRY_STOCK_LIST_HOURS):
            return pd.read_pickle(cache_file)

        # NASDAQとNYSEの銘柄リストを取得
        stocks_df = self._fetch_stock_list_from_exchanges()

        # キャッシュに保存
        stocks_df.to_pickle(cache_file)

        return stocks_df

    def _fetch_stock_list_from_exchanges(self) -> pd.DataFrame:
        """取引所から銘柄リストを取得（NASDAQ公式FTPデータを優先使用）"""
        # 第1優先: NASDAQ公式FTP（NASDAQ/NYSE/AMEX全銘柄、日次更新）
        result = self._fetch_from_nasdaq_ftp()
        if not result.empty:
            return result

        # 第2優先: GitHubメンテナンス済み銘柄リスト（約7,400銘柄）
        result = self._fetch_from_github()
        if not result.empty:
            return result

        # 第3優先: NASDAQ スクリーナーAPI
        result = self._fetch_from_nasdaq_api()
        if not result.empty:
            return result

        # 第4優先: S&P 500（Wikipedia）
        return self._get_sp500_tickers()

    def _fetch_from_nasdaq_ftp(self) -> pd.DataFrame:
        """NASDAQ公式FTPから全上場銘柄を取得"""
        all_stocks = []

        # NASDAQ上場銘柄
        # 形式: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
        try:
            url = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                stocks = []
                for line in response.text.strip().split("\n")[1:]:  # ヘッダー行をスキップ
                    parts = line.split("|")
                    if len(parts) < 7:
                        continue
                    symbol = parts[0].strip()
                    name = parts[1].strip()
                    test_issue = parts[3].strip()
                    fin_status = parts[4].strip()
                    etf = parts[6].strip()
                    # ETF・テスト銘柄・財務問題銘柄・特殊記号を除外
                    if etf == "N" and test_issue == "N" and fin_status == "N" and self._is_valid_symbol(symbol):
                        stocks.append({"symbol": symbol, "name": name, "exchange": "NASDAQ",
                                       "marketCap": None, "sector": None, "industry": None})
                if stocks:
                    all_stocks.append(pd.DataFrame(stocks))
                    print(f"NASDAQ FTP: {len(stocks)}銘柄取得")
        except Exception as e:
            print(f"NASDAQ FTP取得エラー: {e}")

        # NYSE/AMEX等の上場銘柄
        # 形式: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
        try:
            url = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                exchange_map = {"N": "NYSE", "A": "AMEX", "P": "NYSE Arca"}
                stocks = []
                for line in response.text.strip().split("\n")[1:]:  # ヘッダー行をスキップ
                    parts = line.split("|")
                    if len(parts) < 7:
                        continue
                    symbol = parts[0].strip()
                    name = parts[1].strip()
                    exchange_code = parts[2].strip()
                    etf = parts[4].strip()
                    test_issue = parts[6].strip()
                    if (exchange_code in exchange_map and etf == "N"
                            and test_issue == "N" and self._is_valid_symbol(symbol)):
                        stocks.append({"symbol": symbol, "name": name,
                                       "exchange": exchange_map[exchange_code],
                                       "marketCap": None, "sector": None, "industry": None})
                if stocks:
                    all_stocks.append(pd.DataFrame(stocks))
                    print(f"NYSE/AMEX FTP: {len(stocks)}銘柄取得")
        except Exception as e:
            print(f"NYSE/AMEX FTP取得エラー: {e}")

        if all_stocks:
            combined = pd.concat(all_stocks, ignore_index=True)
            return combined[["symbol", "name", "exchange", "marketCap", "sector", "industry"]]

        return pd.DataFrame(columns=["symbol", "name", "exchange", "marketCap", "sector", "industry"])

    def _is_valid_symbol(self, symbol: str) -> bool:
        """有効なティッカーシンボルかチェック（ワラント・ライツ・ユニット等を除外）"""
        if not symbol or len(symbol) > 5:
            return False
        # 特殊記号を含む場合は除外（ワラント: +W、ライツ: +R、ユニット: +U 等）
        return all(c.isalpha() or c == "-" for c in symbol)

    def _fetch_from_github(self) -> pd.DataFrame:
        """GitHubメンテナンス済み銘柄リストから取得（FTPが利用不可の場合のフォールバック）"""
        base_url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main"
        exchange_files = {
            "NASDAQ": f"{base_url}/nasdaq/nasdaq_tickers.txt",
            "NYSE": f"{base_url}/nyse/nyse_tickers.txt",
            "AMEX": f"{base_url}/amex/amex_tickers.txt",
        }
        all_stocks = []

        for exchange, url in exchange_files.items():
            try:
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    symbols = [s.strip() for s in response.text.strip().split("\n") if s.strip()]
                    stocks = [
                        {"symbol": s, "name": "", "exchange": exchange,
                         "marketCap": None, "sector": None, "industry": None}
                        for s in symbols if self._is_valid_symbol(s)
                    ]
                    if stocks:
                        all_stocks.append(pd.DataFrame(stocks))
                        print(f"GitHub ({exchange}): {len(stocks)}銘柄取得")
            except Exception as e:
                print(f"GitHub ({exchange}) 取得エラー: {e}")

        if all_stocks:
            combined = pd.concat(all_stocks, ignore_index=True)
            return combined[["symbol", "name", "exchange", "marketCap", "sector", "industry"]]

        return pd.DataFrame(columns=["symbol", "name", "exchange", "marketCap", "sector", "industry"])

    def _fetch_from_nasdaq_api(self) -> pd.DataFrame:
        """NASDAQ スクリーナーAPIから銘柄リストを取得（フォールバック用）"""
        all_stocks = []
        nasdaq_url = "https://api.nasdaq.com/api/screener/stocks"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for exchange in ["NASDAQ", "NYSE", "AMEX"]:
            try:
                params = {"tableonly": "true", "limit": 10000, "exchange": exchange}
                response = requests.get(nasdaq_url, headers=headers, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and "rows" in data["data"]:
                        df = pd.DataFrame(data["data"]["rows"])
                        df["exchange"] = exchange
                        all_stocks.append(df)
                        print(f"NASDAQ API ({exchange}): {len(df)}銘柄取得")
            except Exception as e:
                print(f"NASDAQ API ({exchange}) 取得エラー: {e}")

        if all_stocks:
            combined = pd.concat(all_stocks, ignore_index=True)
            if "symbol" in combined.columns:
                for col in ["marketCap", "sector", "industry"]:
                    if col not in combined.columns:
                        combined[col] = None
                return combined[["symbol", "name", "exchange", "marketCap", "sector", "industry"]].copy()

        return pd.DataFrame(columns=["symbol", "name", "exchange", "marketCap", "sector", "industry"])

    def _get_sp500_tickers(self) -> pd.DataFrame:
        """S&P 500銘柄リストを取得（フォールバック用）"""
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            sp500 = tables[0]
            sp500 = sp500.rename(columns={
                "Symbol": "symbol",
                "Security": "name",
                "GICS Sector": "sector",
                "GICS Sub-Industry": "industry"
            })
            sp500["exchange"] = "NYSE/NASDAQ"
            sp500["marketCap"] = None
            return sp500[["symbol", "name", "exchange", "marketCap", "sector", "industry"]]
        except Exception as e:
            print(f"S&P 500リスト取得エラー: {e}")
            return pd.DataFrame(columns=["symbol", "name", "exchange", "marketCap", "sector", "industry"])

    def get_stock_info(self, ticker: str, force_refresh: bool = False) -> Optional[dict]:
        """個別銘柄の詳細情報を取得"""
        cache_file = os.path.join(self.cache_dir, f"info_{ticker}.json")

        if not force_refresh and self._is_cache_valid(cache_file, hours=CACHE_EXPIRY_INFO_HOURS):
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_info = json.load(f)
            if is_valid_stock_info(cached_info):
                return cached_info
            logger.warning("不完全な基本情報キャッシュを無視します ticker=%s", ticker)

        try:
            def fetch():
                YAHOO_RATE_LIMITER.wait(ticker, "info")
                return yf.Ticker(ticker).info

            info = with_retry(fetch, ticker=ticker)

            if not is_valid_stock_info(info):
                logger.warning("基本情報が不完全です ticker=%s", ticker)
                return None

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)

            return info
        except Exception as e:
            logger.warning("情報取得エラー ticker=%s: %s", ticker, e)
            return None

    def get_stock_history(
        self, ticker: str, period: str = "1y", force_refresh: bool = False
    ) -> Optional[pd.DataFrame]:
        """株価の履歴データを取得"""
        cache_file = os.path.join(self.cache_dir, f"history_{ticker}_{period}.pkl")

        if not force_refresh and self._is_cache_valid(cache_file, hours=CACHE_EXPIRY_HISTORY_HOURS):
            return pd.read_pickle(cache_file)

        try:
            def fetch():
                YAHOO_RATE_LIMITER.wait(ticker, f"history:{period}")
                return yf.Ticker(ticker).history(period=period)

            history = with_retry(fetch, ticker=ticker)

            if not history.empty:
                history.to_pickle(cache_file)

            return history
        except Exception as e:
            logger.warning("履歴取得エラー ticker=%s: %s", ticker, e)
            return None

    def get_financials(self, ticker: str, force_refresh: bool = False) -> dict:
        """財務データを取得"""
        cache_file = os.path.join(self.cache_dir, f"financials_{ticker}.pkl")

        if not force_refresh and self._is_cache_valid(cache_file, hours=CACHE_EXPIRY_FINANCIALS_HOURS):
            with open(cache_file, "rb") as f:
                cached_financials = pickle.load(f)
            if has_required_financial_data(cached_financials):
                return cached_financials
            logger.warning("不完全な財務キャッシュを無視します ticker=%s", ticker)

        stock = yf.Ticker(ticker)
        statements = {
            "income_stmt": "income_stmt",
            "balance_sheet": "balance_sheet",
            "cashflow": "cashflow",
            "quarterly_income_stmt": "quarterly_income_stmt",
            "quarterly_balance_sheet": "quarterly_balance_sheet",
            "quarterly_cashflow": "quarterly_cashflow",
        }
        financials = {}

        for result_key, attribute_name in statements.items():
            try:
                def fetch_statement(name=attribute_name):
                    YAHOO_RATE_LIMITER.wait(ticker, name)
                    return getattr(stock, name)

                financials[result_key] = with_retry(
                    fetch_statement, ticker=ticker
                )
            except Exception as e:
                logger.warning(
                    "%sの財務データ取得エラー ticker=%s: %s",
                    attribute_name,
                    ticker,
                    e,
                )
                financials[result_key] = pd.DataFrame()

        if has_required_financial_data(financials):
            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(financials, f)
            except Exception as e:
                logger.warning("財務データのキャッシュ保存失敗 ticker=%s: %s", ticker, e)
        else:
            logger.warning("年次損益計算書が空のためキャッシュしません ticker=%s", ticker)

        return financials

    def get_multiple_stocks_info(self, tickers: list, progress_callback=None) -> dict:
        """複数銘柄の情報を20回/分の制限内で逐次取得"""
        results = {}
        total = len(tickers)

        for i, ticker in enumerate(tickers, start=1):
            info = self.get_stock_info(ticker)
            if info:
                results[ticker] = info
            if progress_callback:
                progress_callback(i / total)

        return results

    def _is_cache_valid(self, cache_file: str, hours: int = CACHE_EXPIRY_INFO_HOURS) -> bool:
        """キャッシュが有効かどうかを確認"""
        if not os.path.exists(cache_file):
            return False

        file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
        expiry_time = datetime.now() - timedelta(hours=hours)

        return file_time > expiry_time

    def clear_cache(self, cache_type: str = "all") -> int:
        """
        キャッシュをクリア

        Args:
            cache_type: "all" | "info" | "financials" | "history" | "stock_list"

        Returns:
            削除したファイル数
        """
        import shutil

        prefix_map = {
            "info":       "info_",
            "financials": "financials_",
            "history":    "history_",
            "stock_list": "us_stocks_list",
        }

        if cache_type == "all":
            if os.path.exists(self.cache_dir):
                files = os.listdir(self.cache_dir)
                shutil.rmtree(self.cache_dir)
                os.makedirs(self.cache_dir)
                return len(files)
            return 0

        prefix = prefix_map.get(cache_type)
        if prefix is None:
            raise ValueError(f"不明なキャッシュ種別: {cache_type}")

        count = 0
        for fname in os.listdir(self.cache_dir):
            if fname.startswith(prefix):
                os.remove(os.path.join(self.cache_dir, fname))
                count += 1
        return count

    def get_cache_stats(self) -> dict:
        """キャッシュの統計情報を取得"""
        if not os.path.exists(self.cache_dir):
            return {"total": 0, "info": 0, "financials": 0, "history": 0, "stock_list": 0}

        stats = {"total": 0, "info": 0, "financials": 0, "history": 0, "stock_list": 0}
        for fname in os.listdir(self.cache_dir):
            stats["total"] += 1
            if fname.startswith("info_"):
                stats["info"] += 1
            elif fname.startswith("financials_"):
                stats["financials"] += 1
            elif fname.startswith("history_"):
                stats["history"] += 1
            elif fname.startswith("us_stocks_list"):
                stats["stock_list"] += 1
        return stats


if __name__ == "__main__":
    # テスト実行
    fetcher = DataFetcher()

    # 銘柄リストを取得
    print("銘柄リストを取得中...")
    stocks = fetcher.get_us_stock_list()
    print(f"取得銘柄数: {len(stocks)}")
    print(stocks.head())

    # AAPLの情報を取得
    print("\nAAPLの情報を取得中...")
    info = fetcher.get_stock_info("AAPL")
    if info:
        print(f"企業名: {info.get('longName')}")
        print(f"時価総額: {info.get('marketCap')}")
        print(f"PER: {info.get('trailingPE')}")
