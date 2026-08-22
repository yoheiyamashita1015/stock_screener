"""テクニカル分析モジュール"""

from typing import Optional
import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    print("pandas-taがインストールされていません。基本的なテクニカル指標のみ使用可能です。")

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SMA_PERIODS, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, BB_STD


class TechnicalAnalyzer:
    """テクニカル指標を計算するクラス"""

    def __init__(self, history: pd.DataFrame):
        """
        Args:
            history: 株価履歴データ（yfinanceから取得したDataFrame）
                    必須カラム: Open, High, Low, Close, Volume
        """
        self.history = history
        self._validate_data()

    def _validate_data(self):
        """データの検証"""
        required_columns = ["Open", "High", "Low", "Close", "Volume"]
        for col in required_columns:
            if col not in self.history.columns:
                raise ValueError(f"必須カラム {col} がありません")

    def calculate_sma(self, periods: list = None) -> dict:
        """
        単純移動平均線（SMA）を計算

        Args:
            periods: 計算する期間のリスト（デフォルト: [20, 50, 200]）

        Returns:
            dict: {period: 最新のSMA値}
        """
        if periods is None:
            periods = SMA_PERIODS

        result = {}
        close = self.history["Close"]

        for period in periods:
            if len(close) >= period:
                sma = close.rolling(window=period).mean()
                result[f"sma_{period}"] = sma.iloc[-1]
            else:
                result[f"sma_{period}"] = None

        return result

    def calculate_ema(self, periods: list = None) -> dict:
        """
        指数移動平均線（EMA）を計算

        Args:
            periods: 計算する期間のリスト

        Returns:
            dict: {period: 最新のEMA値}
        """
        if periods is None:
            periods = [12, 26]

        result = {}
        close = self.history["Close"]

        for period in periods:
            if len(close) >= period:
                ema = close.ewm(span=period, adjust=False).mean()
                result[f"ema_{period}"] = ema.iloc[-1]
            else:
                result[f"ema_{period}"] = None

        return result

    def calculate_rsi(self, period: int = None) -> Optional[float]:
        """
        RSI（相対力指数）を計算

        Args:
            period: 計算期間（デフォルト: 14）

        Returns:
            float: 最新のRSI値（0-100）
        """
        if period is None:
            period = RSI_PERIOD

        close = self.history["Close"]

        if len(close) < period + 1:
            return None

        # 価格変動を計算
        delta = close.diff()

        # 上昇と下落を分離
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        # 平均を計算
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # RSを計算
        rs = avg_gain / avg_loss

        # RSIを計算
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1]

    def calculate_macd(self, fast: int = None, slow: int = None, signal: int = None) -> dict:
        """
        MACDを計算

        Args:
            fast: 短期EMA期間（デフォルト: 12）
            slow: 長期EMA期間（デフォルト: 26）
            signal: シグナル線期間（デフォルト: 9）

        Returns:
            dict: {macd: MACD値, signal: シグナル値, histogram: ヒストグラム}
        """
        if fast is None:
            fast = MACD_FAST
        if slow is None:
            slow = MACD_SLOW
        if signal is None:
            signal = MACD_SIGNAL

        close = self.history["Close"]

        if len(close) < slow:
            return {"macd": None, "signal": None, "histogram": None}

        # EMAを計算
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        # MACDラインを計算
        macd_line = ema_fast - ema_slow

        # シグナルラインを計算
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        # ヒストグラムを計算
        histogram = macd_line - signal_line

        return {
            "macd": macd_line.iloc[-1],
            "signal": signal_line.iloc[-1],
            "histogram": histogram.iloc[-1]
        }

    def calculate_bollinger_bands(self, period: int = None, std_dev: int = None) -> dict:
        """
        ボリンジャーバンドを計算

        Args:
            period: 計算期間（デフォルト: 20）
            std_dev: 標準偏差の倍数（デフォルト: 2）

        Returns:
            dict: {upper: 上バンド, middle: 中央線, lower: 下バンド, percent_b: %B}
        """
        if period is None:
            period = BB_PERIOD
        if std_dev is None:
            std_dev = BB_STD

        close = self.history["Close"]

        if len(close) < period:
            return {"upper": None, "middle": None, "lower": None, "percent_b": None}

        # 中央線（SMA）
        middle = close.rolling(window=period).mean()

        # 標準偏差
        std = close.rolling(window=period).std()

        # 上下バンド
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        # %B（現在価格のバンド内での位置）
        current_price = close.iloc[-1]
        percent_b = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) * 100

        return {
            "upper": upper.iloc[-1],
            "middle": middle.iloc[-1],
            "lower": lower.iloc[-1],
            "percent_b": percent_b
        }

    def calculate_52week_position(self) -> dict:
        """
        52週高値/安値からの乖離率を計算

        Returns:
            dict: {
                high_52w: 52週高値,
                low_52w: 52週安値,
                pct_from_high: 高値からの乖離率（%、マイナス値）,
                pct_from_low: 安値からの乖離率（%、プラス値）
            }
        """
        close = self.history["Close"]
        high = self.history["High"]
        low = self.history["Low"]

        # 52週 = 約252営業日
        lookback = min(252, len(close))

        if lookback < 20:  # 最低20日分のデータが必要
            return {
                "high_52w": None,
                "low_52w": None,
                "pct_from_high": None,
                "pct_from_low": None
            }

        high_52w = high.tail(lookback).max()
        low_52w = low.tail(lookback).min()
        current_price = close.iloc[-1]

        pct_from_high = ((current_price - high_52w) / high_52w) * 100
        pct_from_low = ((current_price - low_52w) / low_52w) * 100

        return {
            "high_52w": high_52w,
            "low_52w": low_52w,
            "pct_from_high": pct_from_high,
            "pct_from_low": pct_from_low
        }

    def calculate_volume_analysis(self) -> dict:
        """
        出来高分析

        Returns:
            dict: {
                avg_volume_20: 20日平均出来高,
                volume_ratio: 現在出来高/平均出来高
            }
        """
        volume = self.history["Volume"]

        if len(volume) < 20:
            return {"avg_volume_20": None, "volume_ratio": None}

        avg_volume = volume.tail(20).mean()
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else None

        return {
            "avg_volume_20": avg_volume,
            "volume_ratio": volume_ratio
        }

    def calculate_price_momentum(self) -> dict:
        """
        価格モメンタムを計算

        Returns:
            dict: {
                return_1d: 1日リターン（%）,
                return_5d: 5日リターン（%）,
                return_20d: 20日リターン（%）,
                return_60d: 60日リターン（%）
            }
        """
        close = self.history["Close"]

        result = {}
        periods = {"1d": 1, "5d": 5, "20d": 20, "60d": 60}

        for name, period in periods.items():
            if len(close) > period:
                ret = ((close.iloc[-1] / close.iloc[-period - 1]) - 1) * 100
                result[f"return_{name}"] = ret
            else:
                result[f"return_{name}"] = None

        return result

    def get_all_technicals(self) -> dict:
        """
        全てのテクニカル指標を取得

        Returns:
            dict: 全テクニカル指標
        """
        result = {
            "current_price": self.history["Close"].iloc[-1]
        }

        # SMA
        sma = self.calculate_sma()
        result.update(sma)

        # RSI
        result["rsi"] = self.calculate_rsi()

        # MACD
        macd = self.calculate_macd()
        result["macd"] = macd["macd"]
        result["macd_signal"] = macd["signal"]
        result["macd_histogram"] = macd["histogram"]

        # ボリンジャーバンド
        bb = self.calculate_bollinger_bands()
        result["bb_upper"] = bb["upper"]
        result["bb_middle"] = bb["middle"]
        result["bb_lower"] = bb["lower"]
        result["bb_percent_b"] = bb["percent_b"]

        # 52週ポジション
        week52 = self.calculate_52week_position()
        result.update(week52)

        # 出来高分析
        volume = self.calculate_volume_analysis()
        result.update(volume)

        # 価格モメンタム
        momentum = self.calculate_price_momentum()
        result.update(momentum)

        # SMAとの乖離率を追加
        current_price = result["current_price"]
        for period in SMA_PERIODS:
            sma_val = result.get(f"sma_{period}")
            if sma_val and sma_val > 0:
                result[f"pct_from_sma_{period}"] = ((current_price - sma_val) / sma_val) * 100
            else:
                result[f"pct_from_sma_{period}"] = None

        return result


