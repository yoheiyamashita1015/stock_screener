"""ファンダメンタル分析モジュール"""

from typing import Optional
import pandas as pd
import numpy as np


class FundamentalAnalyzer:
    """ファンダメンタル指標を計算するクラス"""

    @staticmethod
    def calculate_per(info: dict) -> Optional[float]:
        """PER（株価収益率）を取得"""
        return info.get("trailingPE") or info.get("forwardPE")

    @staticmethod
    def calculate_pbr(info: dict) -> Optional[float]:
        """PBR（株価純資産倍率）を取得"""
        return info.get("priceToBook")

    @staticmethod
    def calculate_dividend_yield(info: dict) -> Optional[float]:
        """配当利回りを百分率で取得する。

        ``trailingAnnualDividendYield`` は割合（例: 0.0034 = 0.34%）、
        現行yfinanceの ``dividendYield`` は百分率（例: 0.34 = 0.34%）で
        返るため、同じ変換を適用しない。
        """
        trailing_yield = info.get("trailingAnnualDividendYield")
        if trailing_yield is not None:
            return trailing_yield * 100

        dividend_yield = info.get("dividendYield")
        return dividend_yield if dividend_yield is not None else 0

    @staticmethod
    def calculate_market_cap(info: dict) -> Optional[float]:
        """時価総額を取得（ドル）"""
        return info.get("marketCap")

    @staticmethod
    def calculate_roe(info: dict) -> Optional[float]:
        """ROE（自己資本利益率）を取得（%）"""
        roe = info.get("returnOnEquity")
        if roe:
            return roe * 100
        return None

    @staticmethod
    def calculate_roa(info: dict) -> Optional[float]:
        """ROA（総資産利益率）を取得（%）"""
        roa = info.get("returnOnAssets")
        if roa:
            return roa * 100
        return None

    @staticmethod
    def calculate_revenue_growth(info: dict) -> Optional[float]:
        """売上高成長率を取得（%）"""
        growth = info.get("revenueGrowth")
        if growth:
            return growth * 100
        return None

    @staticmethod
    def calculate_eps_growth(financials: dict) -> dict:
        """
        EPS成長率を計算

        Returns:
            dict: {
                "eps_growth_rate": 年率成長率（%）,
                "consecutive_years": 連続増加年数,
                "eps_history": 過去のEPSリスト
            }
        """
        result = {
            "eps_growth_rate": None,
            "consecutive_years": 0,
            "eps_history": []
        }

        try:
            income_stmt = financials.get("income_stmt")
            if income_stmt is None or income_stmt.empty:
                return result

            # Basic EPSを取得
            if "Basic EPS" in income_stmt.index:
                eps_series = income_stmt.loc["Basic EPS"].dropna().sort_index()
            elif "Diluted EPS" in income_stmt.index:
                eps_series = income_stmt.loc["Diluted EPS"].dropna().sort_index()
            else:
                return result

            if len(eps_series) < 2:
                return result

            result["eps_history"] = eps_series.tolist()

            # 年率成長率を計算（CAGR）
            years = len(eps_series) - 1
            first_eps = float(eps_series.iloc[0])
            last_eps = float(eps_series.iloc[-1])
            if (
                years > 0
                and np.isfinite(first_eps)
                and np.isfinite(last_eps)
                and first_eps > 0
                and last_eps > 0
            ):
                cagr = ((last_eps / first_eps) ** (1 / years) - 1) * 100
                result["eps_growth_rate"] = cagr

            # 連続増加年数を計算
            consecutive = 0
            for i in range(len(eps_series) - 1, 0, -1):
                if eps_series.iloc[i] > eps_series.iloc[i - 1]:
                    consecutive += 1
                else:
                    break
            result["consecutive_years"] = consecutive

        except Exception as e:
            print(f"EPS成長率計算エラー: {e}")

        return result

    @staticmethod
    def calculate_insider_hold(info: dict) -> Optional[float]:
        """インサイダー保有比率を取得（%）"""
        insider_hold = info.get("heldPercentInsiders")
        if insider_hold:
            return insider_hold * 100
        return None

    @staticmethod
    def calculate_fcf_yield(info: dict, financials: dict) -> Optional[float]:
        """
        FCF利回り（フリーキャッシュフロー利回り）を計算（%）

        FCF Yield = Free Cash Flow / Market Cap * 100
        """
        try:
            market_cap = info.get("marketCap")
            if not market_cap or market_cap <= 0:
                return None

            # キャッシュフロー計算書からFCFを取得
            cashflow = financials.get("cashflow")
            if cashflow is None or cashflow.empty:
                # infoから直接取得を試みる
                fcf = info.get("freeCashflow")
                if fcf:
                    return (fcf / market_cap) * 100
                return None

            # Operating Cash FlowとCapital Expendituresを取得
            ocf = None
            capex = None

            if "Operating Cash Flow" in cashflow.index:
                ocf = cashflow.loc["Operating Cash Flow"].iloc[0]
            elif "Total Cash From Operating Activities" in cashflow.index:
                ocf = cashflow.loc["Total Cash From Operating Activities"].iloc[0]

            if "Capital Expenditure" in cashflow.index:
                capex = cashflow.loc["Capital Expenditure"].iloc[0]
            elif "Capital Expenditures" in cashflow.index:
                capex = cashflow.loc["Capital Expenditures"].iloc[0]

            if ocf is not None and capex is not None:
                fcf = ocf + capex  # capexは通常マイナス値
                return (fcf / market_cap) * 100

            # 直接FCFが取得できる場合
            if "Free Cash Flow" in cashflow.index:
                fcf = cashflow.loc["Free Cash Flow"].iloc[0]
                return (fcf / market_cap) * 100

        except Exception as e:
            print(f"FCF利回り計算エラー: {e}")

        return None

    @staticmethod
    def calculate_peg_ratio(info: dict) -> Optional[float]:
        """PEGレシオを取得"""
        return info.get("pegRatio")

    @staticmethod
    def calculate_debt_to_equity(info: dict) -> Optional[float]:
        """負債資本比率を取得"""
        return info.get("debtToEquity")

    @staticmethod
    def calculate_current_ratio(info: dict) -> Optional[float]:
        """流動比率を取得"""
        return info.get("currentRatio")

    @staticmethod
    def calculate_quick_ratio(info: dict) -> Optional[float]:
        """当座比率を取得"""
        return info.get("quickRatio")

    def get_all_fundamentals(self, info: dict, financials: dict = None) -> dict:
        """
        全てのファンダメンタル指標を取得

        Args:
            info: yfinanceのinfoデータ
            financials: yfinanceの財務データ（オプション）

        Returns:
            dict: 全ファンダメンタル指標
        """
        if financials is None:
            financials = {}

        eps_data = self.calculate_eps_growth(financials)

        return {
            "ticker": info.get("symbol", ""),
            "name": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "per": self.calculate_per(info),
            "pbr": self.calculate_pbr(info),
            "dividend_yield": self.calculate_dividend_yield(info),
            "market_cap": self.calculate_market_cap(info),
            "roe": self.calculate_roe(info),
            "roa": self.calculate_roa(info),
            "revenue_growth": self.calculate_revenue_growth(info),
            "eps_growth_rate": eps_data["eps_growth_rate"],
            "eps_consecutive_years": eps_data["consecutive_years"],
            "insider_hold": self.calculate_insider_hold(info),
            "fcf_yield": self.calculate_fcf_yield(info, financials),
            "peg_ratio": self.calculate_peg_ratio(info),
            "debt_to_equity": self.calculate_debt_to_equity(info),
            "current_ratio": self.calculate_current_ratio(info),
            "quick_ratio": self.calculate_quick_ratio(info),
        }


def format_market_cap(value: float) -> str:
    """時価総額を読みやすい形式にフォーマット"""
    if value is None:
        return "N/A"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    elif value >= 1e9:
        return f"${value / 1e9:.2f}B"
    elif value >= 1e6:
        return f"${value / 1e6:.2f}M"
    else:
        return f"${value:,.0f}"


if __name__ == "__main__":
    # テスト実行
    from data_fetcher import DataFetcher

    fetcher = DataFetcher()
    analyzer = FundamentalAnalyzer()

    # AAPLのデータを取得
    info = fetcher.get_stock_info("AAPL")
    financials = fetcher.get_financials("AAPL")

    if info:
        fundamentals = analyzer.get_all_fundamentals(info, financials)
        print("\nAAPLのファンダメンタル指標:")
        for key, value in fundamentals.items():
            if key == "market_cap":
                print(f"  {key}: {format_market_cap(value)}")
            elif isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
