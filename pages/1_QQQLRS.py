import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 基礎設定 ---
st.set_page_config(page_title="台美股動能旋轉系統", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (請確保同層級有 auth.py)
try:
    import auth
    if not auth.check_password():
        st.stop()
except ImportError:
    st.warning("提醒：未偵測到 auth.py 模組，暫時跳過驗證。")

# --- 樣式設定 ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# --- 標的配置 ---
ETF_CONFIG = {
    "台股大盤 (0050 / 00631L)": {"base": "0050", "lev": "00631L", "label": "台股正2"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662", "lev": "00670L", "label": "那指正2"},
    "S&P 500 (00646 / 00647L)": {"base": "00646", "lev": "00647L", "label": "標普正2"}
}

DATA_DIR = Path("data")

# --- 工具函式 ---
def load_data(symbol):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    return df[["Close"]].rename(columns={"Close": "Price"})

def calc_performance(equity_series, daily_ret_series):
    # 計算 KPI 指標
    days = (equity_series.index[-1] - equity_series.index[0]).days
    final_return = equity_series.iloc[-1] - 1
    cagr = (1 + final_return)**(365/days) - 1 if days > 0 else 0
    mdd = (equity_series / equity_series.cummax() - 1).min()
    vol = daily_ret_series.std() * np.sqrt(252)
    sharpe = (daily_ret_series.mean() / daily_ret_series.std() * np.sqrt(252)) if daily_ret_series.std() != 0 else 0
    return {"Total Ret": final_return, "CAGR": cagr, "MDD": mdd, "Vol": vol, "Sharpe": sharpe}

# --- UI 介面 ---
st.title("🦅 三標動態 LRS 旋轉策略回測")
st.markdown("當原型 ETF > 200MA，持有動能最強(12m Return)的正2 ETF；全破均線則持現金。")

with st.sidebar:
    st.header("⚙️ 設定參數")
    selected_pool = st.multiselect("選擇投資池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys()))
    capital = st.number_input("初始本金 (元)", value=100000, step=10000)
    lookback = st.slider("動能參考天數 (12個月約252天)", 100, 300, 252)
    ma_window = st.number_input("均線天數 (SMA)", value=200)

if not selected_pool:
    st.error("請至少選擇一個標的")
    st.stop()

# --- 執行回測 ---
if st.button("開始回測 🚀"):
    all_dfs = {}
    
    # 1. 載入資料與預處理
    with st.spinner("讀取 CSV 資料中..."):
        for key in selected_pool:
            cfg = ETF_CONFIG[key]
            base_df = load_data(cfg["base"])
            lev_df = load_data(cfg["lev"])
            
            if base_df.empty or lev_df.empty:
                st.error(f"資料缺失: {key}")
                st.stop()
            
            # 計算訊號指標
            base_df["MA"] = base_df["Price"].rolling(ma_window).mean()
            base_df["Mom"] = base_df["Price"].pct_change(lookback)
            base_df["Above"] = base_df["Price"] > base_df["MA"]
            base_df["Lev_Ret"] = lev_df["Price"].pct_change().fillna(0)
            
            all_dfs[key] = base_df

    # 2. 對齊時間軸
    common_idx = None
    for key in all_dfs:
        if common_idx is None: common_idx = all_dfs[key].index
        else: common_idx = common_idx.intersection(all_dfs[key].index)
    
    # 3. 每日模擬
    df_res = pd.DataFrame(index=common_idx).sort_index()
    holdings = []
    daily_rets = []
    
    for date in df_res.index:
        qualified = []
        for key in selected_pool:
            if all_dfs[key].loc[date, "Above"]:
                mom_val = all_dfs[key].loc[date, "Mom"]
                qualified.append((key, mom_val))
        
        if not qualified:
            current_choice = "Cash (現金)"
            ret = 0.0
        else:
            # 排序選出最強動能
            current_choice = max(qualified, key=lambda x: x[1])[0]
            ret = all_dfs[current_choice].loc[date, "Lev_Ret"]
        
        holdings.append(current_choice)
        daily_rets.append(ret)
    
    df_res["Holding"] = holdings
    df_res["Strategy_Ret"] = daily_rets
    df_res["Equity"] = (1 + df_res["Strategy_Ret"]).cumprod()
    
    # 4. 績效與圖表
    metrics = calc_performance(df_res["Equity"], df_res["Strategy_Ret"])
    
    # KPI 顯示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("期末資產", f"${capital * df_res['Equity'].iloc[-1]:,.0f}")
    c2.metric("年化報酬 (CAGR)", f"{metrics['CAGR']:.2%}")
    c3.metric("最大回撤 (MDD)", f"{metrics['MDD']:.2%}", delta_color="inverse")
    c4.metric("夏普比率 (Sharpe)", f"{metrics['Sharpe']:.2f}")

    # 資金曲線
    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="#FFD700", width=3)))
    
    # 對照組 (各標的原型 B&H)
    for key in selected_pool:
        p_series = all_dfs[key].loc[df_res.index, "Price"]
        bh_equity = (p_series / p_series.iloc[0]) * capital
        fig_equity.add_trace(go.Scatter(x=df_res.index, y=bh_equity, name=f"持有 {key}", opacity=0.4))
    
    fig_equity.update_layout(title="策略資金曲線 vs 買進持有", template="plotly_white", height=500)
    st.plotly_chart(fig_equity, use_container_width=True)

    # 持倉分析圖
    st.markdown("### 🛰️ 每日持倉分布")
    fig_hold = go.Figure()
    fig_hold.add_trace(go.Scatter(x=df_res.index, y=df_res["Holding"], mode='markers', 
                                 marker=dict(size=5, color=np.arange(len(df_res)), colorscale='Viridis')))
    fig_hold.update_layout(height=300, yaxis_title="持有資產")
    st.plotly_chart(fig_hold, use_container_width=True)

    # 換股統計
    switches = (df_res["Holding"] != df_res["Holding"].shift()).sum()
    st.info(f"💡 回測期間總共進行了 **{switches}** 次換股或進出動作。")

    # 下載數據
    csv = df_res.to_csv().encode('utf-8')
    st.download_button("下載回測詳細紀錄 (CSV)", csv, "backtest_result.csv", "text/csv")
