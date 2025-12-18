import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面與資料設定
###############################################################
st.set_page_config(page_title="單標的 LRS + 乖離套利系統", page_icon="📈", layout="wide")

# 標的清單 (可自行增加)
ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
}

DATA_DIR = Path("data")
WINDOW = 200

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# 🔒 認證 (保持原本邏輯)
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except: pass

###############################################################
# 2. 主頁面輸入區 (取代 Sidebar)
###############################################################
st.markdown("<h1 style='text-align: center;'>📊 單標的 LRS 動態策略回測</h1>", unsafe_allow_html=True)

# 使用 Container 集中回測條件
with st.container(border=True):
    st.subheader("⚙️ 核心回測條件設定")
    
    # 第一排：標的與本金
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        target_label = st.selectbox("選擇回測標的", list(ETFS.keys()))
        target_symbol = ETFS[target_label]
    with c2:
        capital = st.number_input("投入本金 (元)", 1000, 10_000_000, 100_000, step=10000)
    with c3:
        pos_init = st.radio("初始狀態", ["空手起跑", "一開始就全倉"], horizontal=True)

    # 第二排：日期區間
    df_raw = load_csv(target_symbol)
    if not df_raw.empty:
        s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()
        c4, c5 = st.columns(2)
        with c4:
            start_date = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=365*5)), min_value=s_min, max_value=s_max)
        with c5:
            end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
    else:
        st.error("找不到資料檔案，請確認 data/*.csv 存在")
        st.stop()

    st.divider()
    
    # 第三排：乖離率進階設定
    st.subheader("🎯 乖離率套利增強")
    c6, c7, c8 = st.columns([1, 2, 2])
    with c6:
        enable_bias = st.toggle("啟用乖離率策略", value=True)
    with c7:
        bias_sell_pct = st.slider("高位套利賣出點 (%)", 10, 60, 40) if enable_bias else 40
    with c8:
        bias_buy_pct = st.slider("低位抄底買進點 (%)", -50, -5, -20) if enable_bias else -20

    # 執行按鈕
    btn_run = st.button("開始回測 🚀", use_container_width=True, type="primary")

###############################################################
# 3. 回測計算與圖表
###############################################################
if btn_run:
    # 準備資料 (預留 365 天計算均線)
    df = df_raw.loc[pd.to_datetime(start_date) - dt.timedelta(days=365) : pd.to_datetime(end_date)].copy()
    
    # 計算均線與乖離率
    df["MA_200"] = df["Price"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_date):pd.to_datetime(end_date)]

    # 訊號與持倉邏輯
    df["Signal"] = 0
    df["Signal_Note"] = ""
    current_pos = 1 if "全倉" in pos_init else 0
    
    for i in range(1, len(df)):
        p, m, b = df["Price"].iloc[i], df["MA_200"].iloc[i], df["Bias_200"].iloc[i]
        p0, m0 = df["Price"].iloc[i-1], df["MA_200"].iloc[i-1]
        
        # 乖離率優先
        if enable_bias:
            if b > bias_sell_pct and current_pos == 1:
                df.iloc[i, df.columns.get_loc("Signal")] = -1
                df.iloc[i, df.columns.get_loc("Signal_Note")] = "乖離套利賣"
                current_pos = 0; continue
            elif b < bias_buy_pct and current_pos == 0:
                df.iloc[i, df.columns.get_loc("Signal")] = 1
                df.iloc[i, df.columns.get_loc("Signal_Note")] = "乖離抄底買"
                current_pos = 1; continue

        # LRS 邏輯
        if p > m and p0 <= m0 and current_pos == 0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
            df.iloc[i, df.columns.get_loc("Signal_Note")] = "LRS 買進"
            current_pos = 1
        elif p < m and p0 >= m0 and current_pos == 1:
            df.iloc[i, df.columns.get_loc("Signal")] = -1
            df.iloc[i, df.columns.get_loc("Signal_Note")] = "LRS 賣出"
            current_pos = 0

    # 計算績效
    pos = 1 if "全倉" in pos_init else 0
    pos_h = []
    for s in df["Signal"]:
        if s == 1: pos = 1
        elif s == -1: pos = 0
        pos_h.append(pos)
    df["Position"] = pos_h
    
    # 權益曲線
    equity = [1.0]
    for i in range(1, len(df)):
        r = df["Price"].iloc[i] / df["Price"].iloc[i-1] if df["Position"].iloc[i-1] == 1 else 1.0
        equity.append(equity[-1] * r)
    df["Equity"] = equity
    df["BH_Equity"] = df["Price"] / df["Price"].iloc[0]

    # --- 圖表呈現 ---
    st.divider()
    
    # 1. 價格與訊號圖
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price"], name="收盤價", line=dict(color="#636EFA")))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200SMA", line=dict(color="#FFA15A", dash="dash")))
    
    # 買賣標記
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    fig_p.add_trace(go.Scatter(x=buys.index, y=buys["Price"], mode="markers+text", name="買點", text=buys["Signal_Note"], textposition="top center", marker=dict(symbol="triangle-up", size=12, color="green")))
    fig_p.add_trace(go.Scatter(x=sells.index, y=sells["Price"], mode="markers+text", name="賣點", text=sells["Signal_Note"], textposition="bottom center", marker=dict(symbol="triangle-down", size=12, color="red")))
    fig_p.update_layout(height=500, title="📌 價格走勢與執行訊號", template="plotly_white")
    st.plotly_chart(fig_p, use_container_width=True)

    # 2. 乖離率與績效雙欄位
    c_left, c_right = st.columns(2)
    with c_left:
        fig_b = go.Figure()
        fig_b.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率", fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)'))
        if enable_bias:
            fig_b.add_hline(y=bias_sell_pct, line_dash="dash", line_color="red")
            fig_b.add_hline(y=bias_buy_pct, line_dash="dash", line_color="green")
        fig_b.update_layout(height=400, title="📈 200MA 乖離率監測", yaxis=dict(ticksuffix="%"), template="plotly_white")
        st.plotly_chart(fig_b, use_container_width=True)
        
    with c_right:
        fig_e = go.Figure()
        fig_e.add_trace(go.Scatter(x=df.index, y=df["Equity"]-1, name="策略績效", line=dict(color="#AB63FA", width=3)))
        fig_e.add_trace(go.Scatter(x=df.index, y=df["BH_Equity"]-1, name="買入持有", line=dict(color="silver")))
        fig_e.update_layout(height=400, title="💰 累積報酬率 (%)", yaxis=dict(tickformat=".1%"), template="plotly_white")
        st.plotly_chart(fig_e, use_container_width=True)

    # 3. KPI 結算
    mdd = 1 - (df["Equity"] / df["Equity"].cummax()).min()
    final_val = df["Equity"].iloc[-1] * capital
    
    k1, k2, k3 = st.columns(3)
    k1.metric("最終資產價值", f"{final_val:,.0f} 元", f"{(df['Equity'].iloc[-1]-1):.2%}")
    k2.metric("最大回撤 (MDD)", f"-{mdd:.2%}")
    k3.metric("總交易次數", f"{len(df[df['Signal']!=0])} 次")
