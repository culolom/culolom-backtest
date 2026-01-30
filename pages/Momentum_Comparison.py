import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# ==========================================
# 1. 基礎設定與資料自動掃描
# ==========================================
# 根據你的專案架構，資料存放於 data 資料夾
DATA_DIR = Path("data") 

def get_available_csvs():
    """自動抓取 data 資料夾下所有的 CSV 檔案"""
    if not DATA_DIR.exists():
        return []
    return [f.stem for f in DATA_DIR.glob("*.csv")]

@st.cache_data
def load_data(symbol: str) -> pd.DataFrame:
    """讀取 CSV 並識別價格欄位"""
    path = DATA_DIR / f"{symbol}.csv"
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        # 優先使用還原股價 Adj Close
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except Exception as e:
        st.error(f"讀取 {symbol} 出錯: {e}")
        return pd.DataFrame()

# ==========================================
# 2. UI 介面佈局 (側邊欄參數)
# ==========================================
st.set_page_config(page_title="倉鼠量化戰情室", layout="wide")
st.title("📈 倉鼠量化戰情室：雙區段動能回測系統")

csv_files = get_available_csvs()

if not csv_files:
    st.error("❌ 在 data 資料夾中找不到任何 CSV 檔案，請確認路徑。")
    st.stop()

with st.sidebar:
    st.header("⚙️ 全域參數設定")
    selected_assets = st.multiselect(
        "選擇分析標的 (最多5種)", 
        options=csv_files, 
        default=csv_files[:3] if len(csv_files) >= 3 else csv_files,
        max_selections=5
    )
    
    st.divider()
    sma_period = st.number_input("均線週期 (SMA)", value=200, step=10)
    mom_months = st.number_input("動能計算週期 (月)", value=12, step=1)
    st.caption(f"提示：將計算近 {mom_months} 個月的滾動報酬。")

if not selected_assets:
    st.warning("👈 請在左側選單選擇標的以開始分析。")
    st.stop()

# ==========================================
# 3. 核心數據處理邏輯
# ==========================================
all_data = {}
for asset in selected_assets:
    df = load_data(asset)
    if not df.empty:
        # 計算 12M 滾動報酬 (Rolling Return)
        # 每個時間點的數值 = (當前價格 / 12個月前價格) - 1
        days = mom_months * 21 
        df['Rolling_Mom'] = df['Price'].pct_change(periods=days) * 100
        
        # 計算 SMA 乖離率 (Bias)
        df['SMA'] = df['Price'].rolling(window=sma_period).mean()
        df['Bias'] = ((df['Price'] - df['SMA']) / df['SMA']) * 100
        all_data[asset] = df

# 獲取全局日期範圍以供選擇器使用
all_dates = pd.concat([df.index.to_series() for df in all_data.values()])
max_date = all_dates.max().date()
min_date = all_dates.min().date()

# ==========================================
# 4. 兩階段日期選擇介面
# ==========================================
col_obs, col_inv = st.columns(2)

with col_obs:
    st.subheader("🔍 第一區段：動能觀察期")
    st.write("用於比對各標的的相對強度與乖離狀態。")
    obs_range = st.date_input(
        "觀察時間區間",
        value=[max_date - dt.timedelta(days=365*2), max_date - dt.timedelta(days=365)],
        min_value=min_date, max_value=max_date, key="obs_date"
    )

with col_inv:
    st.subheader("💰 第二區段：投資持有期")
    st.write("設定全倉買入日，觀察後續資金成長。")
    invest_start = st.date_input(
        "買入日期 (Investment Start)", 
        value=max_date - dt.timedelta(days=365),
        min_value=min_date, max_value=max_date, key="invest_date"
    )

# ==========================================
# 5. 圖表繪製：觀察期 (連動上下圖)
# ==========================================
st.divider()
st.markdown("### 📋 觀察期深度分析")

if len(obs_range) == 2:
    obs_s, obs_e = pd.to_datetime(obs_range[0]), pd.to_datetime(obs_range[1])
    
    # 建立上下排列的子圖，共用 X 軸
    fig_obs = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.07,
        subplot_titles=(f"1. 近 {mom_months}M 滾動報酬率 (%)", f"2. {sma_period}SMA 乖離率 (%)"),
        row_heights=[0.5, 0.5]
    )

    for name, df in all_data.items():
        d_sub = df.loc[obs_s:obs_e]
        if d_sub.empty: continue
        
        # 上圖：動能
        fig_obs.add_trace(
            go.Scatter(x=d_sub.index, y=d_sub['Rolling_Mom'], name=name, legendgroup=name),
            row=1, col=1
        )
        # 下圖：乖離率 (不重疊顯示 legend)
        fig_obs.add_trace(
            go.Scatter(x=d_sub.index, y=d_sub['Bias'], name=f"{name} Bias", legendgroup=name, showlegend=False),
            row=2, col=1
        )

    # 加入零軸線
    fig_obs.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)
    fig_obs.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)

    fig_obs.update_layout(height=700, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_obs, use_container_width=True)

# ==========================================
# 6. 圖表繪製：投資期 (資金曲線)
# ==========================================
st.divider()
st.markdown(f"### 🚀 持有期表現 (起始日: {invest_start})")

fig_inv = go.Figure()
inv_results = []

for name, df in all_data.items():
    # 截取投資起始日之後的資料
    d_inv = df.loc[pd.to_datetime(invest_start):]
    if d_inv.empty: continue
    
    # 資金曲線計算：以起始日價格為 100% 基準
    # 公式：(當前價格 / 初始價格 - 1) * 100
    capital_curve = (d_inv['Price'] / d_inv['Price'].iloc[0] - 1) * 100
    
    fig_inv.add_trace(go.Scatter(x=d_inv.index, y=capital_curve, name=f"{name} 成長"))
    
    final_ret = capital_curve.iloc[-1]
    inv_results.append({"資產標的": name, "持有期總報酬": f"{final_ret:.2f}%"})

fig_inv.update_layout(
    title="3. 買入後資金成長曲線 (%)", 
    yaxis_title="報酬率 (%)",
    hovermode="x unified", 
    template="plotly_white", 
    height=500
)
st.plotly_chart(fig_inv, use_container_width=True)

# 顯示最終戰績表
if inv_results:
    res_df = pd.DataFrame(inv_results).sort_values("持有期總報酬", ascending=False)
    st.table(res_df)
