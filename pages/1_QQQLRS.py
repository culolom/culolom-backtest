import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from pathlib import Path

# --- 1. 基礎與頁面設定 ---
st.set_page_config(page_title="台美股動能旋轉系統 - 時間自定義版", page_icon="📅", layout="wide")

# 🔒 驗證 (請確保 auth.py 存在)
try:
    import auth
    if not auth.check_password():
        st.stop()
except:
    pass

# --- 2. 標的配置 ---
ETF_CONFIG = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW"}
}

DATA_DIR = Path("data")
if not DATA_DIR.exists():
    DATA_DIR.mkdir()

# --- 3. 工具函式：取得資料與補齊 ---
def get_data(symbol):
    file_path = DATA_DIR / f"{symbol}.csv"
    if not file_path.exists():
        with st.status(f"📥 正在下載: {symbol}...", expanded=False):
            df = yf.download(symbol, period="max")
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.to_csv(file_path)
    
    df = pd.read_csv(file_path, parse_dates=["Date"], index_col="Date")
    return df.sort_index()[["Close"]].rename(columns={"Close": "Price"})

# --- 4. 預載資料以取得時間範圍 ---
# 這裡先快速掃描資料，決定側邊欄日曆的範圍
all_available_dates = []
for key in ETF_CONFIG:
    f_path = DATA_DIR / f"{ETF_CONFIG[key]['base']}.csv"
    if f_path.exists():
        temp_df = pd.read_csv(f_path, parse_dates=["Date"], index_col="Date")
        all_available_dates.append(temp_df.index.min())
        all_available_dates.append(temp_df.index.max())

# 設定預設日期 (如果沒資料就用今天)
abs_min_date = min(all_available_dates).date() if all_available_dates else dt.date(2010, 1, 1)
abs_max_date = max(all_available_dates).date() if all_available_dates else dt.date.today()

# --- 5. UI 介面 ---
st.title("📊 三標動態 LRS 動能旋轉策略 (自定義時間)")

with st.sidebar:
    st.header("⚙️ 參數設定")
    selected_pool = st.multiselect("選擇投資池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys()))
    
    # 📅 新增時間選擇功能
    st.subheader("📅 回測時間選擇")
    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("開始日期", value=abs_min_date, min_value=abs_min_date, max_value=abs_max_date)
    with col_end:
        end_date = st.date_input("結束日期", value=abs_max_date, min_value=abs_min_date, max_value=abs_max_date)

    capital = st.number_input("本金 (元)", value=100000, step=10000)
    lookback = st.slider("動能參考天數 (12個月約252天)", 100, 300, 252)
    ma_val = st.number_input("均線天數", value=200)

# --- 6. 執行回測 ---
if st.button("開始回測 🚀"):
    if start_date >= end_date:
        st.error("❌ 錯誤：開始日期必須早於結束日期。")
        st.stop()

    all_dfs = {}
    for key in selected_pool:
        cfg = ETF_CONFIG[key]
        base_df = get_data(cfg["base"])
        lev_df = get_data(cfg["lev"])
        
        # 計算指標
        base_df["MA"] = base_df["Price"].rolling(ma_val).mean()
        base_df["Mom"] = base_df["Price"].pct_change(lookback)
        base_df["Above"] = base_df["Price"] > base_df["MA"]
        base_df["Lev_Ret"] = lev_df["Price"].pct_change().fillna(0)
        
        # 🟢 在這裡根據使用者的選擇進行時間過濾
        filtered_df = base_df.loc[str(start_date):str(end_date)]
        all_dfs[key] = filtered_df

    # 取所有標的時間的交集
    common_idx = None
    for key in all_dfs:
        if common_idx is None: common_idx = all_dfs[key].index
        else: common_idx = common_idx.intersection(all_dfs[key].index)
    
    if len(common_idx) < 10:
        st.warning("⚠️ 所選時間範圍內的資料點太少，回測可能不準確。")

    # 模擬邏輯
    res_list = []
    current_equity = 1.0
    for date in common_idx:
        candidates = []
        for key in selected_pool:
            # 確保資料在均線上且動能不是 NaN
            if all_dfs[key].loc[date, "Above"] and not pd.isna(all_dfs[key].loc[date, "Mom"]):
                candidates.append((key, all_dfs[key].loc[date, "Mom"]))
        
        if not candidates:
            choice = "Cash (空手)"
            daily_ret = 0.0
        else:
            choice = max(candidates, key=lambda x: x[1])[0]
            daily_ret = all_dfs[choice].loc[date, "Lev_Ret"]
            
        current_equity *= (1 + daily_ret)
        res_list.append({"Date": date, "Holding": choice, "Equity": current_equity})

    df_res = pd.DataFrame(res_list).set_index("Date")

    # --- 7. 顯示統計與圖表 ---
    final_asset = capital * df_res["Equity"].iloc[-1]
    total_ret = df_res["Equity"].iloc[-1] - 1
    mdd = (df_res["Equity"] / df_res["Equity"].cummax() - 1).min()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("期末資產", f"${final_asset:,.0f}")
    c2.metric("總報酬率", f"{total_ret:.2%}")
    c3.metric("最大回撤 (MDD)", f"{mdd:.2%}", delta_color="inverse")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="gold", width=3)))
    
    for key in selected_pool:
        bench_p = all_dfs[key].loc[common_idx, "Price"]
        bench_eq = (bench_p / bench_p.iloc[0]) * capital
        fig.add_trace(go.Scatter(x=common_idx, y=bench_eq, name=f"持有 {key}", opacity=0.3))
        
    fig.update_layout(title=f"回測區間：{start_date} 至 {end_date}", template="plotly_white", height=500)
    st.plotly_chart(fig, use_container_width=True)
