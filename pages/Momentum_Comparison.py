import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# ==========================================
# 1. 基礎設定與資料讀取
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
# 2. UI 介面設定
# ==========================================
st.set_page_config(page_title="雙區段量化分析", layout="wide")
st.title("📈 量化動能研究室：觀察與回測分離系統")

csv_files = get_available_csvs()

with st.sidebar:
    st.header("⚙️ 全域參數")
    selected_assets = st.multiselect("選擇分析標的", options=csv_files, default=csv_files[:3], max_selections=5)
    sma_period = st.number_input("均線週期 (SMA)", value=200)
    mom_months = st.number_input("動能計算週期 (月)", value=12)

if not selected_assets:
    st.warning("👈 請在左側選單選擇標的。")
    st.stop()

# ==========================================
# 3. 資料處理
# ==========================================
all_data = {}
for asset in selected_assets:
    df = load_data(asset)
    if not df.empty:
        # 計算 12M 滾動報酬
        days = mom_months * 21 
        df['Rolling_Mom'] = df['Price'].pct_change(periods=days) * 100
        # 計算 SMA 乖離
        df['SMA'] = df['Price'].rolling(window=sma_period).mean()
        df['Bias'] = ((df['Price'] - df['SMA']) / df['SMA']) * 100
        all_data[asset] = df

# 獲取全局日期範圍
all_dates = pd.concat([df.index.to_series() for df in all_data.values()])
max_date = all_dates.max().date()
min_date = all_dates.min().date()

# ==========================================
# 4. 兩階段日期選擇
# ==========================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔍 第一區段：動能觀察期")
    st.caption("用於判斷誰的動能最強、是否過熱")
    obs_range = st.date_input(
        "選擇觀察時間",
        value=[max_date - dt.timedelta(days=365*2), max_date - dt.timedelta(days=365)],
        min_value=min_date, max_value=max_date, key="obs_date"
    )

with col2:
    st.subheader("💰 第二區段：投資持有期")
    st.caption("根據觀察結果，從此日期開始計算資金曲線")
    invest_start = st.date_input(
        "選擇買入日期 (Start Date)", 
        value=max_date - dt.timedelta(days=365),
        min_value=min_date, max_value=max_date, key="invest_date"
    )

# ==========================================
# 5. 繪製圖表
# ==========================================

if len(obs_range) == 2:
    obs_start, obs_end = pd.to_datetime(obs_range[0]), pd.to_datetime(obs_range[1])
    
    # --- 圖表 1 & 2：觀察期數據 ---
    st.divider()
    st.markdown("### 📋 觀察期分析 (第一區段)")
    
    fig_mom = go.Figure()
    fig_bias = go.Figure()
    
    for name, df in all_data.items():
        d_obs = df.loc[obs_start:obs_end]
        fig_mom.add_trace(go.Scatter(x=d_obs.index, y=d_obs['Rolling_Mom'], name=name))
        fig_bias.add_trace(go.Scatter(x=d_obs.index, y=d_obs['Bias'], name=f"{name} Bias"))

    fig_mom.update_layout(title=f"1. 滾動 {mom_months}M 報酬率 (%)", hovermode="x unified", template="plotly_white", height=400)
    fig_mom.add_hline(y=0, line_dash="dash")
    
    fig_bias.update_layout(title=f"2. {sma_period}SMA 乖離率 (%)", hovermode="x unified", template="plotly_white", height=400)
    fig_bias.add_hline(y=0, line_dash="dash")

    c1, c2 = st.columns(2)
    c1.plotly_chart(fig_mom, use_container_width=True)
    c2.plotly_chart(fig_bias, use_container_width=True)

# --- 圖表 3：投資持有期 (資金曲線) ---
st.divider()
st.markdown(f"### 📈 投資持有期分析 (從 {invest_start} 開始)")

fig_cum = go.Figure()
summary_data = []

for name, df in all_data.items():
    # 找尋最接近買入日期的實際交易日
    d_invest = df.loc[pd.to_datetime(invest_start):]
    if d_invest.empty: continue
    
    # 以投資起始日為基點 0 (100% 資金)
    # 計算公式：(當前價格 / 買入日價格 - 1) * 100
    capital_curve = (d_invest['Price'] / d_invest['Price'].iloc[0] - 1) * 100
    fig_cum.add_trace(go.Scatter(x=d_invest.index, y=capital_curve, name=f"{name} 成長"))
    
    total_return = capital_curve.iloc[-1]
    summary_data.append({"標的": name, "投資期總報酬": f"{total_return:.2f}%"})

fig_cum.update_layout(
    title="3. 買入後資金成長曲線 (%)", 
    yaxis_title="報酬率 (%)",
    hovermode="x unified", 
    template="plotly_white", 
    height=500
)
st.plotly_chart(fig_cum, use_container_width=True)

# 顯示最後結果
st.table(pd.DataFrame(summary_data).sort_values("投資期總報酬", ascending=False))
