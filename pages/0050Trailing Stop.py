###############################################################
# app.py — 0050LRS 趨勢保護版 (絕對獲利 + SMA 強制停損)
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

# --- 字型與頁面設定 ---
st.set_page_config(page_title="0050LRS 趨勢保護版", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (保留原邏輯)
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import auth 
    if not auth.check_password(): st.stop()
except: pass 

# --- 1. 基礎設定與 CSV 讀取 ---
TICKER_NAMES = {
    "0050.TW": "0050 元大台灣50",
    "006208.TW": "006208 富邦台50",
    "00631L.TW": "00631L 元大台灣50正2",
    "00663L.TW": "00663L 國泰台灣加權正2",
    "00675L.TW": "00675L 富邦台灣加權正2",
    "00685L.TW": "00685L 群益台灣加權正2",
    "BTC-USD": "BTC-USD 比特幣"
}

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std = daily.mean(), daily.std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    return vol, sharpe

# --- 2. UI 介面 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### ⚙️ 策略參數")
    sma_window = st.number_input("長線趨勢 (SMA)", 10, 300, 200)
    buy_pct = st.number_input("進場：低點反彈 (%)", 0.5, 20.0, 3.0)
    sell_pct = st.number_input("出場：高點回落 (%)", 0.5, 20.0, 3.0)

st.markdown("# 📊 0050LRS 趨勢保護版")
st.info("💡 核心邏輯：1. 破 SMA 必賣 | 2. 高點回落 + 獲利才賣 | 3. 未獲利前除非破 SMA 否則死抱")

col1, col2 = st.columns(2)
base_id = col1.selectbox("原型 ETF (訊號來源)", ["0050.TW", "006208.TW"], format_func=lambda x: TICKER_NAMES.get(x, x))
lev_id = col2.selectbox("槓桿 ETF (實際交易)", ["00631L.TW", "00663L.TW", "00675L.TW", "00685L.TW"], format_func=lambda x: TICKER_NAMES.get(x, x))

df_preview = load_csv(base_id)
s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
col3, col4, col5 = st.columns(3)
start = col3.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col4.date_input("結束日期", value=s_max)
capital = col5.number_input("投入本金", 1000, 10000000, 100000)

# --- 3. 策略核心迴圈 ---
if st.button("啟動回測引擎 🚀"):
    # 讀取資料並對齊
    df_base = load_csv(base_id)
    df_lev = load_csv(lev_id)
    df = df_base.rename(columns={"Price": "Price_base"}).join(df_lev["Price"].rename("Price_lev"), how="inner")
    
    # 計算 SMA (訊號以原型為準)
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start:end].dropna(subset=["SMA"])

    # 狀態變數
    in_position = False
    entry_price_lev = 0.0      # 買進時槓桿 ETF 的成本
    trailing_low_base = df["Price_base"].iloc[0]  # 空手時追蹤原型的最低點
    trailing_high_lev = 0.0    # 持倉時追蹤槓桿的最高點
    
    sigs, pos = [0] * len(df), [0.0] * len(df)
    exit_reasons = [""] * len(df)

    for i in range(1, len(df)):
        p_base = df["Price_base"].iloc[i]
        p_lev = df["Price_lev"].iloc[i]
        sma = df["SMA"].iloc[i]
        
        if not in_position:
            # 追蹤「空手期」原型的最低點
            trailing_low_base = min(trailing_low_base, p_base)
            buy_trigger = trailing_low_base * (1 + buy_pct / 100)
            
            # [邏輯 1] 進場條件：Price > SMA 且 從低點反彈
            if p_base > sma and p_base >= buy_trigger:
                in_position = True
                entry_price_lev = p_lev
                trailing_high_lev = p_lev
                sigs[i] = 1
        else:
            # 追蹤「持倉期」槓桿的最高點
            trailing_high_lev = max(trailing_high_lev, p_lev)
            sell_trigger = trailing_high_lev * (1 - sell_pct / 100)
            
            # [邏輯 3] 強制停損：破 SMA
            if p_base < sma:
                in_position = False
                sigs[i] = -1
                exit_reasons[i] = "SMA 強制停損"
                trailing_low_base = p_base # 重置最低點追蹤
            
            # [邏輯 2] 絕對獲利賣出：高點回落 且 價格 > 成本
            elif p_lev <= sell_trigger and p_lev > entry_price_lev:
                in_position = False
                sigs[i] = -1
                exit_reasons[i] = "獲利入袋"
                trailing_low_base = p_base # 重置最低點追蹤

        pos[i] = 1.0 if in_position else 0.0

    df["Signal"], df["Position"] = sigs, pos

    # --- 4. 績效計算 ---
    equity = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity"] = equity
    df["Equity_BH"] = df["Price_lev"] / df["Price_lev"].iloc[0]
    
    # 指標
    y_len = (df.index[-1] - df.index[0]).days / 365
    cagr = (df["Equity"].iloc[-1])**(1/y_len) - 1
    mdd = 1 - (df["Equity"] / df["Equity"].cummax()).min()
    
    # --- 5. 圖表與結果展示 ---
    st.markdown("### 🏆 回測績效摘要")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末總資產", f"{df['Equity'].iloc[-1]*capital:,.0f} 元")
    k2.metric("年化報酬 (CAGR)", f"{cagr:.2%}")
    k3.metric("最大回撤 (MDD)", f"{mdd:.2%}", delta_color="inverse")
    k4.metric("交易次數", f"{(df['Signal']!=0).sum()} 次")

    # 
    fig = go.Figure()
    # 價格與 SMA
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="原型股價", line=dict(color="#64748B", width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="SMA 趨勢線", line=dict(color="#F59E0B", width=2)))
    
    # 買賣點
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", marker=dict(symbol="triangle-up", size=12, color="#10B981"), name="觸發買進"))
    fig.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", marker=dict(symbol="triangle-down", size=12, color="#EF4444"), name="觸發賣出"))

    fig.update_layout(height=600, template="plotly_white", title="策略執行軌跡 (原型訊號對照)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 資金曲線
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity"]-1, name="策略累積報酬", fill='tozeroy', line=dict(color="#10B981")))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name="槓桿 ETF 標的持有的報酬", line=dict(color="#94A3B8", dash="dash")))
    fig_eq.update_layout(height=400, template="plotly_white", title="資金曲線比較", yaxis=dict(tickformat=".0%"))
    st.plotly_chart(fig_eq, use_container_width=True)
