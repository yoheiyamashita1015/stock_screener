"""バックテストエンジン - スクリーニング条件の過去検証"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, Callable

import numpy as np
import pandas as pd
import yfinance as yf

from .data_fetcher import DataFetcher
from .screener import ScreeningCriteria, StockScreener
from .technical import TechnicalAnalyzer, get_trend_signal


class BacktestEngine:
    """スクリーニング条件のバックテスト"""

    def __init__(self):
        self.data_fetcher = DataFetcher()
        self._screener = StockScreener()

    def run(
        self,
        tickers: list,
        criteria: ScreeningCriteria,
        start_date: datetime,
        end_date: datetime,
        progress_callback: Optional[Callable] = None,
        max_workers: int = 5,
    ) -> dict:
        """
        バックテスト実行

        Args:
            tickers:           対象ティッカーリスト
            criteria:          スクリーニング条件
            start_date:        スクリーニング基準日（この日に条件を適用）
            end_date:          リターン計算終了日
            progress_callback: (pct, msg) -> None
            max_workers:       並列スレッド数

        Returns:
            {
                "selected":          pd.DataFrame  # 条件通過銘柄
                "all_results":       pd.DataFrame  # 全銘柄のリターン（比較用）
                "portfolio_return":  float         # 等重ポートフォリオリターン(%)
                "benchmark_return":  float         # SPY リターン(%)
                "start_date":        datetime
                "end_date":          datetime
                "screened_count":    int           # 条件通過銘柄数
                "total_count":       int           # 分析銘柄数
            }
        """
        total = len(tickers)
        selected = []
        all_results = []
        completed = 0
        lock = threading.Lock()

        # ベンチマーク(SPY = S&P500 ETF)のリターンを先に取得
        benchmark_return = self._get_price_return("SPY", start_date, end_date)

        def analyze(ticker: str):
            try:
                return self._analyze_ticker(ticker, criteria, start_date, end_date)
            except Exception as e:
                print(f"{ticker} バックテストエラー: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze, t): t for t in tickers}

            for future in as_completed(futures):
                ticker = futures[future]
                result = future.result()

                with lock:
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            completed / total,
                            f"検証中: {ticker} ({completed}/{total})"
                        )

                if result is not None:
                    with lock:
                        all_results.append(result)
                        if result.get("passed_criteria"):
                            selected.append(result)

        selected_df = pd.DataFrame(selected) if selected else pd.DataFrame()
        all_df = pd.DataFrame(all_results) if all_results else pd.DataFrame()

        portfolio_return = selected_df["return_pct"].mean() if not selected_df.empty else None

        return {
            "selected": selected_df,
            "all_results": all_df,
            "portfolio_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "start_date": start_date,
            "end_date": end_date,
            "screened_count": len(selected),
            "total_count": len(all_results),
        }

    # ------------------------------------------------------------------
    # 内部メソッド
    # ------------------------------------------------------------------

    def _analyze_ticker(
        self,
        ticker: str,
        criteria: ScreeningCriteria,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[dict]:
        """1銘柄を分析してスクリーニング判定とリターンを返す"""

        # start_date の1年前から end_date まで価格データを取得
        extended_start = start_date - timedelta(days=380)
        history = self._fetch_history(ticker, extended_start, end_date)
        if history is None or len(history) < 20:
            return None

        # start_date 時点までのデータ（スクリーニング判定に使用）
        hist_at_start = history[history.index.tz_localize(None) <= pd.Timestamp(start_date)]
        if len(hist_at_start) < 20:
            return None

        # start_date 時点の株価
        start_price = float(hist_at_start["Close"].iloc[-1])

        # 財務データ・銘柄情報を取得
        info = self.data_fetcher.get_stock_info(ticker)
        financials = self.data_fetcher.get_financials(ticker)
        if info is None:
            return None

        # start_date 時点のファンダメンタル指標を再構築
        fund_data = self._build_historical_fundamentals(
            ticker, info, financials, hist_at_start, start_date, start_price
        )

        # テクニカル指標を計算（start_date 時点）
        try:
            tech = TechnicalAnalyzer(hist_at_start)
            tech_data = tech.get_all_technicals()
            tech_data["trend_signal"] = get_trend_signal(tech_data)
            fund_data.update(tech_data)
        except Exception:
            pass

        fund_data["ticker"] = ticker

        # スクリーニング条件を適用
        passed = self._screener._matches_criteria(fund_data, criteria)
        fund_data["passed_criteria"] = passed

        # リターンを計算
        ret = self._get_return_from_history(history, start_date, end_date)
        fund_data["return_pct"] = ret

        return fund_data

    def _build_historical_fundamentals(
        self,
        ticker: str,
        info: dict,
        financials: dict,
        hist_at_start: pd.DataFrame,
        as_of_date: datetime,
        start_price: float,
    ) -> dict:
        """as_of_date 時点のファンダメンタル指標を財務諸表から近似再構築"""

        result = {
            "name":    info.get("longName") or info.get("shortName", ticker),
            "sector":  info.get("sector", ""),
            "current_price": start_price,
        }

        as_of_ts = pd.Timestamp(as_of_date)
        shares = info.get("sharesOutstanding")

        # 時価総額（株価 × 発行済株式数）
        result["market_cap"] = start_price * shares if shares else None

        income_stmt  = financials.get("income_stmt")
        balance_sheet = financials.get("balance_sheet")
        cashflow     = financials.get("cashflow")

        def latest_before(df: pd.DataFrame, row: str) -> Optional[float]:
            """as_of_date 以前の最新の財務値を取得（先見バイアスを防ぐ）"""
            if df is None or df.empty or row not in df.index:
                return None
            cols = [c for c in df.columns if pd.Timestamp(c) <= as_of_ts]
            if not cols:
                return None
            return df.loc[row, max(cols)]

        # PER: start_price / EPS
        for eps_key in ("Diluted EPS", "Basic EPS"):
            eps = latest_before(income_stmt, eps_key)
            if eps and eps > 0:
                result["per"] = round(start_price / eps, 2)
                break
        else:
            result["per"] = None

        # PBR: start_price / BVPS
        equity = latest_before(balance_sheet, "Stockholders Equity")
        if equity and shares and shares > 0:
            bvps = equity / shares
            result["pbr"] = round(start_price / bvps, 2) if bvps > 0 else None
        else:
            result["pbr"] = None

        # ROE
        net_income = latest_before(income_stmt, "Net Income")
        if net_income and equity and equity > 0:
            result["roe"] = round((net_income / equity) * 100, 2)
        else:
            result["roe"] = None

        # ROA
        total_assets = latest_before(balance_sheet, "Total Assets")
        if net_income and total_assets and total_assets > 0:
            result["roa"] = round((net_income / total_assets) * 100, 2)
        else:
            result["roa"] = None

        # 売上高成長率（直近2期比較）
        result["revenue_growth"] = self._calc_growth_rate(income_stmt, "Total Revenue", as_of_ts)

        # EPS成長率
        result["eps_growth_rate"] = self._calc_growth_rate(income_stmt, "Diluted EPS", as_of_ts) \
                                 or self._calc_growth_rate(income_stmt, "Basic EPS", as_of_ts)
        result["eps_consecutive_years"] = 0  # 過去データからの完全再現は困難

        # FCF利回り
        ocf   = latest_before(cashflow, "Operating Cash Flow")
        capex = latest_before(cashflow, "Capital Expenditure")
        mktcap = result.get("market_cap")
        if ocf and capex and mktcap and mktcap > 0:
            fcf = ocf + capex  # capex は通常マイナス
            result["fcf_yield"] = round((fcf / mktcap) * 100, 2)
        else:
            result["fcf_yield"] = None

        # 配当利回り・インサイダー保有率は過去値が取得困難なため現在値で代用
        div_yield = info.get("dividendYield")
        result["dividend_yield"] = round(div_yield * 100, 2) if div_yield else None
        insider = info.get("heldPercentInsiders")
        result["insider_hold"] = round(insider * 100, 2) if insider else None

        return result

    def _calc_growth_rate(
        self, df: Optional[pd.DataFrame], row: str, as_of_ts: pd.Timestamp
    ) -> Optional[float]:
        """直近2期の成長率(%)を計算"""
        if df is None or df.empty or row not in df.index:
            return None
        cols = sorted([c for c in df.columns if pd.Timestamp(c) <= as_of_ts], reverse=True)
        if len(cols) < 2:
            return None
        v_new = df.loc[row, cols[0]]
        v_old = df.loc[row, cols[1]]
        if v_old and v_old != 0:
            return round(((v_new - v_old) / abs(v_old)) * 100, 2)
        return None

    def _fetch_history(
        self, ticker: str, start: datetime, end: datetime
    ) -> Optional[pd.DataFrame]:
        """yfinance から指定期間の価格データを取得"""
        try:
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + timedelta(days=5)).strftime("%Y-%m-%d"),
            )
            return hist if not hist.empty else None
        except Exception:
            return None

    def _get_price_return(
        self, ticker: str, start: datetime, end: datetime
    ) -> Optional[float]:
        """指定期間の価格リターン(%)を計算"""
        hist = self._fetch_history(ticker, start - timedelta(days=5), end)
        return self._get_return_from_history(hist, start, end) if hist is not None else None

    def _get_return_from_history(
        self, history: pd.DataFrame, start: datetime, end: datetime
    ) -> Optional[float]:
        """履歴DataFrameから start→end のリターン(%)を計算"""
        try:
            idx = history.index.tz_localize(None)
            start_ts = pd.Timestamp(start)
            end_ts   = pd.Timestamp(end)

            after_start  = history[idx >= start_ts]
            before_end   = history[idx <= end_ts]

            if after_start.empty or before_end.empty:
                return None

            p_start = float(after_start["Close"].iloc[0])
            p_end   = float(before_end["Close"].iloc[-1])
            return round((p_end / p_start - 1) * 100, 2)
        except Exception:
            return None


def build_equity_curve(
    selected_df: pd.DataFrame,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame:
    """
    選択銘柄の等重ポートフォリオとSPY(ベンチマーク)の日次累積リターン曲線を生成

    Returns:
        pd.DataFrame: index=日付, columns=["portfolio", "benchmark"]
    """
    if selected_df.empty:
        return pd.DataFrame()

    tickers = selected_df["ticker"].tolist() + ["SPY"]
    extended_start = start_date - timedelta(days=5)

    try:
        raw = yf.download(
            tickers,
            start=extended_start.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=5)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
    except Exception:
        return pd.DataFrame()

    # Close 価格だけ取り出す
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})

    # start_date 以降に絞る
    idx = close.index.tz_localize(None) if close.index.tz else close.index
    close.index = idx
    close = close[close.index >= pd.Timestamp(start_date)]

    if close.empty:
        return pd.DataFrame()

    # 日次リターン → 累積リターン(%)
    returns = close.pct_change().fillna(0)
    cum = (1 + returns).cumprod() - 1

    portfolio_cols = [c for c in cum.columns if c != "SPY"]
    if not portfolio_cols:
        return pd.DataFrame()

    result = pd.DataFrame(index=cum.index)
    result["portfolio"]  = cum[portfolio_cols].mean(axis=1) * 100
    result["benchmark"]  = cum["SPY"] * 100 if "SPY" in cum.columns else None

    return result
