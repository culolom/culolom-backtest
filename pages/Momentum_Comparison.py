import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# ==========================================
# 1. 自動掃描資料夾內的 CSV
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
st.set_page_config(page_title="12M 滾動動能比較", layout="wide")
st.title("🚀 雙動能觀測站：12M 報酬與 200SMA 乖離")

csv_files = get_available_csvs()

with st.sidebar:
    st.header("⚙️ 參數設定")
    selected_assets = st.multiselect("選擇比較標的 (最多5種)", options=csv_files, default=csv_files[:3], max_selections=5)
    sma_period = st.number_input("均線週期 (SMA)", value=200)
    momentum_window = st.number_input("動能計算週期 (月)", value=12)

if not selected_assets:
    st.warning("👈 請先選擇資產。")
    st.stop()

# ==========================================
# 3. 核心邏輯：計算 12M 滾動報酬
# ==========================================
all_data = {}
for asset in selected_assets:
    df = load_data(asset)
    if not df.empty:
        # 計算 12 個月滾動報酬 (約 252 個交易日)
        # 我們使用 pct_change 並指定天數，這樣每個點都是「相較於一年前的報酬」
        days = momentum_window * 21 
        df['Rolling_12M_Ret'] = df['Price'].pct_change(periods=days) * 100
        
        # 計算 SMA 乖離率
        df['SMA'] = df['Price'].rolling(window=sma_period).mean()
        df['Bias'] = ((df['Price'] - df['SMA']) / df['SMA']) * 100
        all_data[asset] = df

# 處理日期選擇
all_dates = pd.concat([df.index.to_series() for df in all_data.values()])
max_date = all_dates.max().date()
min_date = all_dates.min().date()

date_range = st.date_input(
    "選擇圖表觀察區間",
    value=[max_date - dt.timedelta(days=365*2), max_date],
    min_value=min_date,
    max_value=max_date
)

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    
    # --- 圖表一：12個月滾動報酬 ---
    fig_mom = go.Figure()
    for name, df in all_data.items():
        # 過濾顯示範圍
        df_plot = df.loc[start_dt:end_dt]
        fig_mom.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Rolling_12M_Ret'], name=name))
    
    fig_mom.update_layout(
        title=f"1. 近 {momentum_window} 個月滾動報酬率 (Relative Momentum)",
        yaxis_title="報酬率 (%)",
        hovermode="x unified",
        template="plotly_white",
        height=500
    )
    fig_mom.add_hline(y=0, line_dash="dash", line_color="black") # 絕對動能分界線

    # --- 圖表二：SMA 乖離率 ---
    fig_bias = go.Figure()
    for name, df in all_data.items():
        df_plot = df.loc[start_dt:end_dt]
        fig_bias.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Bias'], name=f"{name} Bias"))
    
    fig_bias.update_layout(
        title=f"2. {sma_period}SMA 乖離率比較 (Trend Filter)",
        yaxis_title="乖離率 (%)",
        hovermode="x unified",
        template="plotly_white",
        height=500
    )
    fig_bias.add_hline(y=0, line_dash="dash", line_color="black")

    st.plotly_chart(fig_mom, use_container_width=True)
    st.plotly_chart(fig_bias, use_container_width=True)

    # --- 即時排名表格 ---
    st.subheader("🏆 當前動能排名 (最新數據)")
    rank_list = []
    for name, df in all_data.items():
        latest = df.iloc[-1]
        rank_list.append({
            "資產": name,
            f"最新 {momentum_window}M 報酬": f"{latest['Rolling_12M_Ret']:.2f}%",
            "最新乖離率": f"{latest['Bias']:.2f}%",
            "狀態": "📈 多頭" if latest['Bias'] > 0 else "📉 空頭"
        })
    
    # 根據報酬率排序
    rank_df = pd.DataFrame(rank_list).sort_values(f"最新 {momentum_window}M 報酬", ascending=False)
    st.table(rank_df)
