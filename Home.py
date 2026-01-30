import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# ==========================================
# 1. 基礎設定與資料讀取函數
# ==========================================
DATA_DIR = Path("data")

ASSET_OPTIONS = {
    "0050.TW (台灣50)": "0050.TW",
    "00631L.TW (台指2X)": "00631L.TW",
    "QQQ (納斯達克100)": "QQQ", 
    "SPY (標普500)": "SPY", 
    "NVDA (輝達)": "NVDA"
}

def load_csv(symbol: str) -> pd.DataFrame:
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv"]
    path = next((DATA_DIR / c for c in candidates if (DATA_DIR / c).exists()), None)
    if not path:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except:
        return pd.DataFrame()

# ==========================================
# 2. UI 介面佈局
# ==========================================
st.title("📈 動能衰竭研究室")

with st.sidebar:
    st.markdown("### ⚙️ 參數設定")
    lookback_months = st.slider("動能計算週期 (月)", 1, 24, 12)
    smooth_days = st.slider("動能平滑天數", 5, 60, 20)

col_target, col_date = st.columns([1, 2])

with col_target:
    selected_label = st.selectbox("選擇研究標的", list(ASSET_OPTIONS.keys()))
    sym = ASSET_OPTIONS[selected_label]

# --- 關鍵修正：先定義 df_raw，確保後面檢查時它已經存在 ---
df_raw = load_csv(sym)

if df_raw.empty:
    st.error(f"❌ 找不到 {sym}.csv 的資料，請確認 data 資料夾是否有該檔案。")
    st.stop()

# 取得日期區間
s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()
with col_date:
    date_range = st.date_input("選擇觀察區間", 
                               value=[max(s_min, s_max - dt.timedelta(days=365*3)), s_max], 
                               min_value=s_min, max_value=s_max)

# ==========================================
# 3. 核心計算邏輯 (動能與衰竭偵測)
# ==========================================
if len(date_range) == 2:
    start_date, end_date = date_range
    df = df_raw.loc[str(start_date):str(end_date)].copy()
    
    # 計算 12M 動能 (ROC)
    lookback_days = lookback_months * 21
    df['Momentum'] = df['Price'].pct_change(lookback_days)
    
    # 計算平滑動能 (紅線)
    df['Mom_Smooth'] = df['Momentum'].rolling(window=smooth_days).mean()
    
    # 計算斜率 (判斷是否衰竭)
    df['Mom_Slope'] = df['Mom_Smooth'].diff(5)
    df['Is_Exhaustion'] = (df['Mom_Smooth'] > 0) & (df['Mom_Slope'] < 0)

    # ==========================================
    # 4. 繪製圖表 (價格與動能對照)
    # ==========================================
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.08, 
                        subplot_titles=(f"{selected_label} 價格走勢 (底色為動能衰竭區)", "動能強度 (ROC)"),
                        row_heights=[0.6, 0.4])

    # 價格線
    fig.add_trace(go.Scatter(x=df.index, y=df['Price'], name="價格", line=dict(color="#1f77b4")), row=1, col=1)

    # 動能線
    fig.add_trace(go.Scatter(x=df.index, y=df['Mom_Smooth'], name="平滑動能", line=dict(color="#e41a1c", width=3)), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)

    # 標註衰竭區間 (橘色背景)
    for i in range(1, len(df)):
        if df['Is_Exhaustion'].iloc[i]:
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor="orange", opacity=0.1, line_width=0, row=1, col=1)

    fig.update_layout(height=700, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
