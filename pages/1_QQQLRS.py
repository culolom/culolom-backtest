import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面配置與高級 CSS 樣式 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 統合對齊版", page_icon="🐹", layout="wide")

st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        /* KPI 卡片樣式 */
        .kpi-card {
            background-color: #ffffff;
            border-radius: 16px;
            padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(128, 128, 128, 0.1);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100%;
            transition: all 0.3s ease;
        }
        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08);
        }
        .kpi-label {
            font-size: 0.95rem;
            color: #666;
            font-weight: 500;
            margin-bottom: 8px;
        }
        .kpi-value {
            font-size: 2rem;
            font-weight: 800;
            color: #1f1f1f;
            font-family: 'Noto Sans TC', sans-serif;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. 標的配置 (已補齊逗號與完整代號) ---
ETF_CONFIG = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW"},
    "黃金 (00635U / 00708L)": {"base": "00635U.TW", "lev": "00708L.TW"}
}

DATA_DIR = Path("data")

# --- 3. 工具函式 ---
def load_csv(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    # 統一使用 Price 欄位
    df["Price"] = df["Close"]
    return df[["Price"]]

# --- 4. Sidebar 參數設定 ---
# 🔒 驗證 (若無 auth.py 會自動跳過)
try:
    import auth
    if not auth.check_password(): st.stop()
except: pass

with st.sidebar:
    st.header("⚙️ 策略參數")
    selected_keys = st.multiselect("投資組合池", options=list(ETF_CONFIG.keys()), default=[list(ETF_CONFIG.keys())[0]])
    
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    capital = st.number_input("投入本金 (元)", value=100000, step=10000)
    
    ma_window = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("動能天數 (12M)", 100, 300, 252)
    
    position_mode = st.radio("策略初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑（標準 LRS）"], index=0)

# --- 5. 主程式回測邏輯 ---
st.title("📈 三標動態 LRS 動能旋轉策略 (統合對齊版)")
st.info("策略邏輯：收盤 > 200MA 准許買入；若多標的同時達標，選擇【12個月報酬最高者】持有。")

if st.button("開始精確回測 🚀"):
    all_data = {}
    # 為了計算 MA 與動能，資料需要足夠長
    for key in selected_keys:
        cfg = ETF_CONFIG[key]
        df_b = load_csv(cfg["base"])
        df_l = load_csv(cfg["lev"])
        
        if df_b.empty or df_l.empty:
            st.error(f"資料缺失：{key}")
            st.stop()
            
        # 計算 200MA 與 12M 動能
        df_b["MA"] = df_b["Price"].rolling(ma_window).mean()
        df_b["Mom"] = df_b["Price"].pct_change(mom_lookback)
        df_b["Above"] = df_b["Price"] > df_b["MA"]
        
        all_data[key] = {"base": df_b, "lev": df_l}

    # B. 取時間交集並過濾
    common_idx = None
    for key in all_data:
        if common_idx is None: common_idx = all_data[key]["base"].index
        else: common_idx = common_idx.intersection(all_data[key]["base"].index)
    
    backtest_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]

    # C. 每日模擬 (完全對齊單標版 if pos[i]==1 and pos[i-1]==1 邏輯)
    holdings = []
    equity_lrs = [1.0]
    
    # 初始狀態判斷
    current_choice = "Cash"
    if "一開始" in position_mode:
        init_day = backtest_idx[0]
        init_cands = []
        for key in selected_keys:
            if all_data[key]["base"].loc[init_day, "Above"]:
                init_cands.append((key, all_data[key]["base"].loc[init_day, "Mom"]))
        if init_cands:
            current_choice = max(init_cands, key=lambda x: x[1])[0]

    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        
        # 1. 根據今日收盤更新明日持倉決策
        candidates = []
        for key in selected_keys:
            if all_data[key]["base"].loc[today, "Above"]:
                mom_val = all_data[key]["base"].loc[today, "Mom"]
                if not pd.isna(mom_val):
                    candidates.append((key, mom_val))
        
        next_choice = max(candidates, key=lambda x: x[1])[0] if candidates else "Cash"
        holdings.append(current_choice)
        
        # 2. 計算今日淨值 (對齊邏輯：必須昨天持有 A，今天也持有 A 才算報酬)
        if i == 0:
            equity_lrs.append(1.0)
        else:
            if current_choice != "Cash" and current_choice == holdings[i-1]:
                p_today = all_data[current_choice]["lev"].loc[today, "Price"]
                p_yest = all_data[current_choice]["lev"].loc[yesterday, "Price"]
                equity_lrs.append(equity_lrs[-1] * (p_today / p_yest))
            else:
                equity_lrs.append(equity_lrs[-1])
        
        # 準備下一天的決策
        current_choice = next_choice

    # 封裝結果
    df_res = pd.DataFrame({"Equity": equity_lrs[1:], "Holding": holdings}, index=backtest_idx)

    # --- 6. 統計指標與圖表 ---
    final_eq = df_res["Equity"].iloc[-1]
    total_ret = final_eq - 1
    mdd = (1 - df_res["Equity"] / df_res["Equity"].cummax()).max()
    
    # KPI 卡片列
    k1, k2, k3 = st.columns(3)
    with k1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產 (LRS)</div><div class="kpi-value">${final_eq*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with k2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">總報酬率</div><div class="kpi-value">{total_ret:.2%}</div></div>', unsafe_allow_html=True)
    with k3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤 (MDD)</div><div class="kpi-value">-{mdd:.2%}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 資金曲線圖
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="#21c354", width=3)))
    
    for key in selected_keys:
        p_base = all_data[key]["base"].loc[backtest_idx, "Price"]
        bench_equity = (p_base / p_base.iloc[0]) * capital
        fig.add_trace(go.Scatter(x=backtest_idx, y=bench_equity, name=f"持有 {key}", opacity=0.3))
    
    fig.update_layout(template="plotly_white", height=500, margin=dict(l=20, r=20, t=50, b=20), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("查看詳細持倉紀錄"):
        st.dataframe(df_res)
