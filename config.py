"""データ取得・分析で共通利用する設定ファイル。

値は環境変数で上書きできます。Yahoo Financeの既定値は、50銘柄の
実測確認で429が発生しなかった60回/分です。
"""

import os


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))

# キャッシュ設定
CACHE_DIR = os.getenv("CACHE_DIR", "data/cache")

# データ種別ごとのキャッシュ有効期間
CACHE_EXPIRY_STOCK_LIST_HOURS  = 24 * 7    # 銘柄リスト: 7日（上場廃止・新規上場は稀）
CACHE_EXPIRY_INFO_HOURS        = 24 * 7    # 銘柄基本情報（PER・時価総額等）: 7日
CACHE_EXPIRY_FINANCIALS_HOURS  = 24 * 90   # 財務データ（EPS・ROE等）: 90日（四半期更新）
CACHE_EXPIRY_HISTORY_HOURS     = 24        # 株価履歴: 24時間（平日毎日更新）

# データ取得設定
MAX_TICKERS_PER_BATCH = _env_int("MAX_TICKERS_PER_BATCH", 50)
YAHOO_MAX_REQUESTS_PER_MINUTE = _env_float("YAHOO_MAX_REQUESTS_PER_MINUTE", 60)
if YAHOO_MAX_REQUESTS_PER_MINUTE <= 0:
    raise ValueError("YAHOO_MAX_REQUESTS_PER_MINUTE は0より大きい値が必要です")

# 60回/分なら呼び出し開始間隔は最低1秒。REQUEST_DELAY_SECONDSを指定しても
# この下限より短くはしません。
MIN_REQUEST_INTERVAL_SECONDS = 60 / YAHOO_MAX_REQUESTS_PER_MINUTE
REQUEST_DELAY_SECONDS = max(
    _env_float("REQUEST_DELAY_SECONDS", MIN_REQUEST_INTERVAL_SECONDS),
    MIN_REQUEST_INTERVAL_SECONDS,
)
REQUEST_JITTER_SECONDS = max(_env_float("REQUEST_JITTER_SECONDS", 0), 0)

# レート制限リトライ設定
RETRY_MAX_ATTEMPTS = _env_int("RETRY_MAX_ATTEMPTS", 3)
RETRY_WAIT_SECONDS = _env_int("RETRY_WAIT_SECONDS", 60)
if RETRY_MAX_ATTEMPTS < 1:
    raise ValueError("RETRY_MAX_ATTEMPTS は1以上が必要です")
if RETRY_WAIT_SECONDS < 0:
    raise ValueError("RETRY_WAIT_SECONDS は0以上が必要です")

# テクニカル指標のデフォルト期間
SMA_PERIODS = [20, 50, 200]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2

# ファンダメンタル指標のデフォルト値
DEFAULT_MIN_MARKET_CAP = 1_000_000_000  # 10億ドル
DEFAULT_MAX_PER = 50
DEFAULT_MIN_ROE = 0
DEFAULT_MIN_DIVIDEND_YIELD = 0
