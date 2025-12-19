import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面配置與樣式 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 統合版", page_icon="🐹", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .kpi-card {
            background-color: #ffffff;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            border: 1px solid #eee;
            text-align: center;
        }
        .kpi-label { font-size: 0.9rem; color: #666; margin-bottom: 5px; }
        .kpi-value { font-size: 1.8rem; font-weight: 700; color: #1f1f1f; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 標的配置 (已修正語法錯誤) ---
ETF_CONFIG = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW"},
    "黃金 (00635U / 00708L)": {"base": "00635U.TW", "lev": "00708L.TW"}
}

DATA_DIR = Path("data")

# --- 3. 工具函式 ---
def load_csv_standard(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    # 確保欄位名稱統一
    if "Close" in df.columns and "Price" not in df.columns:
        df["Price"] = df["Close"]
    return df.sort_index()[["Price"]]

def calc_metrics_standard(series):
    # 使用與單標的程式一致的指標算法
    final_equity = series.iloc[-1]
    total_ret = final_equity - 1
    mdd = 1 - (series / series.cummax()).min()
    return final_equity, total_ret, mdd

# --- 4. Sidebar 參數設定 ---
# 🔒 驗證守門員 (若無 auth.py 會跳過)
try:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import auth
    if not auth.check_password():
        st.stop()
except:
    pass

with st.sidebar:
    st.header("⚙️ 策略參數")
    selected_keys = st.multiselect("投資組合池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys()))
    
    st.subheader("📅 回測時間範圍")
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    
    capital = st.number_input("投入本金 (元)", value=100000, step=10000)
    ma_window = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("動能參考天數 (12M)", 100, 300, 252)

# --- 5. 主程式回測邏輯 ---
st.title("🐹 三標動態 LRS 旋轉策略 (統合修正版)")
st.info("策略邏輯：收盤 > 200MA 准許買入；若多標的同時達標，選擇【12個月報酬最高者】持有其正2。全破則空手。")

if st.button("開始精確回測 🚀"):
    all_data = {}
    # 為了計算 MA，需要包含足夠的歷史資料
    for key in selected_keys:
        cfg = ETF_CONFIG[key]
        df_b = load_csv_standard(cfg["base"])
        df_l = load_csv_standard(cfg["lev"])
        
        if df_b.empty or df_l.empty:
            st.error(f"資料缺失：{key}")
            st.stop()
            
        # 計算 200MA 與 12M 動能
        df_b["MA"] = df_b["Price"].rolling(ma_window).mean()
        df_b["Mom"] = df_b["Price"].pct_change(mom_lookback)
        df_b["Above"] = df_b["Price"] > df_b["MA"]
        
        all_data[key] = {"base": df_b, "lev": df_l}

    # B. 取時間交集並過濾使用者區間
    common_idx = None
    for key in all_data:
        if common_idx is None: common_idx = all_data[key]["base"].index
        else: common_idx = common_idx.intersection(all_data[key]["base"].index)
    
    mask = (common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))
    backtest_idx = common_idx[mask]

    if len(backtest_idx) == 0:
        st.error("此時間區間內無重疊資料，請重新選擇時間。")
        st.stop()

    # C. 每日模擬 (採用與單標的 LRS 相同的價格比例法)
    equity_lrs = []
    holdings = []
    current_equity = 1.0
    
    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        
        # 1. 決定今天持有的標的 (根據當天收盤狀態決定下一日的持倉)
        candidates = []
        for key in selected_keys:
            if all_data[key]["base"].loc[today, "Above"]:
                mom_val = all_data[key]["base"].loc[today, "Mom"]
                if not pd.isna(mom_val):
                    candidates.append((key, mom_val))
        
        choice = max(candidates, key=lambda x: x[1])[0] if candidates else "Cash"
        holdings.append(choice)
        
        # 2. 計算今日報酬 (今日淨值 = 昨日淨值 * 今日價格比)
        if i > 0:
            last_choice = holdings[i-1]
            if last_choice != "Cash":
                p_today = all_data[last_choice]["lev"].loc[today, "Price"]
                p_yest = all_data[last_choice]["lev"].loc[yesterday, "Price"]
                current_equity *= (p_today / p_yest)
        
        equity_lrs.append(current_equity)
    
    df_res = pd.DataFrame({"Equity": equity_lrs, "Holding": holdings}, index=backtest_idx)

    # --- 6. 呈現結果 ---
    final_val, total_ret, mdd_val = calc_metrics_standard(df_res["Equity"])
    
    # KPI 顯示區
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產</div><div class="kpi-value">${final_val*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with kpi2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">總報酬率</div><div class="kpi-value">{total_ret:.2%}</div></div>', unsafe_allow_html=True)
    with kpi3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤 (MDD)</div><div class="kpi-value">{mdd_val:.2%}</div></div>', unsafe_allow_html=True)

    # 資金曲線
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="#21c354", width=3)))
    
    # 繪製各標的原型 Buy & Hold 作為對照
    for key in selected_keys:
        p_base = all_data[key]["base"].loc[backtest_idx, "Price"]
        bench_equity = (p_base / p_base.iloc[0]) * capital
        fig.add_trace(go.Scatter(x=backtest_idx, y=bench_equity, name=f"持有 {key}", opacity=0.3))
    
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 詳細表格
    with st.expander("查看詳細交易紀錄"):
        st.dataframe(df_res)
