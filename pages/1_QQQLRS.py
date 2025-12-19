import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面配置與高級樣式 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 統合版", page_icon="🐹", layout="wide")

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

# --- 2. 完整標的配置 ---
ETF_CONFIG = {
    '台股大盤': {'base': '0050.TW', 'lev': '00631L.TW'},
    '美股納指': {'base': '00662.TW', 'lev': '00670L.TW'},
    '美股標普': {'base': '00646.TW', 'lev': '00647L.TW'},
    '黃金部隊': {'base': '00635U.TW', 'lev': '00708L.TW'},
    '長天期債': {'base': '00679B.TW', 'lev': '00680L.TW'},
    '數位資產': {'base': 'BTC-USD', 'lev': 'BTC-USD'}, # BTC 無正2，用原型
    '國庫券基準': {'base': 'BIL', 'lev': 'BIL'}        # BIL 作為現金參考
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

# 🔒 驗證守門員
try:
    import auth
    if not auth.check_password(): st.stop()
except: pass

# --- 4. Sidebar 參數設定 ---
with st.sidebar:
    st.header("⚙️ 策略參數設定")
    selected_keys = st.multiselect("選擇投資標的池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys())[:4])
    
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    capital = st.number_input("投入本金 (元)", value=100000, step=10000)
    
    ma_window = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("動能天數 (12M)", 100, 300, 252)
    
    position_mode = st.radio("初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑（標準 LRS）"], index=0)

# --- 5. 主程式回測邏輯 ---
st.title("🛡️ 倉鼠全資產動態 LRS 旋轉策略")
st.info("邏輯：原型 > 200MA 時進入；多標的同時達標時選擇【12個月報酬最高】者持有其正 2；全破均線則持現金。")

if st.button("啟動模擬分析 🚀"):
    if not selected_keys:
        st.error("請至少選擇一個標的。")
        st.stop()

    all_data = {}
    for key in selected_keys:
        cfg = ETF_CONFIG[key]
        df_b = load_csv(cfg["base"])
        df_l = load_csv(cfg["lev"])
        
        if df_b.empty or df_l.empty:
            st.warning(f"資料缺失：{key}，已從計算中剔除。")
            continue
            
        df_b["MA"] = df_b["Price"].rolling(ma_window).mean()
        df_b["Mom"] = df_b["Price"].pct_change(mom_lookback)
        df_b["Above"] = df_b["Price"] > df_b["MA"]
        all_data[key] = {"base": df_b, "lev": df_l}

    # 時間對齊
    common_idx = None
    for key in all_data:
        if common_idx is None: common_idx = all_data[key]["base"].index
        else: common_idx = common_idx.intersection(all_data[key]["base"].index)
    
    backtest_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]

    # 模擬持倉邏輯 (嚴格 T+1 對齊版)
    holdings = []
    equity_lrs = [1.0]
    
    # 處理初始狀態
    current_choice = "Cash"
    if "一開始" in position_mode:
        init_day = backtest_idx[0]
        init_cands = [(k, all_data[k]["base"].loc[init_day, "Mom"]) for k in all_data if all_data[k]["base"].loc[init_day, "Above"]]
        if init_cands:
            current_choice = max(init_cands, key=lambda x: x[1])[0]

    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        
        # A. 今日結算 (根據昨日決策)
        if i == 0:
            equity_lrs.append(1.0)
        else:
            last_choice = holdings[i-1]
            if last_choice != "Cash" and last_choice == current_choice:
                # 只有當昨天決定的跟今天持有的一樣(代表已進場一天以上)才計損益
                p_today = all_data[last_choice]["lev"].loc[today, "Price"]
                p_yest = all_data[last_choice]["lev"].loc[yesterday, "Price"]
                equity_lrs.append(equity_lrs[-1] * (p_today / p_yest))
            else:
                equity_lrs.append(equity_lrs[-1])

        # B. 產生今日決策 (供明日使用)
        holdings.append(current_choice)
        qualified = [(k, all_data[k]["base"].loc[today, "Mom"]) for k in all_data if all_data[k]["base"].loc[today, "Above"]]
        
        if not qualified:
            current_choice = "Cash"
        else:
            current_choice = max(qualified, key=lambda x: x[1])[0]

    df_res = pd.DataFrame({"Equity": equity_lrs[1:], "Holding": holdings}, index=backtest_idx)

    # --- 6. KPI 卡片與圖表 ---
    final_eq = df_res["Equity"].iloc[-1]
    mdd = (1 - df_res["Equity"] / df_res["Equity"].cummax()).max()
    
    k1, k2, k3 = st.columns(3)
    with k1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產</div><div class="kpi-value">${final_eq*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with k2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">累積報酬</div><div class="kpi-value">{(final_eq-1):.2%}</div></div>', unsafe_allow_html=True)
    with k3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤 (MDD)</div><div class="kpi-value">-{mdd:.2%}</div></div>', unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="統合旋轉策略", line=dict(color="#21c354", width=3)))
    for key in all_data:
        p_base = all_data[key]["base"].loc[backtest_idx, "Price"]
        fig.add_trace(go.Scatter(x=backtest_idx, y=(p_base/p_base.iloc[0])*capital, name=f"持有 {key}", opacity=0.3))
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # --- 7. 相關性矩陣分析 ---
    st.header("🔍 資產相關性矩陣 (Correlation)")
    corr_df = pd.DataFrame()
    for key in all_data:
        corr_df[key] = all_data[key]["base"].loc[backtest_idx, "Price"].pct_change()
    
    matrix = corr_df.corr()
    fig_corr = go.Figure(data=go.Heatmap(
        z=matrix.values, x=matrix.columns, y=matrix.columns,
        colorscale='RdBu', zmin=-1, zmax=1, text=np.around(matrix.values, 2), texttemplate="%{text}"
    ))
    fig_corr.update_layout(title="回測區間資產日報酬相關性", yaxis_autorange='reversed')
    st.plotly_chart(fig_corr, use_container_width=True)

    with st.expander("查看詳細日誌紀錄"):
        st.dataframe(df_res)
