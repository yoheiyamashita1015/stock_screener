"""米国株スクリーニングシステム - Streamlit UI"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import json
import threading
from datetime import datetime, timedelta

# パスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# プリセット保存先ディレクトリ
PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "presets")
os.makedirs(PRESET_DIR, exist_ok=True)

# 保存対象のセッションキーとデフォルト値
PRESET_KEYS = {
    "min_market_cap": 10.0,
    "max_market_cap": 0.0,
    "min_per": 0.0,
    "max_per": 50.0,
    "min_div": 0.0,
    "max_div": 0.0,
    "min_roe": 0.0,
    "min_roa": 0.0,
    "min_revenue_growth": 0.0,
    "eps_mode": "年率成長率",
    "min_eps_growth": 0.0,
    "min_eps_consecutive": 0,
    "min_insider": 0.0,
    "max_insider": 0.0,
    "min_fcf_yield": 0.0,
    "min_rsi": 0.0,
    "max_rsi": 100.0,
    "above_sma_20": False,
    "above_sma_50": False,
    "above_sma_200": False,
    "min_from_high": -100.0,
    "max_from_high": 0.0,
    "trend_signals": [],
}


def get_preset_list() -> list[str]:
    """保存済みプリセット名一覧を取得"""
    files = [f[:-5] for f in os.listdir(PRESET_DIR) if f.endswith(".json")]
    return sorted(files)


def save_preset(name: str):
    """現在のセッション状態をプリセットとして保存"""
    preset = {key: st.session_state.get(key, default) for key, default in PRESET_KEYS.items()}
    path = os.path.join(PRESET_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(preset, f, ensure_ascii=False, indent=2)


def load_preset(name: str):
    """プリセットをセッション状態に読み込む"""
    path = os.path.join(PRESET_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        preset = json.load(f)
    for key, value in preset.items():
        st.session_state[key] = value


def delete_preset(name: str):
    """プリセットを削除"""
    path = os.path.join(PRESET_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)

from src.data_fetcher import DataFetcher
from src.fundamental import FundamentalAnalyzer, format_market_cap
from src.technical import TechnicalAnalyzer, get_trend_signal
from src.screener import StockScreener, ScreeningCriteria
from src.backtest import BacktestEngine, build_equity_curve

# ページ設定
st.set_page_config(
    page_title="米国株スクリーナー",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    .positive {
        color: #00c853;
    }
    .negative {
        color: #ff1744;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """セッション状態を初期化"""
    if "screener" not in st.session_state:
        st.session_state.screener = StockScreener()
    if "results" not in st.session_state:
        st.session_state.results = pd.DataFrame()
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None
    # スクリーニング条件のデフォルト値を初期化（未設定のキーのみ）
    for key, default in PRESET_KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = default
    # スクリーニング実行状態（スレッドと共有するためst.session_stateを経由しないdictで管理）
    if "sc" not in st.session_state:
        st.session_state.sc = {
            "running":  False,
            "cancel":   threading.Event(),
            "logs":     [],
            "results":  pd.DataFrame(),
            "progress": 0.0,
        }


def render_preset_section():
    """プリセット保存・読み込みセクション"""
    st.sidebar.header("💾 プリセット")

    presets = get_preset_list()

    # 読み込み・削除
    if presets:
        selected_preset = st.sidebar.selectbox("保存済みプリセット", presets, key="preset_select")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("読み込む", key="load_preset"):
                load_preset(selected_preset)
                st.rerun()
        with col2:
            if st.button("削除", key="delete_preset"):
                delete_preset(selected_preset)
                st.rerun()
    else:
        st.sidebar.caption("保存済みプリセットはありません")

    # 保存
    preset_name = st.sidebar.text_input("プリセット名", key="preset_name_input", placeholder="例: 成長株")
    if st.sidebar.button("現在の条件を保存", key="save_preset"):
        name = preset_name.strip()
        if name:
            save_preset(name)
            st.sidebar.success(f"「{name}」を保存しました")
            st.rerun()
        else:
            st.sidebar.error("プリセット名を入力してください")

    st.sidebar.divider()


def render_cache_section():
    """キャッシュ管理セクション"""
    with st.sidebar.expander("🗂️ キャッシュ管理"):
        fetcher = DataFetcher()
        stats = fetcher.get_cache_stats()

        st.caption(f"合計: {stats['total']}件")
        st.caption(f"銘柄情報: {stats['info']}件 / 財務: {stats['financials']}件 / 株価履歴: {stats['history']}件 / 銘柄リスト: {stats['stock_list']}件")

        cache_type = st.selectbox(
            "クリア対象",
            ["all", "info", "financials", "history", "stock_list"],
            format_func=lambda x: {
                "all":        "すべて",
                "info":       "銘柄情報（PER・時価総額等）",
                "financials": "財務データ（EPS・ROE等）",
                "history":    "株価履歴",
                "stock_list": "銘柄リスト",
            }[x],
            key="cache_type_select"
        )

        if st.button("キャッシュをクリア", key="clear_cache"):
            count = fetcher.clear_cache(cache_type)
            st.success(f"{count}件のキャッシュを削除しました")
            st.rerun()


def render_sidebar():
    """サイドバーのレンダリング"""
    st.sidebar.title("スクリーニング条件")

    render_preset_section()
    render_cache_section()

    # 条件のリセットボタン
    if st.sidebar.button("条件をリセット"):
        for key in PRESET_KEYS:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # ファンダメンタル条件
    st.sidebar.header("📊 ファンダメンタル")

    # 時価総額
    st.sidebar.subheader("時価総額")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_market_cap = st.number_input(
            "最小（億ドル）",
            min_value=0.0,
            step=1.0,
            key="min_market_cap"
        )
    with col2:
        max_market_cap = st.number_input(
            "最大（億ドル）",
            min_value=0.0,
            step=10.0,
            key="max_market_cap",
            help="0で制限なし"
        )

    # PER
    st.sidebar.subheader("PER（株価収益率）")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_per = st.number_input("最小", min_value=0.0, step=1.0, key="min_per")
    with col2:
        max_per = st.number_input("最大", min_value=0.0, step=1.0, key="max_per", help="0で制限なし")

    # 配当利回り
    st.sidebar.subheader("配当利回り（%）")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_div = st.number_input("最小", min_value=0.0, step=0.5, key="min_div")
    with col2:
        max_div = st.number_input("最大", min_value=0.0, step=0.5, key="max_div", help="0で制限なし")

    # ROE
    min_roe = st.sidebar.number_input(
        "最小ROE（%）",
        min_value=0.0,
        step=1.0,
        key="min_roe"
    )

    # ROA
    min_roa = st.sidebar.number_input(
        "最小ROA（%）",
        min_value=0.0,
        step=1.0,
        key="min_roa"
    )

    # 売上高成長率
    min_revenue_growth = st.sidebar.number_input(
        "最小売上高成長率（%）",
        min_value=-100.0,
        step=5.0,
        key="min_revenue_growth"
    )

    # EPS成長
    st.sidebar.subheader("EPS成長")
    eps_mode = st.sidebar.radio(
        "EPS成長条件",
        ["年率成長率", "連続増加年数", "両方"],
        key="eps_mode"
    )

    min_eps_growth = None
    min_eps_consecutive = None

    if eps_mode in ["年率成長率", "両方"]:
        min_eps_growth = st.sidebar.number_input(
            "最小EPS年率成長率（%）",
            min_value=-100.0,
            step=5.0,
            key="min_eps_growth"
        )

    if eps_mode in ["連続増加年数", "両方"]:
        min_eps_consecutive = st.sidebar.number_input(
            "最小EPS連続増加年数",
            min_value=0,
            step=1,
            key="min_eps_consecutive"
        )

    # インサイダー保有率
    st.sidebar.subheader("インサイダー保有率（%）")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_insider = st.number_input("最小", min_value=0.0, step=1.0, key="min_insider")
    with col2:
        max_insider = st.number_input("最大", min_value=0.0, step=5.0, key="max_insider", help="0で制限なし")

    # FCF利回り
    min_fcf_yield = st.sidebar.number_input(
        "最小FCF利回り（%）",
        min_value=-100.0,
        step=1.0,
        key="min_fcf_yield"
    )

    # テクニカル条件
    st.sidebar.header("📈 テクニカル")

    # RSI
    st.sidebar.subheader("RSI")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_rsi = st.number_input("最小", min_value=0.0, max_value=100.0, step=5.0, key="min_rsi")
    with col2:
        max_rsi = st.number_input("最大", min_value=0.0, max_value=100.0, step=5.0, key="max_rsi", help="100で制限なし")

    # 移動平均線
    st.sidebar.subheader("移動平均線")
    above_sma_20  = st.sidebar.checkbox("SMA20より上",  key="above_sma_20")
    above_sma_50  = st.sidebar.checkbox("SMA50より上",  key="above_sma_50")
    above_sma_200 = st.sidebar.checkbox("SMA200より上", key="above_sma_200")

    # 52週高値からの乖離
    st.sidebar.subheader("52週高値からの乖離（%）")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_from_high = st.number_input("最小", min_value=-100.0, step=5.0, key="min_from_high", help="-100で制限なし")
    with col2:
        max_from_high = st.number_input("最大", min_value=-100.0, max_value=0.0, step=5.0, key="max_from_high", help="0で制限なし")

    # トレンドシグナル
    trend_signals = st.sidebar.multiselect(
        "トレンドシグナル",
        ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"],
        key="trend_signals"
    )

    # 条件オブジェクトを作成
    criteria = ScreeningCriteria(
        min_market_cap=min_market_cap * 1e8 if min_market_cap > 0 else None,
        max_market_cap=max_market_cap * 1e8 if max_market_cap > 0 else None,
        min_per=min_per if min_per > 0 else None,
        max_per=max_per if max_per > 0 else None,
        min_dividend_yield=min_div if min_div > 0 else None,
        max_dividend_yield=max_div if max_div > 0 else None,
        min_roe=min_roe if min_roe > 0 else None,
        min_roa=min_roa if min_roa > 0 else None,
        min_revenue_growth=min_revenue_growth if min_revenue_growth != 0 else None,
        min_eps_growth=min_eps_growth if min_eps_growth and min_eps_growth != 0 else None,
        min_eps_consecutive_years=min_eps_consecutive if min_eps_consecutive and min_eps_consecutive > 0 else None,
        min_insider_hold=min_insider if min_insider > 0 else None,
        max_insider_hold=max_insider if max_insider > 0 else None,
        min_fcf_yield=min_fcf_yield if min_fcf_yield != 0 else None,
        min_rsi=min_rsi if min_rsi > 0 else None,
        max_rsi=max_rsi if max_rsi < 100 else None,
        above_sma_20=True if above_sma_20 else None,
        above_sma_50=True if above_sma_50 else None,
        above_sma_200=True if above_sma_200 else None,
        min_pct_from_52w_high=min_from_high if min_from_high > -100 else None,
        max_pct_from_52w_high=max_from_high if max_from_high < 0 else None,
        trend_signals=trend_signals if trend_signals else []
    )

    return criteria


def render_main_content(criteria: ScreeningCriteria):
    """メインコンテンツのレンダリング"""
    st.title("📈 米国株スクリーナー")

    # タブを作成
    tab1, tab2, tab3 = st.tabs(["スクリーニング", "個別銘柄分析", "バックテスト"])

    with tab1:
        render_screening_tab(criteria)

    with tab2:
        render_individual_analysis_tab()

    with tab3:
        render_backtest_tab(criteria)


def render_screening_tab(criteria: ScreeningCriteria):
    """スクリーニングタブのレンダリング"""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        # 銘柄数の選択
        num_stocks = st.selectbox(
            "分析銘柄数",
            [10, 25, 50, 100, 200, 500, 1000, 3000, 99999],
            format_func=lambda x: "全件（約8,000銘柄）" if x == 99999 else str(x),
            index=2,
            help="NASDAQ/NYSE/AMEXの全上場銘柄を対象にできます。全件は数時間かかります"
        )

    with col2:
        # テクニカル分析を含めるか
        include_tech = st.checkbox("テクニカル分析を含める", value=True)
        # 並列数
        max_workers = st.selectbox(
            "並列数",
            [1, 3, 5, 10, 20],
            index=2,
            help="大きいほど高速。APIレート制限に引っかかる場合は小さくしてください"
        )

    with col3:
        sc = st.session_state.sc  # スレッドと共有する plain dict
        if not sc["running"]:
            run_screening = st.button("🔍 スクリーニング実行", type="primary")
            cancel_screening = False
        else:
            run_screening = False
            cancel_screening = st.button("⏹ 中断", type="secondary")

    # 中断ボタン処理（st.session_stateは触らずdictのみ操作）
    if cancel_screening:
        sc["cancel"].set()

    # 実行ボタン処理
    if run_screening:
        screener = st.session_state.screener
        tickers  = screener.get_sample_tickers(num_stocks)

        sc["running"]  = True
        sc["cancel"].clear()
        sc["logs"]     = [f"開始: {len(tickers)}銘柄を分析します"]
        sc["results"]  = pd.DataFrame()
        sc["progress"] = 0.0
        st.session_state.results = pd.DataFrame()

        # スレッドには dict を直接渡すので st.session_state に触れない
        def run_screening_thread(sc, screener, tickers, criteria, include_tech, max_workers):
            def on_progress(pct, msg):
                sc["progress"] = pct
                sc["logs"].append(msg)
                if len(sc["logs"]) > 500:
                    sc["logs"] = sc["logs"][-500:]

            def on_log(msg):
                sc["logs"].append(msg)
                if len(sc["logs"]) > 500:
                    sc["logs"] = sc["logs"][-500:]

            try:
                results = screener.screen_stocks(
                    tickers,
                    criteria,
                    progress_callback=on_progress,
                    log_callback=on_log,
                    cancel_event=sc["cancel"],
                    include_technicals=include_tech,
                    max_workers=max_workers,
                )
                sc["results"] = results
            except Exception as e:
                on_log(f"[エラー] {e}")
            finally:
                sc["running"] = False

        t = threading.Thread(
            target=run_screening_thread,
            args=(sc, screener, tickers, criteria, include_tech, max_workers),
            daemon=True,
        )
        t.start()
        st.rerun()

    # ---- UI 表示（st.session_state.sc から読む）----
    sc = st.session_state.sc

    if sc["running"]:
        pct = sc["progress"]
        st.progress(pct, text=f"スクリーニング実行中... {pct*100:.0f}%")

    if sc["logs"]:
        st.subheader("ログ")
        try:
            log_container = st.container(height=300)
            log_container.code("\n".join(sc["logs"]), language=None)
        except TypeError:
            # 古いStreamlitバージョン向けフォールバック
            st.code("\n".join(sc["logs"]), language=None)

        if st.button("ログをクリア", key="clear_log"):
            sc["logs"] = []
            st.rerun()

    # 実行中は自動リフレッシュ
    if sc["running"]:
        import time as _time
        _time.sleep(1)
        st.rerun()

    # 結果を表示（スレッドが書き込んだ results を session_state に反映）
    if not sc["running"] and not sc["results"].empty:
        st.session_state.results = sc["results"]

    if not st.session_state.results.empty:
        display_results(st.session_state.results)
    elif not sc["running"] and not sc["logs"]:
        st.info("スクリーニングを実行してください")


def display_results(results: pd.DataFrame):
    """スクリーニング結果を表示"""
    st.subheader(f"結果: {len(results)}銘柄")

    # 表示するカラムを選択
    display_cols = []
    available_cols = results.columns.tolist()

    # 基本情報
    for col in ["ticker", "name", "sector"]:
        if col in available_cols:
            display_cols.append(col)

    # ファンダメンタル
    for col in ["per", "pbr", "dividend_yield", "roe", "roa", "revenue_growth",
                "eps_growth_rate", "eps_consecutive_years", "insider_hold", "fcf_yield"]:
        if col in available_cols:
            display_cols.append(col)

    # テクニカル
    for col in ["current_price", "rsi", "trend_signal", "pct_from_high"]:
        if col in available_cols:
            display_cols.append(col)

    # 時価総額フォーマット
    if "market_cap" in results.columns:
        results["market_cap_fmt"] = results["market_cap"].apply(format_market_cap)
        display_cols.insert(3, "market_cap_fmt")

    # 数値フォーマット
    display_df = results[display_cols].copy()
    for col in display_df.columns:
        if display_df[col].dtype in ["float64", "float32"]:
            display_df[col] = display_df[col].round(2)

    # カラム名を日本語に変換
    column_names = {
        "ticker": "ティッカー",
        "name": "企業名",
        "sector": "セクター",
        "market_cap_fmt": "時価総額",
        "per": "PER",
        "pbr": "PBR",
        "dividend_yield": "配当利回り(%)",
        "roe": "ROE(%)",
        "roa": "ROA(%)",
        "revenue_growth": "売上成長率(%)",
        "eps_growth_rate": "EPS成長率(%)",
        "eps_consecutive_years": "EPS連続増加",
        "insider_hold": "インサイダー(%)",
        "fcf_yield": "FCF利回り(%)",
        "current_price": "現在価格",
        "rsi": "RSI",
        "trend_signal": "シグナル",
        "pct_from_high": "高値乖離(%)"
    }
    display_df = display_df.rename(columns=column_names)

    # データフレームを表示（行クリックで個別分析）
    st.caption("行をクリックすると個別分析を表示します")
    try:
        event = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_rows = event.selection.rows if event.selection else []
    except TypeError:
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        selected_rows = []

    # エクスポートボタン
    csv = results.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 CSVダウンロード",
        data=csv,
        file_name="screening_results.csv",
        mime="text/csv"
    )

    # 選択行の個別分析を表示
    if selected_rows and "ticker" in results.columns:
        ticker = results.iloc[selected_rows[0]]["ticker"]
        st.session_state.selected_ticker = ticker
        st.divider()
        st.subheader(f"📊 {ticker} の詳細分析")
        analyze_individual_stock(ticker)


def render_individual_analysis_tab():
    """個別銘柄分析タブ"""
    st.subheader("個別銘柄分析")

    # ティッカー入力
    ticker = st.text_input(
        "ティッカーシンボル",
        value=st.session_state.selected_ticker or "AAPL",
        key="individual_ticker"
    ).upper()

    if st.button("分析", key="analyze_individual"):
        analyze_individual_stock(ticker)


def analyze_individual_stock(ticker: str):
    """個別銘柄の詳細分析"""
    with st.spinner(f"{ticker}を分析中..."):
        fetcher = DataFetcher()
        fund_analyzer = FundamentalAnalyzer()

        # データを取得
        info = fetcher.get_stock_info(ticker)
        if info is None:
            st.error(f"{ticker}のデータを取得できませんでした")
            return

        financials = fetcher.get_financials(ticker)
        history = fetcher.get_stock_history(ticker, period="1y")

        # 基本情報
        st.header(f"{info.get('longName', ticker)} ({ticker})")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("現在価格", f"${info.get('currentPrice', 'N/A'):.2f}" if info.get('currentPrice') else "N/A")
        with col2:
            st.metric("時価総額", format_market_cap(info.get('marketCap')))
        with col3:
            change = info.get('regularMarketChangePercent', 0)
            st.metric("日次変動", f"{change:.2f}%" if change else "N/A")
        with col4:
            st.metric("セクター", info.get('sector', 'N/A'))

        # ファンダメンタル指標
        st.subheader("📊 ファンダメンタル指標")
        fundamentals = fund_analyzer.get_all_fundamentals(info, financials)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("PER", f"{fundamentals['per']:.2f}" if fundamentals['per'] else "N/A")
            st.metric("ROE", f"{fundamentals['roe']:.2f}%" if fundamentals['roe'] else "N/A")
        with col2:
            st.metric("PBR", f"{fundamentals['pbr']:.2f}" if fundamentals['pbr'] else "N/A")
            st.metric("ROA", f"{fundamentals['roa']:.2f}%" if fundamentals['roa'] else "N/A")
        with col3:
            st.metric("配当利回り", f"{fundamentals['dividend_yield']:.2f}%" if fundamentals['dividend_yield'] else "N/A")
            st.metric("売上成長率", f"{fundamentals['revenue_growth']:.2f}%" if fundamentals['revenue_growth'] else "N/A")
        with col4:
            st.metric("インサイダー保有", f"{fundamentals['insider_hold']:.2f}%" if fundamentals['insider_hold'] else "N/A")
            st.metric("FCF利回り", f"{fundamentals['fcf_yield']:.2f}%" if fundamentals['fcf_yield'] else "N/A")

        # EPS成長
        col1, col2 = st.columns(2)
        with col1:
            st.metric("EPS年率成長率", f"{fundamentals['eps_growth_rate']:.2f}%" if fundamentals['eps_growth_rate'] else "N/A")
        with col2:
            st.metric("EPS連続増加年数", f"{fundamentals['eps_consecutive_years']}年")

        # テクニカル指標とチャート
        if history is not None and not history.empty:
            st.subheader("📈 テクニカル分析")

            tech_analyzer = TechnicalAnalyzer(history)
            technicals = tech_analyzer.get_all_technicals()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("RSI", f"{technicals['rsi']:.2f}" if technicals['rsi'] else "N/A")
            with col2:
                st.metric("52週高値乖離", f"{technicals['pct_from_high']:.2f}%" if technicals['pct_from_high'] else "N/A")
            with col3:
                st.metric("SMA200乖離", f"{technicals.get('pct_from_sma_200', 0):.2f}%")
            with col4:
                signal = get_trend_signal(technicals)
                st.metric("シグナル", signal)

            # チャートを描画
            render_price_chart(history, ticker, technicals)


def render_price_chart(history: pd.DataFrame, ticker: str, technicals: dict):
    """価格チャートを描画"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3]
    )

    # ローソク足
    fig.add_trace(
        go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name="価格"
        ),
        row=1, col=1
    )

    # 移動平均線
    close = history["Close"]
    for period, color in [(20, "orange"), (50, "blue"), (200, "purple")]:
        if len(close) >= period:
            sma = close.rolling(window=period).mean()
            fig.add_trace(
                go.Scatter(
                    x=history.index,
                    y=sma,
                    mode="lines",
                    name=f"SMA{period}",
                    line=dict(color=color, width=1)
                ),
                row=1, col=1
            )

    # 出来高
    colors = ["red" if close.iloc[i] < close.iloc[i-1] else "green"
              for i in range(1, len(close))]
    colors.insert(0, "green")

    fig.add_trace(
        go.Bar(
            x=history.index,
            y=history["Volume"],
            name="出来高",
            marker_color=colors
        ),
        row=2, col=1
    )

    # レイアウト
    fig.update_layout(
        title=f"{ticker} 株価チャート（1年）",
        xaxis_rangeslider_visible=False,
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    fig.update_yaxes(title_text="価格", row=1, col=1)
    fig.update_yaxes(title_text="出来高", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)


def render_backtest_tab(criteria: ScreeningCriteria):
    """バックテストタブ"""
    st.subheader("バックテスト")
    st.caption("サイドバーで設定したスクリーニング条件を過去の日付に適用し、その後のリターンを検証します。")
    st.caption("⚠️ 配当利回り・インサイダー保有率は過去値が取得困難なため現在値で代用。上場廃止銘柄は含まれません。")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input(
            "スクリーニング基準日",
            value=(datetime.today() - timedelta(days=365)).date(),
            max_value=(datetime.today() - timedelta(days=30)).date(),
            key="bt_start_date",
        )
    with col2:
        end_date = st.date_input(
            "リターン計測終了日",
            value=datetime.today().date(),
            max_value=datetime.today().date(),
            key="bt_end_date",
        )
    with col3:
        bt_num_stocks = st.selectbox(
            "分析銘柄数",
            [50, 100, 200, 500],
            index=1,
            key="bt_num_stocks",
        )
        bt_workers = st.selectbox(
            "並列数",
            [3, 5, 10],
            index=1,
            key="bt_workers",
        )

    if start_date >= end_date:
        st.error("終了日は基準日より後にしてください")
        return

    run_bt = st.button("バックテスト実行", type="primary", key="run_backtest")

    if run_bt:
        with st.spinner("バックテスト実行中..."):
            engine = BacktestEngine()
            screener = st.session_state.screener
            tickers = screener.get_sample_tickers(bt_num_stocks)

            progress_bar = st.progress(0)
            status_text  = st.empty()

            def update_progress(pct, msg):
                progress_bar.progress(pct)
                status_text.text(msg)

            result = engine.run(
                tickers=tickers,
                criteria=criteria,
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.min.time()),
                progress_callback=update_progress,
                max_workers=bt_workers,
            )

            progress_bar.empty()
            status_text.empty()
            st.session_state["bt_result"] = result

    # 結果を表示
    result = st.session_state.get("bt_result")
    if result:
        _render_backtest_result(result)


