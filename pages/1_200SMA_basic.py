# 200 SMA 回測（統一使用本地 CSV 資料）

import os
import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hamster_data.loader import load_price, list_symbols

# === 字型設定 ===
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# === Streamlit 頁面設定 ===
st.set_page_config(page_title="200SMA 回測系統", page_icon="📈", layout="wide")
st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 200SMA 回測系統（本地 CSV 資料）</h1>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# 公用工具
# ---------------------------------------------------------------------
def select_price_column(df: pd.DataFrame) -> pd.Series:
    """Pick a usable price series from the dataframe."""
    for col in ["Adj Close", "Close", "Price"]:
        if col in df.columns:
            return df[col]
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        return df[numeric_cols[0]]
    raise ValueError("缺少價格欄位（需包含 Adj Close/Close/Price）")


# ---------------------------------------------------------------------
# 介面：使用者輸入
# ---------------------------------------------------------------------
etf_list = list_symbols()
if not etf_list:
    st.error("⚠️ data/ 資料夾中沒有 CSV，請先匯入價格檔案。")
    st.stop()

symbol = st.selectbox("選擇 ETF", etf_list)

try:
    df_full = load_price(symbol)
except FileNotFoundError:
    st.error("⚠️ 找不到對應的 CSV 檔案，請確認 data/ 目錄。")
    st.stop()
except ValueError as exc:
    st.error(f"⚠️ 資料檔案異常：{exc}")
    st.stop()
except Exception as exc:  # pragma: no cover - 防呆
    st.error(f"⚠️ 載入資料時發生錯誤：{exc}")
    st.stop()

if df_full.empty:
    st.error("該 ETF 無資料")
    st.stop()

try:
    select_price_column(df_full)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

available_start = df_full.index.min().date()
available_end = df_full.index.max().date()
st.info(f"📌 可回測區間：{available_start} ~ {available_end}")

col1, col2, col3 = st.columns(3)
with col1:
    start_default = max(available_start, available_end - dt.timedelta(days=5 * 365))
    start = st.date_input(
        "開始日期",
        value=start_default,
        min_value=available_start,
        max_value=available_end,
        format="YYYY/MM/DD",
    )
with col2:
    end = st.date_input(
        "結束日期",
        value=available_end,
        min_value=available_start,
        max_value=available_end,
        format="YYYY/MM/DD",
    )
with col3:
    initial_capital = st.number_input("投入本金（元）", 1000, 1_000_000, 10000, step=1000)

col4, col5 = st.columns(2)
with col4:
    ma_type = st.selectbox("均線種類", ["SMA", "EMA"])
with col5:
    window = st.slider("均線天數", 10, 200, 200, 10)


