import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面配置 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 主動防禦版", page_icon="🐹", layout="wide")

st.markdown("""
    <style>
        .kpi-card {
            background-color: #ffffff; border-radius: 16px; padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04); border: 1px solid rgba(128, 128, 128, 0.1);
            text-align: center; height: 100%; transition: all 0.3s ease;
        }
        .kpi-label { font-size: 0.95rem; color: #666; margin-bottom: 8px; }
        .kpi-value { font-size: 1.8rem; font-weight: 800; color: #1f1f1f; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 標的配置表 ---
# 主策略股票池
MAIN_STOCKS = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW"}
}

# 避險資產池
DEFENSIVE_ASSETS = {
    "黃金部隊": {"base": "00635U.TW", "lev": "00708L.TW"}, # 避險時可選黃金正2
    "國庫券基準": {"base": "BIL", "lev": "BIL"}            # 或保守的國庫券
}

DATA_DIR = Path("data")

def load_csv(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# --- 3. Sidebar 參數 ---
with st.sidebar:
    st.header("⚙️ 戰情室設定")
    strategy_key = st.selectbox("選擇主策略標的", options=list(MAIN_STOCKS.keys()))
    
    st.subheader("📅 回測設定")
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    capital = st.number_input("投入本金", value=100000)
    
    ma_val = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("避險動能參考天數 (12M)", 100, 300, 252)

# --- 4. 回測核心邏輯 ---
st.title("🛡️ 主動防禦型 LRS 動態配置策略")
st.info("策略：一開始全倉買入主標的。若主標的跌破 200MA，則自動切換至【黃金】或【國庫券】中動能較強者。")



if st.button("啟動精確回測 🚀"):
    # A. 載入資料
    main_cfg = MAIN_STOCKS[strategy_key]
    df_main_b = load_csv(main_cfg["base"])
    df_main_l = load_csv(main_cfg["lev"])
    
    def_data = {}
    for d_key, d_cfg in DEFENSIVE_ASSETS.items():
        def_data[d_key] = {"base": load_csv(d_cfg["base"]), "lev": load_csv(d_cfg["lev"])}

    # B. 時間對齊
    all_symbols = [df_main_b, df_main_l] + [d["base"] for d in def_data.values()]
    common_idx = all_symbols[0].index
    for d in all_symbols[1:]: common_idx = common_idx.intersection(d.index)
    
    backtest_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]

    # C. 計算指標
    df_main_b["MA"] = df_main_b["Price"].rolling(ma_val).mean()
    for d_key in def_data:
        def_data[d_key]["base"]["Mom"] = def_data[d_key]["base"]["Price"].pct_change(mom_lookback)

    # D. 模擬循環 (T+1 對齊邏輯)
    equity_curve = [1.0]
    holdings = []
    actions = []
    reasons = []
    
    # 初始狀態：全倉買進主策略
    current_choice = "Main" 

    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        
        # 1. 產生今日決策 (判定今日收盤，決定明天持有的標的)
        stock_above_ma = df_main_b.loc[today, "Price"] > df_main_b.loc[today, "MA"]
        
        if stock_above_ma:
            next_choice = "Main"
            reason = "股市站上均線，持有正2放大獲利"
        else:
            # 比較避險資產動能
            best_def = "Cash"
            best_mom = -999
            for d_key in def_data:
                m = def_data[d_key]["base"].loc[today, "Mom"]
                if m > best_mom:
                    best_mom = m
                    best_def = d_key
            next_choice = best_def
            reason = f"股市跌破均線，避險至強勢資產 {best_def}"

        # 2. 紀錄與損益計算 (T+1 邏輯)
        holdings.append(current_choice)
        if i == 0:
            equity_curve.append(1.0)
            actions.append("初始買進")
        else:
            # 只有昨天跟今天持有一樣的標的才計算報酬 (模擬換股延遲)
            if current_choice == holdings[i-1]:
                if current_choice == "Main":
                    r = df_main_l.loc[today, "Price"] / df_main_l.loc[yesterday, "Price"]
                else:
                    r = def_data[current_choice]["lev"].loc[today, "Price"] / def_data[current_choice]["lev"].loc[yesterday, "Price"]
                equity_curve.append(equity_curve[-1] * r)
            else:
                equity_curve.append(equity_curve[-1])
            
            # 動作標註
            actions.append("切換" if current_choice != holdings[i-1] else "續抱")

        reasons.append(reason)
        current_choice = next_choice

    # E. 結果呈現
    df_res = pd.DataFrame({
        "Equity": equity_curve[1:], "Holding": holdings, 
        "動作": actions, "理由": reasons
    }, index=backtest_idx)

    f_eq = df_res["Equity"].iloc[-1]
    mdd = (1 - df_res["Equity"] / df_res["Equity"].cummax()).max()

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產</div><div class="kpi-value">${f_eq*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">累積報酬</div><div class="kpi-value">{(f_eq-1):.2%}</div></div>', unsafe_allow_html=True)
    with kpi3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤</div><div class="kpi-value">-{mdd:.2%}</div></div>', unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="防禦型策略", line=dict(color="#21c354", width=3)))
    fig.add_trace(go.Scatter(x=backtest_idx, y=(df_main_b.loc[backtest_idx, "Price"]/df_main_b.loc[backtest_idx[0], "Price"])*capital, name="原型買進持有", opacity=0.3))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📝 策略執行日誌 (僅顯示變動日)")
    log_show = df_res[df_res["動作"] != "續抱"].copy()
    st.dataframe(log_show[["動作", "Holding", "理由", "Equity"]], use_container_width=True)
