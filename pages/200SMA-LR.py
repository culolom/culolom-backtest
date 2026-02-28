###############################################################
# app.py — 0050 多空切換策略 (00631L vs 00632R)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path
import sys

# 字型與頁面設定保持不變...
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="0050 多空切換回測", page_icon="📉", layout="wide")

# ------------------------------------------------------
# 🔒 驗證 (略，同原代碼)
# ------------------------------------------------------

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 多空切換策略</h1>", unsafe_allow_html=True)
st.markdown("當 0050 > SMA 買入 **00631L**；當 0050 < SMA 買入 **00632R**。")

# ETF 清單定義
BASE_ETFS = {"0050 元大台灣50": "0050.TW"}
BULL_ETFS = {"00631L 元大台灣50正2": "00631L.TW"}
BEAR_ETFS = {"00632R 元大台灣50反1": "00632R.TW"}
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# --- UI 輸入 ---
col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF (訊號來源)", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200)

col3, col4, col5 = st.columns(3)
with col3:
    capital = st.number_input("投入本金", 1000, 5000000, 100000)
with col4:
    start_date = st.date_input("開始日期", dt.date(2015, 1, 1))
with col5:
    end_date = st.date_input("結束日期", dt.date.today())

if st.button("開始回測 🚀"):
    # 1. 讀取三份資料
    df_base = load_csv(base_symbol)
    df_bull = load_csv("00631L.TW")
    df_bear = load_csv("00632R.TW")

    if df_base.empty or df_bull.empty or df_bear.empty:
        st.error("找不到 0050、00631L 或 00632R 的 CSV 資料")
        st.stop()

    # 2. 合併與預處理
    df = df_base.rename(columns={"Price": "Price_base"})
    df = df.join(df_bull.rename(columns={"Price": "Price_bull"}), how="inner")
    df = df.join(df_bear.rename(columns={"Price": "Price_bear"}), how="inner")
    
    # 計算 SMA
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start_date:end_date].dropna(subset=["SMA"])

    # 3. 策略核心邏輯：多空切換
    # 決定每日報酬來源
    df["Ret_bull"] = df["Price_bull"].pct_change().fillna(0)
    df["Ret_bear"] = df["Price_bear"].pct_change().fillna(0)
    
    # 訊號：1 為做多正2，-1 為做多反1
    df["Signal"] = np.where(df["Price_base"] > df["SMA"], 1, -1)
    
    # 計算策略報酬：今天的報酬取決於「昨晚收盤後」決定的訊號
    df["Strategy_Ret"] = 0.0
    for i in range(1, len(df)):
        current_sig = df["Signal"].iloc[i-1]
        if current_sig == 1:
            df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bull"].iloc[i]
        else:
            df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bear"].iloc[i]

    # 4. 淨值與指標
    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_0050"] = (1 + df["Price_base"].pct_change().fillna(0)).cumprod()
    
    # --- 圖表展示 ---
    st.subheader("📈 策略淨值曲線 (對比 0050)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="多空切換策略 (631L/632R)"))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_0050"]-1, name="0050 Buy & Hold"))
    fig.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"))
    st.plotly_chart(fig, use_container_width=True)

    # --- 交易訊號圖 ---
    st.subheader("🔍 價格與均線訊號")
    fig_sig = go.Figure()
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 價格", line=dict(color="gray")))
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="orange")))
    
    # 標註做多與做空區間
    df["Color"] = np.where(df["Signal"] == 1, "rgba(0, 255, 0, 0.1)", "rgba(255, 0, 0, 0.1)")
    # (此處可進一步開發區間著色，簡化起見先以數值顯示)
    st.plotly_chart(fig_sig, use_container_width=True)

    # --- 指標統計 ---
    def get_mdd(eq):
        return (eq / eq.cummax() - 1).min()

    final_ret = df["Equity_Strategy"].iloc[-1] - 1
    mdd = get_mdd(df["Equity_Strategy"])
    
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("策略總報酬", f"{final_ret:.2%}")
    col_m2.metric("最大回撤 (MDD)", f"{mdd:.2%}")

    # 下載按鈕
    csv = df.to_csv().encode('utf-8-sig')
    st.download_button("📥 下載數據", csv, "strategy_results.csv", "text/csv")
