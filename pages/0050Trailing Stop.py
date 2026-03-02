###############################################################
# app.py — 0050 趨勢保護 + 絕對獲利策略
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# --- 1. 環境設定 ---
TICKER_NAMES = {
    "0050.TW": "0050 元大台灣50",
    "006208.TW": "006208 富邦台50",
    "00631L.TW": "00631L 元大台灣50正2",
    "BTC-USD": "BTC-USD 比特幣"
}

st.set_page_config(page_title="絕對獲利策略", page_icon="🛡️", layout="wide")

# --- 2. 核心計算函數 ---
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

def get_stats(eq, rets, y):
    f_eq = eq.iloc[-1]
    f_ret = f_eq - 1
    cagr = (1 + f_ret)**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq / eq.cummax()).min()
    vol = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0
    return f_eq, f_ret, cagr, mdd, vol, sharpe

# --- 3. UI 介面 ---
st.markdown("# 🛡️ 趨勢保護 + 絕對獲利策略")
st.info("規則：1. 收盤 < 200SMA 必賣 | 2. 獲利回檔才賣 | 3. 虧損時除非破 SMA 否則死抱")

available_ids = sorted([f.stem for f in DATA_DIR.glob("*.csv")])
target_id = st.selectbox("選擇標的", available_ids, format_func=lambda x: TICKER_NAMES.get(x, x))

df_raw = load_csv(target_id)
s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()

col_p1, col_p2, col_p3 = st.columns(3)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 10000000, 100000)

st.write("---")
col_set1, col_set2, col_set3 = st.columns(3)
sma_window = col_set1.number_input("長線趨勢 (SMA)", 10, 300, 200)
buy_pct = col_set2.number_input("進場：低點反彈 (%)", 0.5, 20.0, 3.0)
sell_pct = col_set3.number_input("出場：高點回落 (%)", 0.5, 20.0, 3.0)

# --- 4. 執行策略 ---
if st.button("啟動回測 🚀"):
    df = df_raw.loc[:end].copy()
    df["SMA"] = df["Price"].rolling(sma_window).mean()
    df = df.loc[start:].dropna(subset=["SMA"])

    # 狀態變數
    in_position = False
    entry_price = 0.0
    trailing_low = df["Price"].iloc[0]
    trailing_high = 0.0
    
    sigs = [0] * len(df)
    pos = [0.0] * len(df)
    exit_reason = [""] * len(df)

    for i in range(1, len(df)):
        p = df["Price"].iloc[i]
        sma = df["SMA"].iloc[i]
        
        if not in_position:
            # 更新離場後的最低點
            trailing_low = min(trailing_low, p)
            buy_trigger = trailing_low * (1 + buy_pct / 100)
            
            # 買入條件：股價 > SMA 且 股價 > 買進觸發線
            if p > sma and p >= buy_trigger:
                in_position = True
                entry_price = p
                trailing_high = p
                sigs[i] = 1
        else:
            # 更新持倉期間的最高點
            trailing_high = max(trailing_high, p)
            sell_trigger = trailing_high * (1 - sell_pct / 100)
            
            # 出場條件 1：破 SMA (強制停損)
            if p < sma:
                in_position = False
                sigs[i] = -1
                exit_reason[i] = "SMA 停損"
                trailing_low = p # 重置低點追蹤
            
            # 出場條件 2：回落觸發 且 價格 > 買進成本 (絕對獲利)
            elif p <= sell_trigger and p > entry_price:
                in_position = False
                sigs[i] = -1
                exit_reason[i] = "獲利入袋"
                trailing_low = p # 重置低點追蹤

        pos[i] = 1.0 if in_position else 0.0

    df["Signal"], df["Position"] = sigs, pos
    
    # 計算報酬
    equity = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity"] = equity
    df["Return"] = df["Equity"].pct_change().fillna(0)
    df["Equity_BH"] = df["Price"] / df["Price"].iloc[0]
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity"], df["Return"], y_len)
    sb = get_stats(df["Equity_BH"], df["Price"].pct_change().fillna(0), y_len)

    # --- 5. 顯示結果 ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", f"{sl[0]*capital:,.0f}", f"{(sl[0]/sb[0]-1):+.2%}")
    k2.metric("年化報酬 (CAGR)", f"{sl[2]:.2%}", f"{(sl[2]-sb[2]):+.2%}")
    k3.metric("最大回撤 (MDD)", f"{sl[3]:.2%}", f"{(sl[3]-sb[3]):+.2%}", delta_color="inverse")
    k4.metric("交易次數", f"{(df['Signal']!=0).sum()} 次")

    # 圖表
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.4, 0.6])
    
    # 資金曲線
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity"], name="策略", line=dict(color="#00D494", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"], name="標的持有的報酬", line=dict(color="#94A3B8", dash="dash")), row=1, col=1)
    
    # 價格與 SMA
    fig.add_trace(go.Scatter(x=df.index, y=df["Price"], name="股價", line=dict(color="#1E293B")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#F59E0B")), row=2, col=1)
    
    # 標註買賣點
    buy_pts = df[df["Signal"] == 1]
    sell_pts = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(x=buy_pts.index, y=buy_pts["Price"], mode="markers", marker=dict(symbol="triangle-up", size=10, color="#10B981"), name="買進"), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell_pts.index, y=sell_pts["Price"], mode="markers", marker=dict(symbol="triangle-down", size=10, color="#EF4444"), name="賣出"), row=2, col=1)

    fig.update_layout(height=700, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig, use_container_width=True)