# ---------------------------------------------------------------------
# 主程式：回測 + 視覺化
# ---------------------------------------------------------------------
if st.button("開始回測 🚀"):
    if start >= end:
        st.error("⚠️ 開始日期需早於結束日期")
        st.stop()

    start_early = pd.to_datetime(start) - pd.Timedelta(days=365)

    df = df_full.copy()
    df = df[(df.index >= start_early) & (df.index <= pd.to_datetime(end))]

    if df.empty:
        st.error("該 ETF 無資料")
        st.stop()

    try:
        df["Price"] = select_price_column(df)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if len(df) < window:
        st.error(f"資料筆數不足以計算 {window} 日均線，請縮短均線天數或延長日期。")
        st.stop()

    if ma_type == "SMA":
        df["MA"] = df["Price"].rolling(window=window).mean()
    else:
        df["MA"] = df["Price"].ewm(span=window, adjust=False).mean()

    df = df.dropna(subset=["MA"])
    if df.empty:
        st.error("資料不足以產生均線，請調整參數。")
        st.stop()

    # === 生成訊號（第一天強制買入） ===
    df["Signal"] = 0
    if len(df) == 0:
        st.error("資料不足，請調整日期區間或均線天數。")
        st.stop()

    df.iloc[0, df.columns.get_loc("Signal")] = 1
    for i in range(1, len(df)):
        if df["Price"].iloc[i] > df["MA"].iloc[i] and df["Price"].iloc[i - 1] <= df["MA"].iloc[i - 1]:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif df["Price"].iloc[i] < df["MA"].iloc[i] and df["Price"].iloc[i - 1] >= df["MA"].iloc[i - 1]:
            df.iloc[i, df.columns.get_loc("Signal")] = -1
        else:
            df.iloc[i, df.columns.get_loc("Signal")] = 0

    # === 持倉 ===
    position, current = [], 1
    for sig in df["Signal"]:
        if sig == 1:
            current = 1
        elif sig == -1:
            current = 0
        position.append(current)
    df["Position"] = position

    # === 報酬 ===
    df["Return"] = df["Price"].pct_change().fillna(0)
    df["Strategy_Return"] = df["Return"] * df["Position"]

    # === 真實資金曲線 ===
    df["Equity_LRS"] = 1.0
    for i in range(1, len(df)):
        if df["Position"].iloc[i - 1] == 1:
            df.iloc[i, df.columns.get_loc("Equity_LRS")] = df["Equity_LRS"].iloc[i - 1] * (1 + df["Return"].iloc[i])
        else:
            df.iloc[i, df.columns.get_loc("Equity_LRS")] = df["Equity_LRS"].iloc[i - 1]

    df["Equity_BuyHold"] = (1 + df["Return"]).cumprod()

    # 只保留使用者選定區間，並從第一天重新歸一化
    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)].copy()
    df["Equity_LRS"] /= df["Equity_LRS"].iloc[0]
    df["Equity_BuyHold"] /= df["Equity_BuyHold"].iloc[0]

    df["LRS_Capital"] = df["Equity_LRS"] * initial_capital
    df["BH_Capital"] = df["Equity_BuyHold"] * initial_capital

    # === 買賣點 ===
    buy_points = [(df.index[i], df["Price"].iloc[i]) for i in range(1, len(df)) if df["Signal"].iloc[i] == 1]
    sell_points = [(df.index[i], df["Price"].iloc[i]) for i in range(1, len(df)) if df["Signal"].iloc[i] == -1]
    buy_count, sell_count = len(buy_points), len(sell_points)

    # === 指標 ===
    final_return_lrs = df["Equity_LRS"].iloc[-1] - 1
    final_return_bh = df["Equity_BuyHold"].iloc[-1] - 1
    years_len = (df.index[-1] - df.index[0]).days / 365
    cagr_lrs = (1 + final_return_lrs) ** (1 / years_len) - 1 if years_len > 0 else np.nan
    cagr_bh = (1 + final_return_bh) ** (1 / years_len) - 1 if years_len > 0 else np.nan
    mdd_lrs = 1 - (df["Equity_LRS"] / df["Equity_LRS"].cummax()).min()
    mdd_bh = 1 - (df["Equity_BuyHold"] / df["Equity_BuyHold"].cummax()).min()

    def calc_metrics(series):
        daily = series.dropna()
        if len(daily) <= 1:
            return np.nan, np.nan, np.nan
        avg = daily.mean()
        std = daily.std()
        downside = daily[daily < 0].std()
        vol = std * np.sqrt(252)
        sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
        sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
        return vol, sharpe, sortino

    vol_lrs, sharpe_lrs, sortino_lrs = calc_metrics(df["Strategy_Return"])
    vol_bh, sharpe_bh, sortino_bh = calc_metrics(df["Return"])

    equity_lrs_final = df["LRS_Capital"].iloc[-1]
    equity_bh_final = df["BH_Capital"].iloc[-1]

    # === 圖表 ===
    st.markdown("<h2 style='margin-top:1em;'>📈 策略績效視覺化</h2>", unsafe_allow_html=True)
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("收盤價與均線（含買賣點）", "資金曲線：LRS vs Buy&Hold"),
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["Price"], name="收盤價", line=dict(color="blue")),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["MA"], name=f"{ma_type}{window}", line=dict(color="orange")),
        row=1,
        col=1,
    )

    if buy_points:
        bx, by = zip(*buy_points)
        fig.add_trace(
            go.Scatter(
                x=bx,
                y=by,
                mode="markers",
                name="買進",
                marker=dict(color="green", symbol="triangle-up", size=8),
            ),
            row=1,
            col=1,
        )
    if sell_points:
        sx, sy = zip(*sell_points)
        fig.add_trace(
            go.Scatter(
                x=sx,
                y=sy,
                mode="markers",
                name="賣出",
                marker=dict(color="red", symbol="x", size=8),
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["Equity_LRS"], name="LRS 策略", line=dict(color="green")),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["Equity_BuyHold"], name="Buy & Hold", line=dict(color="gray", dash="dot")),
        row=2,
        col=1,
    )
    fig.update_layout(height=800, showlegend=True, template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

    # === 美化報表 ===
    st.markdown(
        """
    <style>
    .custom-table { width:100%; border-collapse:collapse; margin-top:1.2em; font-family:"Noto Sans TC"; }
    .custom-table th { background:#f5f6fa; padding:12px; font-weight:700; border-bottom:2px solid #ddd; }
    .custom-table td { text-align:center; padding:10px; border-bottom:1px solid #eee; font-size:15px; }
    .custom-table tr:nth-child(even) td { background-color:#fafbfc; }
    .custom-table tr:hover td { background-color:#f1f9ff; }
    .section-title td { background:#eef4ff; color:#1a237e; font-weight:700; font-size:16px; text-align:left; padding:10px 15px;
}
    </style>
    """,
        unsafe_allow_html=True,
    )

    html_table = f"""
    <table class='custom-table'>
    <thead><tr><th>指標名稱</th><th>LRS 策略</th><th>Buy & Hold</th></tr></thead>
    <tbody>
    <tr><td>最終資產</td><td>{equity_lrs_final:,.0f} 元</td><td>{equity_bh_final:,.0f} 元</td></tr>
    <tr><td>總報酬</td><td>{final_return_lrs:.2%}</td><td>{final_return_bh:.2%}</td></tr>
    <tr><td>年化報酬</td><td>{cagr_lrs:.2%}</td><td>{cagr_bh:.2%}</td></tr>
    <tr><td>最大回撤</td><td>{mdd_lrs:.2%}</td><td>{mdd_bh:.2%}</td></tr>
    <tr><td>年化波動率</td><td>{vol_lrs:.2%}</td><td>{vol_bh:.2%}</td></tr>
    <tr><td>夏普值</td><td>{sharpe_lrs:.2f}</td><td>{sharpe_bh:.2f}</td></tr>
    <tr><td>索提諾值</td><td>{sortino_lrs:.2f}</td><td>{sortino_bh:.2f}</td></tr>
    <tr class='section-title'><td colspan='3'>💹 交易統計</td></tr>
    <tr><td>買進次數</td><td>{buy_count}</td><td>—</td></tr>
    <tr><td>賣出次數</td><td>{sell_count}</td><td>—</td></tr>
    </tbody></table>
    """
    st.markdown(html_table, unsafe_allow_html=True)
    st.success("✅ 回測完成！（已使用統一資料層）")
