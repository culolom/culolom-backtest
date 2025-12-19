import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面配置與樣式 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 防禦旋轉版", page_icon="🐹", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .kpi-card {
            background-color: #ffffff; border-radius: 16px; padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04); border: 1px solid rgba(128, 128, 128, 0.1);
            text-align: center; height: 100%; transition: all 0.3s ease;
        }
        .kpi-card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08); }
        .kpi-label { font-size: 0.95rem; color: #666; margin-bottom: 8px; }
        .kpi-value { font-size: 1.8rem; font-weight: 800; color: #1f1f1f; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 標的配置定義 ---
# 主策略股票池
MAIN_STRATEGIES = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW", "label": "台股正2"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW", "label": "那指正2"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW", "label": "標普正2"}
}

# 避險資產池
DEFENSIVE_POOL = {
    "黃金部隊": {"base": "00635U.TW", "lev": "00708L.TW"},
    "國庫券基準": {"base": "BIL", "lev": "BIL"}
}

DATA_DIR = Path("data")

# --- 3. 工具函式 ---
def load_csv(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# --- 4. Sidebar 參數設定 ---
with st.sidebar:
    st.header("⚙️ 策略參數")
    selected_main = st.selectbox("選擇主策略標的", options=list(MAIN_STRATEGIES.keys()))
    
    st.subheader("📅 回測設定")
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    capital = st.number_input("投入本金 (元)", value=100000)
    
    ma_window = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("避險動能天數 (12M)", 100, 300, 252)

# --- 5. 主程式回測邏輯 ---
st.title("🛡️ LRS 主動防禦旋轉策略")
st.info("邏輯：主標的 > 200MA 時全倉持有正2；跌破時，自動切換至【黃金】或【國庫券】中動能(12M)最強者。")



if st.button("開始回測 🚀"):
    # A. 載入主策略資料
    main_cfg = MAIN_STRATEGIES[selected_main]
    df_main_b = load_csv(main_cfg["base"])
    df_main_l = load_csv(main_cfg["lev"])
    
    # B. 載入避險資料
    def_data = {}
    for d_name, d_cfg in DEFENSIVE_POOL.items():
        def_data[d_name] = {"base": load_csv(d_cfg["base"]), "lev": load_csv(d_cfg["lev"])}

    # C. 取所有資料交集時間
    all_dfs = [df_main_b, df_main_l] + [d["base"] for d in def_data.values()] + [d["lev"] for d in def_data.values()]
    common_idx = all_dfs[0].index
    for d in all_dfs[1:]: common_idx = common_idx.intersection(d.index)
    
    backtest_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]

    # D. 計算技術指標
    df_main_b["MA"] = df_main_b["Price"].rolling(ma_window).mean()
    for d_name in def_data:
        def_data[d_name]["base"]["Mom"] = def_data[d_name]["base"]["Price"].pct_change(mom_lookback)

    # E. 模擬持倉循環 (T+1 延遲進場對齊版)
    equity_curve = [1.0]
    holdings = []
    actions = []
    reasons = []
    
    # 初始狀態：直接買入主標的 (全倉買進)
    current_choice = "Main"

    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        
        # 1. 產生今日收盤後的決策 (決定明天持有的標的)
        is_above = df_main_b.loc[today, "Price"] > df_main_b.loc[today, "MA"]
        
        if is_above:
            next_choice = "Main"
            reason = "股市站上均線，全倉正2"
        else:
            # 避險資產動能 PK
            best_def = "Cash"
            best_mom = -9999
            for d_name in def_data:
                m = def_data[d_name]["base"].loc[today, "Mom"]
                if m > best_mom:
                    best_mom = m
                    best_def = d_name
            next_choice = best_def
            reason = f"股市跌破均線，避險至 {best_def}"

        holdings.append(current_choice)
        
        # 2. 標註動作與損益
        if i == 0:
            equity_curve.append(1.0)
            actions.append("初始買進 🟢")
        else:
            prev_h = holdings[i-1]
            if current_choice == prev_h:
                # 損益計算：今日 vs 昨日價格比
                if current_choice == "Main":
                    r = df_main_l.loc[today, "Price"] / df_main_l.loc[yesterday, "Price"]
                else:
                    r = def_data[current_choice]["lev"].loc[today, "Price"] / def_data[current_choice]["lev"].loc[yesterday, "Price"]
                equity_curve.append(equity_curve[-1] * r)
                actions.append("續抱 ⚪")
            else:
                equity_curve.append(equity_curve[-1])
                actions.append("切換 🔄")
        
        reasons.append(reason)
        current_choice = next_choice

    df_res = pd.DataFrame({
        "Equity": equity_curve[1:], "Holding": holdings, 
        "動作": actions, "切換理由": reasons
    }, index=backtest_idx)

    # --- 6. KPI 與圖表呈現 ---
    f_eq = df_res["Equity"].iloc[-1]
    mdd = (1 - df_res["Equity"] / df_res["Equity"].cummax()).max()

    # KPI 卡片 (修正變數命名)
    k1, k2, k3 = st.columns(3)
    with k1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產</div><div class="kpi-value">${f_eq*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with k2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">累積報酬</div><div class="kpi-value">{(f_eq-1):.2%}</div></div>', unsafe_allow_html=True)
    with k3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤 (MDD)</div><div class="kpi-value">-{mdd:.2%}</div></div>', unsafe_allow_html=True)

    # 資金曲線
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="防禦型 LRS 策略", line=dict(color="#21c354", width=3)))
    fig.add_trace(go.Scatter(x=backtest_idx, y=(df_main_b.loc[backtest_idx, "Price"]/df_main_b.loc[backtest_idx[0], "Price"])*capital, name="主標的原型 B&H", opacity=0.3))
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 交易明細表格
    st.header("📝 策略執行紀錄")
    log_display = df_res[df_res["動作"] != "續抱 ⚪"].copy()
    st.dataframe(log_display[["動作", "Holding", "切換理由", "Equity"]], use_container_width=True)
