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
    """自動抓取 data 資料夾下所有的 CSV 檔案名稱"""
    if not DATA_DIR.exists():
        return []
    # 抓取檔名並去掉 .csv 副檔名
    return [f.stem for f in DATA_DIR.glob("*.csv")]

@st.cache_data
def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        # 優先使用 Adj Close (還原股價)，若無則用 Close
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except Exception as e:
        st.error(f"讀取 {symbol} 出錯: {e}")
        return pd.DataFrame()

# ==========================================
# 2. UI 介面佈局
# ==========================================
st.set_page_config(page_title="資產動能自選比較", layout="wide")
st.title("⚖️ 資產動能與 200SMA 乖離率對照")

# 取得目前資料夾所有的標的
csv_files = get_available_csvs()

if not csv_files:
    st.error("❌ 在 data 資料夾中找不到任何 CSV 檔案，請確認檔案路徑。")
    st.stop()

with st.sidebar:
    st.markdown("### 🛠️ 控制面板")
    # 讓使用者從資料夾檔案中自選
    selected_assets = st.multiselect(
        "選擇要比較的標的 (建議 1~5 個)", 
        options=csv_files,
        default=csv_files[:2] if len(csv_files) >= 2 else csv_files
    )
    
    sma_period = st.number_input("SMA 均線天數", value=200, step=10)
    st.info("💡 雙動能小提醒：200SMA 常被視為牛熊分界線。")

if not selected_assets:
    st.warning("👈 請在左側選單選擇至少一個 CSV 檔案。")
    st.stop()

# ==========================================
# 3. 核心數據處理
# ==========================================
all_data = {}
for asset in selected_assets:
    df = load_data(asset)
    if not df.empty:
        all_data[asset] = df

# 找出所有標的共有的日期範圍
all_dates = pd.concat([df.index.to_series() for df in all_data.values()])
min_date, max_date = all_dates.min(), all_dates.max()

date_range = st.date_input(
    "選擇觀察區間",
    value=[max_date.date() - dt.timedelta(days=365), max_date.date()],
    min_value=min_date.date(),
    max_value=max_date.date()
)

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    
    fig_ret = go.Figure()
    fig_bias = go.Figure()

    for name, df in all_data.items():
        # --- 處理 200SMA (需要完整歷史資料計算，不能只切區間) ---
        df_calc = df.copy()
        df_calc['SMA'] = df_calc['Price'].rolling(window=sma_period).mean()
        df_calc['Bias'] = ((df_calc['Price'] - df_calc['SMA']) / df_calc['SMA']) * 100
        
        # --- 切分使用者選擇的區間 ---
        mask = (df_calc.index >= start_dt) & (df_calc.index <= end_dt)
        df_plot = df_calc.loc[mask]
        
        if df_plot.empty: continue

        # --- 計算累積報酬率 (%) ---
        # 以選定區間的第一天價格為 100% 基準
        cum_return = (df_plot['Price'] / df_plot['Price'].iloc[0] - 1) * 100
        
        # 繪製圖表 1: 報酬率
        fig_ret.add_trace(go.Scatter(x=df_plot.index, y=cum_return, name=name))
        
        # 繪製圖表 2: 乖離率
        fig_bias.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Bias'], name=f"{name} {sma_period}SMA Bias"))

    # 圖表修飾
    fig_ret.update_layout(
        title="1. 累積報酬率比較 (%)",
        hovermode="x unified",
        template="plotly_white",
        yaxis_title="報酬率 %",
        height=450
    )
    
    fig_bias.update_layout(
        title=f"2. {sma_period}SMA 乖離率比較 (%)",
        hovermode="x unified",
        template="plotly_white",
        yaxis_title="乖離率 %",
        height=450
    )
    fig_bias.add_hline(y=0, line_dash="dash", line_color="black")

    # 渲染圖表
    st.plotly_chart(fig_ret, use_container_width=True)
    st.plotly_chart(fig_bias, use_container_width=True)

    # --- 數據總覽表格 ---
    st.divider()
    st.subheader("📝 區間績效摘要")
    summary_list = []
    for name, df in all_data.items():
        mask = (df.index >= start_dt) & (df.index <= end_dt)
        sub = df.loc[mask]
        if not sub.empty:
            total_ret = (sub['Price'].iloc[-1] / sub['Price'].iloc[0] - 1) * 100
            # 計算最新乖離率
            full_df = all_data[name].copy()
            full_df['SMA'] = full_df['Price'].rolling(window=sma_period).mean()
            last_bias = ((full_df['Price'].iloc[-1] - full_df['SMA'].iloc[-1]) / full_df['SMA'].iloc[-1]) * 100
            
            summary_list.append({
                "標的": name,
                "區間報酬率": f"{total_ret:.2f}%",
                f"目前 {sma_period}SMA 乖離": f"{last_bias:.2f}%"
            })
    
    st.table(pd.DataFrame(summary_list))