def _render_backtest_result(result: dict):
    """バックテスト結果を描画"""
    selected_df      = result["selected"]
    portfolio_return = result["portfolio_return"]
    benchmark_return = result["benchmark_return"]
    start_date       = result["start_date"]
    end_date         = result["end_date"]
    screened_count   = result["screened_count"]
    total_count      = result["total_count"]

    holding_days = (end_date - start_date).days

    # サマリー指標
    st.subheader("サマリー")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("分析銘柄数", f"{total_count}銘柄")
    with c2:
        st.metric("条件通過銘柄数", f"{screened_count}銘柄")
    with c3:
        port_str = f"{portfolio_return:+.2f}%" if portfolio_return is not None else "N/A"
        delta_str = None
        if portfolio_return is not None and benchmark_return is not None:
            delta_str = f"{portfolio_return - benchmark_return:+.2f}% vs SPY"
        st.metric("ポートフォリオリターン", port_str, delta=delta_str)
    with c4:
        bench_str = f"{benchmark_return:+.2f}%" if benchmark_return is not None else "N/A"
        st.metric("SPY（ベンチマーク）", bench_str)

    st.caption(f"期間: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}  ({holding_days}日間 / 等重ポートフォリオ)")

    if selected_df.empty:
        st.info("条件に一致する銘柄が見つかりませんでした。条件を緩めてみてください。")
        return

    # 累積リターン曲線
    st.subheader("累積リターン推移")
    equity_curve = build_equity_curve(selected_df, start_date, end_date)
    if not equity_curve.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity_curve.index, y=equity_curve["portfolio"],
            mode="lines", name="ポートフォリオ（等重）",
            line=dict(color="royalblue", width=2),
        ))
        if "benchmark" in equity_curve.columns and equity_curve["benchmark"].notna().any():
            fig.add_trace(go.Scatter(
                x=equity_curve.index, y=equity_curve["benchmark"],
                mode="lines", name="SPY（ベンチマーク）",
                line=dict(color="gray", width=1.5, dash="dash"),
            ))
        fig.add_hline(y=0, line_color="black", line_width=0.8)
        fig.update_layout(
            yaxis_title="累積リターン (%)",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    # リターン分布ヒストグラム
    st.subheader("リターン分布")
    fig2 = go.Figure()
    fig2.add_trace(go.Histogram(
        x=selected_df["return_pct"].dropna(),
        nbinsx=20,
        marker_color="royalblue",
        opacity=0.75,
        name="条件通過銘柄",
    ))
    if benchmark_return is not None:
        fig2.add_vline(
            x=benchmark_return, line_color="gray", line_dash="dash",
            annotation_text=f"SPY: {benchmark_return:+.1f}%",
        )
    if portfolio_return is not None:
        fig2.add_vline(
            x=portfolio_return, line_color="royalblue",
            annotation_text=f"平均: {portfolio_return:+.1f}%",
        )
    fig2.update_layout(xaxis_title="リターン (%)", yaxis_title="銘柄数", height=300)
    st.plotly_chart(fig2, use_container_width=True)

    # 銘柄別リターン一覧
    st.subheader("条件通過銘柄のリターン一覧")
    show_cols = [c for c in ["ticker", "name", "sector", "per", "roe", "revenue_growth",
                              "rsi", "trend_signal", "return_pct"] if c in selected_df.columns]
    disp = selected_df[show_cols].copy()
    for col in disp.select_dtypes("float64").columns:
        disp[col] = disp[col].round(2)
    disp = disp.rename(columns={
        "ticker": "ティッカー", "name": "企業名", "sector": "セクター",
        "per": "PER", "roe": "ROE(%)", "revenue_growth": "売上成長率(%)",
        "rsi": "RSI", "trend_signal": "シグナル", "return_pct": "リターン(%)",
    })
    disp = disp.sort_values("リターン(%)", ascending=False)
    st.dataframe(disp, use_container_width=True, hide_index=True)

    # CSV ダウンロード
    csv = selected_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSVダウンロード", data=csv,
                       file_name="backtest_result.csv", mime="text/csv")


def main():
    """メイン関数"""
    init_session_state()
    criteria = render_sidebar()
    render_main_content(criteria)


if __name__ == "__main__":
    main()
