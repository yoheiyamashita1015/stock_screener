"""スクリーニングエンジン - ファンダメンタルとテクニカル分析を統合"""

import time
import threading
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

from .data_fetcher import DataFetcher
from .fundamental import FundamentalAnalyzer
from lambda_app.screen import ScreeningCriteria, check_range, matches_criteria, to_float
from .technical import TechnicalAnalyzer, get_trend_signal


class StockScreener:
    """株式スクリーニングクラス"""

    def __init__(self):
        self.data_fetcher = DataFetcher()
        self.fundamental_analyzer = FundamentalAnalyzer()

    def screen_stocks(
        self,
        tickers: list,
        criteria: ScreeningCriteria,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None,
        include_technicals: bool = True,
        max_workers: int = 5,
    ) -> pd.DataFrame:
        """
        銘柄をスクリーニング（並列処理）

        Args:
            tickers:           ティッカーリスト
            criteria:          スクリーニング条件
            progress_callback: (pct, msg) 進捗コールバック
            log_callback:      (msg) ログ出力コールバック
            cancel_event:      セットされたらスクリーニングを中断
            include_technicals: テクニカル指標を含めるか
            max_workers:       並列スレッド数

        Returns:
            pd.DataFrame: スクリーニング結果
        """
        def log(msg: str):
            print(msg)
            if log_callback:
                log_callback(msg)

        total = len(tickers)
        results = []
        completed = 0
        lock = threading.Lock()

        def analyze(ticker: str):
            try:
                data = self._analyze_stock(ticker, include_technicals)
                return ticker, data
            except Exception as e:
                log(f"[エラー] {ticker}: {e}")
                return ticker, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze, t): t for t in tickers}

            for future in as_completed(futures):
                # 中断チェック
                if cancel_event and cancel_event.is_set():
                    log("⏹ スクリーニングを中断しました")
                    for f in futures:
                        f.cancel()
                    break

                ticker, stock_data = future.result()

                with lock:
                    completed += 1
                    pct = completed / total
                    msg = f"分析中: {ticker} ({completed}/{total})"
                    if progress_callback:
                        progress_callback(pct, msg)

                if stock_data is not None and self._matches_criteria(stock_data, criteria, include_technicals):
                    with lock:
                        results.append(stock_data)
                    log(f"[通過] {ticker}")

        log(f"完了: {total}銘柄中 {len(results)}銘柄が条件を通過")

        if results:
            return pd.DataFrame(results)
        return pd.DataFrame()

    def _analyze_stock(self, ticker: str, include_technicals: bool = True) -> Optional[dict]:
        """個別銘柄を分析"""
        # 基本情報を取得
        info = self.data_fetcher.get_stock_info(ticker)
        if info is None:
            return None

        # ファンダメンタル分析
        financials = self.data_fetcher.get_financials(ticker)
        fundamentals = self.fundamental_analyzer.get_all_fundamentals(info, financials)

        result = fundamentals.copy()
        result["ticker"] = ticker

        # テクニカル分析
        if include_technicals:
            history = self.data_fetcher.get_stock_history(ticker, period="1y")
            if history is not None and not history.empty:
                try:
                    tech_analyzer = TechnicalAnalyzer(history)
                    technicals = tech_analyzer.get_all_technicals()
                    result.update(technicals)
                    result["trend_signal"] = get_trend_signal(technicals)
                except Exception as e:
                    print(f"{ticker}のテクニカル分析エラー: {e}")

        return result

    def _matches_criteria(self, stock_data: dict, criteria: ScreeningCriteria, include_technicals: bool = True) -> bool:
        """銘柄が条件に一致するかチェック"""
        return matches_criteria(stock_data, criteria, include_technicals)

    @staticmethod
    def _to_float(value) -> Optional[float]:
        """値をfloatに変換。文字列・変換不能な値はNoneを返す"""
        return to_float(value)

    def _check_range(self, value: Optional[float], min_val: Optional[float], max_val: Optional[float]) -> bool:
        """値が範囲内かチェック"""
        return check_range(value, min_val, max_val)

    def get_sample_tickers(self, count: int = 100) -> list:
        """ティッカーリストを取得"""
        stocks = self.data_fetcher.get_us_stock_list()
        if not stocks.empty and "symbol" in stocks.columns:
            tickers = stocks["symbol"].tolist()
            return tickers if count >= len(tickers) else tickers[:count]
        # フォールバック: S&P 500主要銘柄（NASDAQ/NYSE APIおよびWikipedia取得失敗時）
        return [
            # 情報技術
            "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "ADBE", "CRM", "AMD", "INTC", "QCOM",
            "TXN", "IBM", "AMAT", "MU", "KLAC", "LRCX", "SNPS", "CDNS", "ANSS", "FTNT",
            "PANW", "CRWD", "ZS", "OKTA", "DDOG", "NET", "SNOW", "PLTR", "UBER", "LYFT",
            # 通信
            "GOOGL", "GOOG", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR",
            # 一般消費財
            "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "BKNG", "TJX", "LOW", "ORLY",
            "AZO", "EBAY", "ETSY", "ROST", "YUM", "CMG", "DHI", "LEN", "PHM", "NVR",
            # 生活必需品
            "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "GIS",
            "K", "HSY", "MKC", "SJM", "CAG", "CPB", "HRL", "TSN", "WBA", "CVS",
            # ヘルスケア
            "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "AMGN",
            "GILD", "VRTX", "REGN", "BIIB", "ISRG", "BSX", "EW", "SYK", "MDT", "ZBH",
            # 金融
            "BRK-B", "JPM", "BAC", "WFC", "GS", "MS", "BLK", "C", "AXP", "SCHW",
            "CB", "AON", "MMC", "TRV", "PGR", "ALL", "MET", "PRU", "AFL", "AIG",
            # 資本財
            "HON", "UPS", "CAT", "DE", "LMT", "RTX", "GE", "BA", "NOC", "GD",
            "EMR", "ETN", "PH", "ROK", "CMI", "IR", "XYL", "VRSK", "FAST", "GWW",
            # エネルギー
            "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "PXD",
            "HAL", "DVN", "HES", "FANG", "APA", "MRO", "OKE", "WMB", "KMI", "LNG",
            # 素材
            "LIN", "APD", "ECL", "DD", "DOW", "PPG", "SHW", "NEM", "FCX", "NUE",
            "VMC", "MLM", "ALB", "CF", "MOS", "FMC", "IFF", "EMN", "CE", "RPM",
            # 公益事業
            "NEE", "DUK", "SO", "D", "AEP", "EXC", "XEL", "SRE", "PCG", "ED",
            "EIX", "ETR", "FE", "ES", "AWK", "CMS", "AES", "CNP", "NI", "PPL",
            # 不動産
            "PLD", "AMT", "EQIX", "CCI", "SPG", "O", "PSA", "EQR", "AVB", "DLR",
            "VICI", "WELL", "VTR", "ARE", "BXP", "KIM", "REG", "MAC", "WPC", "NNN",
            # その他大型株
            "V", "MA", "PYPL", "ACN", "FIS", "FI", "GPN", "WEX", "JKHY", "SSNC",
        ][:count]


def create_default_criteria() -> ScreeningCriteria:
    """デフォルトのスクリーニング条件を作成"""
    return ScreeningCriteria(
        min_market_cap=1_000_000_000,  # 10億ドル以上
        max_per=50,  # PER50以下
        min_roe=10,  # ROE10%以上
    )


if __name__ == "__main__":
    # テスト実行
    screener = StockScreener()

    # サンプルティッカーを取得
    tickers = screener.get_sample_tickers(10)
    print(f"テスト銘柄: {tickers}")

    # デフォルト条件でスクリーニング
    criteria = create_default_criteria()

    def progress(pct, msg):
        print(f"{pct*100:.0f}% - {msg}")

    results = screener.screen_stocks(tickers, criteria, progress_callback=progress)

    print(f"\n結果: {len(results)}銘柄")
    if not results.empty:
        print(results[["ticker", "name", "per", "roe", "market_cap"]].to_string())
