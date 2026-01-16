###############################################################
# app.py — 動能強弱與衰竭研究系統 (Momentum Strategy Lab)
# 核心邏輯：追蹤 12 個月報酬率 (ROC) 與價格之關係
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ==========================================
# 頁面設定
# ==========================================
st.set_page_config(page_title="動能衰竭研究室", page_icon="📈", layout="wide")

# ==========================================
# 🛑 Sidebar 區域
# ==========================================
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### ⚙️ 動能參數設定")
    lookback_months = st.slider("動能計算週期 (月)", 1, 24, 12, help="通常使用 12 個月來衡量長期動能")
    smooth_days = st.slider("動能平滑天數", 5, 60, 20, help="使用移動平均線平滑動能，更易看出趨勢")
    st.divider()
    st.info("💡 邏輯提醒：\n當價格創新高，但紅色的動能平滑線開始掉頭向下，即為動能衰竭訊號。")

# ==========================================
# 資料讀取功能
# ==========================================
DATA_DIR = Path("data")

ASSET_OPTIONS = {
    "QQQ (納斯達克100)": "QQQ", 
    "SPY (標普500)": "SPY", 
    "SOXX (半導體ETF)": "SOXX",
    "VT (全球股市)": "VT", 
    "0050.TW (台灣50)": "0050.TW",
    "00631L.TW (台指2X)": "00631L.TW",
    "NVDA (輝達)": "NVDA",
    "TSLA (特斯拉)": "TSLA"
}

def load_csv(symbol: str) -> pd.DataFrame:
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv"]
    path = next((DATA_DIR / c for c in candidates if (DATA_DIR / c).exists()), None)
    if not path: return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except: return pd.DataFrame()

# ==========================================
# 主頁面 UI
# ==========================================
st.markdown("<h1 style='margin-bottom:0.5em;'>📈 動能強度與價格走勢比較</h1>", unsafe_allow_html=True)

col_target, col_date = st.columns([1, 2])
with col_target:
    selected_label = st.selectbox("選擇研究標的", list(ASSET_OPTIONS.keys()))
    sym = ASSET_OPTIONS[selected_label]

df_raw = load_csv(sym)

if df_raw.empty:
    st.error(f"❌ 找不到 {sym}.csv 的資料，請確認 data 資料夾。")
    st.stop()

# 日期篩選
s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()
with col_date:
    date_range = st.date_input("選擇觀察區間", value=[max(s_min, s_max - dt.timedelta(days=365*3)), s_max], min_value=s_min, max_value=s_max)

if len(date_range) == 2:
    start_date, end_date = date_range
    df = df_raw.loc[str(start_date):str(end_date)].copy()
else:
    st.stop()

# ==========================================
# 核心計算邏輯
# ==========================================
# 1. 計算動能 (ROC)
lookback_days = lookback_months * 21
df['Momentum'] = df['Price'].pct_change(lookback_days)

# 2. 平滑動能
df['Mom_Smooth'] = df['Momentum'].rolling(window=smooth_days).mean()

# 3. 計算加速度 (Slope)
df['Mom_Slope'] = df['Mom_Smooth'].diff()

# ==========================================
# 視覺化圖表
# ==========================================
# 建立上下子圖：上圖價格，下圖動能
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.05, 
                    subplot_titles=(f"{selected_label} 價格走勢", f"{lookback_months}個月 動能強度 (ROC)"),
                    row_heights=[0.6, 0.4])

# --- 上圖：價格 ---
fig.add_trace(go.Scatter(x=df.index, y=df['Price'], name="收盤價", line=dict(color="#1f77b4", width=2)), row=1, col=1)

# --- 下圖：動能 ---
# 原始動能 (淡色線)
fig.add_trace(go.Scatter(x=df.index, y=df['Momentum'], name="原始動能", 
                         line=dict(color="rgba(150,150,150,0.3)", width=1)), row=2, col=1)

# 平滑動能 (粗紅線)
fig.add_trace(go.Scatter(x=df.index, y=df['Mom_Smooth'], name=f"{smooth_days}日平滑動能", 
                         line=dict(color="#e41a1c", width=3)), row=2, col=1)

# 零軸線
fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)

# 佈局美化
fig.update_layout(height=700, template="plotly_white", hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
fig.update_yaxes(title_text="價格", row=1, col=1)
fig.update_yaxes(title_text="報酬率", tickformat=".0%", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 動能狀態儀表板 (當前數值)
# ==========================================
curr_price = df['Price'].iloc[-1]
curr_mom = df['Mom_Smooth'].iloc[-1]
prev_mom = df['Mom_Smooth'].iloc[-5] # 比較一週前
slope = curr_mom - prev_mom

st.markdown("---")
c1, c2, c3 = st.columns(3)

with c1:
    st.metric("當前價格", f"${curr_price:,.2f}")

with c2:
    st.metric(f"當前 {lookback_months}M 動能", f"{curr_mom:.2%}", 
              delta=f"{slope:.2%}", delta_color="normal")

with c3:
    if curr_mom > 0 and slope > 0:
        status_text = "🚀 動能強勁：價格與動能同步上升"
        status_color = "green"
    elif curr_mom > 0 and slope < 0:
        status_text = "⚠️ 動能衰竭：注意價格創高但力道減弱"
        status_color = "orange"
    elif curr_mom < 0 and slope < 0:
        status_text = "📉 弱勢行情：動能持續下滑"
        status_color = "red"
    else:
        status_text = "🔄 轉折打底：負向動能開始收斂"
        status_color = "blue"
    
    st.markdown(f"**目前診斷狀態：**\n<span style='color:{status_color}; font-size:1.2em; font-weight:bold;'>{status_text}</span>", unsafe_allow_html=True)

# ==========================================
# 數據下載
# ==========================================
st.markdown("### 📥 下載分析數據")
export_df = df[['Price', 'Momentum', 'Mom_Smooth', 'Mom_Slope']].copy()
csv = export_df.to_csv().encode('utf-8-sig')
st.download_button("下載動能數據 (CSV)", data=csv, file_name=f"Moment_Analysis_{sym}.csv", mime='text/csv')
