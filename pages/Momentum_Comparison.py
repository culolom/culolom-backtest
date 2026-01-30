import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# ==========================================
# 1. 自動掃描與資料處理
# ==========================================
DATA_DIR = Path("data")

def get_available_csvs():
    if not DATA_DIR.exists(): return []
    return [f.stem for f in DATA_DIR.glob("*.csv")]

@st.cache_data
def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except:
        return pd.DataFrame()

# ==========================================
# 2. UI 介面
# ==========================================
st.set_page_config(page_title="雙動能全方位觀測", layout="wide")
st.title("🐹 倉鼠量化戰情室：動能與累積報酬分析")

csv_files = get_available_csvs()

with st.sidebar:
    st.header("⚙️ 策略參數")
    selected_assets = st.multiselect("選擇資產", options=csv_files, default=csv_files[:3], max_selections=5)
    sma_period = st.number_input("SMA 均線週期", value=200)
    mom_months = st.number_input("動能計算週期 (月)", value=12)

if not selected_assets:
    st.warning("👈 請在左側選單選擇要分析的標的。")
    st.stop()

# ==========================================
# 3. 核心數據處理
# ==========================================
all_data = {}
for asset in selected_assets:
    df = load_data(asset)
    if not df.empty:
        # 計算滾動動能 (每個點相較於一年前的漲幅)
        days = mom_months * 21 
        df['Rolling_Mom'] = df['Price'].pct_change(periods=days) * 100
        
        # 計算 200SMA 乖離
        df['SMA'] = df['Price'].rolling(window=sma_period).mean()
        df['Bias'] = ((df['Price'] - df['SMA']) / df['SMA']) * 100
        all_data[asset] = df

# 日期範圍選擇
all_dates = pd.concat([df.index.to_series() for df in all_data.values()])
max_date = all_dates.max().date()
min_date = all_dates.min().date()

date_range = st.date_input(
    "選擇觀察時間區間",
    value=[max_date - dt.timedelta(days=365*2), max_date],
    min_value=min_date,
    max_value=max_date
)

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    
    # ------------------------------------------
    # 圖表一：累積報酬率 (從區間起點算起)
    # ------------------------------------------
    fig_cum = go.Figure()
    for name, df in all_data.items():
        df_plot = df.loc[start_dt:end_dt].copy()
        if df_plot.empty: continue
        # 以區間第一天為基點 0
        cum_ret = (df_plot['Price'] / df_plot['Price'].iloc[0] - 1) * 100
        fig_cum.add_trace(go.Scatter(x=df_plot.index, y=cum_ret, name=name))
    
    fig_cum.update_layout(title="1. 累積報酬率比較 (%) - 資金成長曲線", yaxis_title="報酬率 (%)", hovermode="x unified", template="plotly_white")

    # ------------------------------------------
    # 圖表二：滾動 12M 報酬 (相對動能)
    # ------------------------------------------
    fig_mom = go.Figure()
    for name, df in all_data.items():
        df_plot = df.loc[start_dt:end_dt]
        fig_mom.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Rolling_Mom'], name=name))
    
    fig_mom.update_layout(title=f"2. 近 {mom_months}M 滾動報酬 (%) - 相對動能觀察", yaxis_title="報酬率 (%)", hovermode="x unified", template="plotly_white")
    fig_mom.add_hline(y=0, line_dash="dash", line_color="black")

    # ------------------------------------------
    # 圖表三：SMA 乖離率 (趨勢過濾)
    # ------------------------------------------
    fig_bias = go.Figure()
    for name, df in all_data.items():
        df_plot = df.loc[start_dt:end_dt]
        fig_bias.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Bias'], name=f"{name} Bias"))
    
    fig_bias.update_layout(title=f"3. {sma_period}SMA 乖離率 (%) - 趨勢過濾器", yaxis_title="乖離率 (%)", hovermode="x unified", template="plotly_white")
    fig_bias.add_hline(y=0, line_dash="dash", line_color="black")

    # 繪製所有圖表
    st.plotly_chart(fig_cum, use_container_width=True)
    st.plotly_chart(fig_mom, use_container_width=True)
    st.plotly_chart(fig_bias, use_container_width=True)

    # --- 戰情簡報表格 ---
    st.divider()
    st.subheader("📊 當前戰情摘要")
    summary = []
    for name, df in all_data.items():
        last = df.iloc[-1]
        summary.append({
            "標的": name,
            "最新價格": round(last['Price'], 2),
            f"{mom_months}M 動能": f"{last['Rolling_Mom']:.2f}%",
            "SMA 乖離": f"{last['Bias']:.2f}%",
            "建議": "✅ 多頭持有" if last['Bias'] > 0 and last['Rolling_Mom'] > 0 else "⚠️ 觀望/空頭"
        })
    st.dataframe(pd.DataFrame(summary).sort_values(f"{mom_months}M 動能", ascending=False), hide_index=True)