def get_trend_signal(technicals: dict) -> str:
    """
    テクニカル指標からトレンドシグナルを判定

    Returns:
        str: "STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"
    """
    score = 0

    # RSIシグナル
    rsi = technicals.get("rsi")
    if rsi is not None:
        if rsi < 30:
            score += 2  # 売られすぎ → 買いシグナル
        elif rsi < 40:
            score += 1
        elif rsi > 70:
            score -= 2  # 買われすぎ → 売りシグナル
        elif rsi > 60:
            score -= 1

    # MACDシグナル
    macd_hist = technicals.get("macd_histogram")
    if macd_hist is not None:
        if macd_hist > 0:
            score += 1
        else:
            score -= 1

    # SMAシグナル（価格がSMAより上なら上昇トレンド）
    for period in [20, 50, 200]:
        pct_from_sma = technicals.get(f"pct_from_sma_{period}")
        if pct_from_sma is not None:
            if pct_from_sma > 5:
                score += 1
            elif pct_from_sma < -5:
                score -= 1

    # 52週高値/安値シグナル
    pct_from_high = technicals.get("pct_from_high")
    if pct_from_high is not None:
        if pct_from_high > -5:  # 高値に近い
            score += 1
        elif pct_from_high < -20:  # 高値から大きく下落
            score -= 1

    # シグナルを決定
    if score >= 4:
        return "STRONG_BUY"
    elif score >= 2:
        return "BUY"
    elif score <= -4:
        return "STRONG_SELL"
    elif score <= -2:
        return "SELL"
    else:
        return "NEUTRAL"


if __name__ == "__main__":
    # テスト実行
    from data_fetcher import DataFetcher

    fetcher = DataFetcher()

    # AAPLの履歴を取得
    history = fetcher.get_stock_history("AAPL", period="1y")

    if history is not None and not history.empty:
        analyzer = TechnicalAnalyzer(history)
        technicals = analyzer.get_all_technicals()

        print("\nAAPLのテクニカル指標:")
        for key, value in technicals.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

        signal = get_trend_signal(technicals)
        print(f"\nトレンドシグナル: {signal}")
