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
    '黃金部隊': {'base': '00635U.TW', 'lev': '00708L.TW'}
}

DATA_DIR = Path("data")

# --- 3. 工具函式 ---
def load_csv_standard(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if "Close" in df.columns:
        df["Price"] = df["Close"]
    return df.sort_index()[["Price"]]

def calc_metrics_standard(series):
    final_equity = series.iloc[-1]
    total_ret = final_equity - 1
    mdd = 1 - (series / series.cummax()).min()
    return final_equity, total_ret, mdd

# --- 4. Sidebar 參數設定 ---
with st.sidebar:
    st.header("⚙️ 策略參數")
    selected_keys = st.multiselect("選擇投資組合池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys()))
    
    st.subheader("📅 回測時間範圍")
    start_date = st.date_input("開始日期", value=dt.date(2020, 1, 1))
    end_date = st.date_input("結束日期", value=dt.date(2025, 12, 18))
    
    capital = st.number_input("投入本金 (元)", value=100000, step=10000)
    ma_window = st.number_input("均線天數 (SMA)", value=200)
    mom_lookback = st.slider("動能參考天數 (12M)", 100, 300, 252)

# --- 5. 主程式回測邏輯 ---
st.title("🛡️ 倉鼠全資產動態 LRS 旋轉策略")
st.info("策略邏輯：收盤 > 200MA 准許買入；若多標的同時達標，選擇【12個月報酬最高者】持有。")

if st.button("開始精確回測 🚀"):
    if not selected_keys:
        st.error("請選擇標的。")
        st.stop()

    all_data = {}
    for key in selected_keys:
        cfg = ETF_CONFIG[key]
        df_b = load_csv_standard(cfg["base"])
        df_l = load_csv_standard(cfg["lev"])
        if df_b.empty or df_l.empty:
            st.error(f"資料缺失：{key}")
            st.stop()
        df_b["MA"] = df_b["Price"].rolling(ma_window).mean()
        df_b["Mom"] = df_b["Price"].pct_change(mom_lookback)
        df_b["Above"] = df_b["Price"] > df_b["MA"]
        all_data[key] = {"base": df_b, "lev": df_l}

    common_idx = None
    for key in all_data:
        if common_idx is None: common_idx = all_data[key]["base"].index
        else: common_idx = common_idx.intersection(all_data[key]["base"].index)
    
    backtest_idx = common_idx[(common_idx >= pd.to_datetime(start_date)) & (common_idx <= pd.to_datetime(end_date))]

    # 模擬持倉與理由紀錄
    equity_lrs = [1.0]
    holdings = []
    actions = []
    reasons = []
    
    for i in range(len(backtest_idx)):
        today = backtest_idx[i]
        yesterday = backtest_idx[i-1] if i > 0 else None
        prev_h = holdings[i-1] if i > 0 else "Cash"
        
        # 1. 決定今天持有的標的 (當日收盤判定)
        candidates = []
        for key in selected_keys:
            if all_data[key]["base"].loc[today, "Above"]:
                mom_val = all_data[key]["base"].loc[today, "Mom"]
                if not pd.isna(mom_val):
                    candidates.append((key, mom_val))
        
        curr_h = max(candidates, key=lambda x: x[1])[0] if candidates else "Cash"
        holdings.append(curr_h)
        
        # 2. 標註動作與理由
        if curr_h != prev_h:
            if prev_h == "Cash":
                actions.append("買進 🟢")
                reasons.append(f"{curr_h} 站上均線且動能最強")
            elif curr_h == "Cash":
                actions.append("賣出 🔴")
                reasons.append(f"{prev_h} 跌破均線，轉現金避險")
            else:
                actions.append("切換 🔄")
                reasons.append(f"{curr_h} 動能超越 {prev_h}")
        else:
            actions.append("續抱 ⚪")
            reasons.append("趨勢/動能維持優勢")

        # 3. 計算今日淨值 (T+1 延遲邏輯)
        if i == 0:
            equity_lrs.append(1.0)
        else:
            if curr_h != "Cash" and holdings[i-1] == curr_h:
                price_today = all_data[curr_h]["lev"].loc[today, "Price"]
                price_yest = all_data[curr_h]["lev"].loc[yesterday, "Price"]
                equity_lrs.append(equity_lrs[-1] * (price_today / price_yest))
            else:
                equity_lrs.append(equity_lrs[-1])
    
    df_res = pd.DataFrame({
        "Equity": equity_lrs[1:], 
        "Holding": holdings, 
        "動作": actions, 
        "切換理由": reasons
    }, index=backtest_idx)

    # --- 6. 呈現結果 ---
    final_val, total_ret, mdd_val = calc_metrics_standard(df_res["Equity"])
    
    k1, k2, k3 = st.columns(3)
    with k1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">期末資產</div><div class="kpi-value">${final_val*capital:,.0f}</div></div>', unsafe_allow_html=True)
    with k2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">總報酬率</div><div class="kpi-value">{total_ret:.2%}</div></div>', unsafe_allow_html=True)
    with k3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">最大回撤 (MDD)</div><div class="kpi-value">-{mdd_val:.2%}</div></div>', unsafe_allow_html=True)

    # 資金曲線
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="#21c354", width=3)))
    st.plotly_chart(fig, use_container_width=True)

    # --- 7. 交易明細表格 ---
    st.header("📝 策略執行明細")
    st.info("僅顯示有「動作」發生的日期（買進、賣出或切換）。")
    
    # 過濾出有動作的日期，排除「續抱」
    trade_log = df_res[df_res["動作"] != "續抱 ⚪"].copy()
    trade_log["淨值"] = (trade_log["Equity"] * capital).map("{:,.0f}".format)
    
    st.dataframe(
        trade_log[["動作", "Holding", "切換理由", "淨值"]],
        use_container_width=True,
        column_config={
            "Holding": "持有標的",
            "Action": st.column_config.TextColumn("動作"),
        }
    )

    # --- 8. 相關性分析 ---
    st.header("🔍 資產相關性矩陣")
    corr_df = pd.DataFrame()
    for key in selected_keys:
        corr_df[key] = all_data[key]["base"].loc[backtest_idx, "Price"].pct_change()
    matrix = corr_df.corr()
    fig_corr = go.Figure(data=go.Heatmap(
        z=matrix.values, x=matrix.columns, y=matrix.columns,
        colorscale='RdBu', zmin=-1, zmax=1, text=np.around(matrix.values, 2), texttemplate="%{text}"
    ))
    st.plotly_chart(fig_corr, use_container_width=True)
