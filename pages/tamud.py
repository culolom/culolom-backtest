###############################################################
# app.py — 塔木德策略 (Talmud Strategy) 回測系統 + 動能衰竭監測
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path
import sys

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

###############################################################
# 字型與頁面設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="塔木德策略與動能監測", page_icon="⚖️", layout="wide")

# ==========================================
# 🛑 Sidebar 區域
# ==========================================
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 📈 動能研究參數")
    mom_period = st.slider("動能計算週期 (月)", 1, 12, 12)
    mom_smooth = st.slider("動能平滑天數 (天)", 5, 60, 20)
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# ==========================================
# 主頁面標題
# ==========================================
st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 塔木德資產配置與動能雷達</h1>", unsafe_allow_html=True)

###############################################################
# 資料設定與讀取
###############################################################

DATA_DIR = Path("data")

ASSETS_REAL_ESTATE = {"VNQ (房地產信託ETF)": "VNQ", "IYR (美國地產ETF)": "IYR"}
ASSETS_STOCKS = {"QQQ (納斯達克100)": "QQQ", "SPY (標普500)": "SPY", "VTI (全美股市)": "VTI", "VT (全球股市)": "VT", "0050.TW (台灣50)": "0050.TW"}
ASSETS_CASH = {"USD Cash (純現金 0利率)": "USD_CASH", "SGOV (0-3月國債)": "SGOV", "TBIL (3個月國債)": "TBIL", "BND (美國總體債券)": "BND", "BNDW (全球總體債券)": "BNDW"}
ASSETS_BENCHMARK = {"SPY (標普500)": "SPY", "QQQ (納斯達克100)": "QQQ", "VT (全球股市)": "VT", "0050.TW (台灣50)": "0050.TW"}

def load_csv(symbol: str) -> pd.DataFrame:
    if symbol == "USD_CASH": return pd.DataFrame()
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv"]
    path = next((DATA_DIR / c for c in candidates if (DATA_DIR / c).exists()), None)
    if not path: return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df["Price"] = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        return df[["Price"]]
    except: return pd.DataFrame()

def get_common_range(sym_list):
    dfs = [load_csv(s) for s in sym_list if s != "USD_CASH"]
    if not dfs or all(d.empty for d in dfs): return dt.date(2015, 1, 1), dt.date.today()
    start = max([d.index.min() for d in dfs if not d.empty]).date()
    end = min([d.index.max() for d in dfs if not d.empty]).date()
    return start, end

###############################################################
# UI 輸入區
###############################################################

col1, col2, col3, col4 = st.columns(4)
with col1: re_label = st.selectbox("1️⃣ 土地 (REITs)", list(ASSETS_REAL_ESTATE.keys())); sym_re = ASSETS_REAL_ESTATE[re_label]
with col2: stk_label = st.selectbox("2️⃣ 事業 (Stocks)", list(ASSETS_STOCKS.keys())); sym_stk = ASSETS_STOCKS[stk_label]
with col3: cash_label = st.selectbox("3️⃣ 現金 (Cash)", list(ASSETS_CASH.keys())); sym_cash = ASSETS_CASH[cash_label]
with col4: bench_label = st.selectbox("📊 對照組", list(ASSETS_BENCHMARK.keys())); sym_bench = ASSETS_BENCHMARK[bench_label]

s_min, s_max = get_common_range([sym_re, sym_stk, sym_cash, sym_bench])
col_d1, col_d2, col_d3 = st.columns(3)
with col_d1: start_date = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=365*5)), min_value=s_min, max_value=s_max)
with col_d2: end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col_d3: initial_capital = st.number_input("初始本金", value=1_000_000, step=100_000)

rebalance_freq = st.radio("再平衡頻率", ["每年 (Yearly)", "每季 (Quarterly)", "不平衡 (Buy & Hold)"], horizontal=True)

###############################################################
# 回測與動能邏輯
###############################################################

if st.button("執行分析 🚀", type="primary"):
    with st.spinner("正在計算..."):
        # 1. 資料處理
        df_stk = load_csv(sym_stk).loc[start_date:end_date]
        df_re = load_csv(sym_re).loc[start_date:end_date]
        df_bench = load_csv(sym_bench).loc[start_date:end_date]
        df_cash = pd.DataFrame(index=df_stk.index)
        df_cash["Price"] = 1.0 if sym_cash == "USD_CASH" else load_csv(sym_cash).loc[start_date:end_date]["Price"]

        df = pd.DataFrame(index=df_stk.index)
        df["P_STK"], df["P_RE"], df["P_CASH"], df["P_BENCH"] = df_stk["Price"], df_re["Price"], df_cash["Price"], df_bench["Price"]
        df = df.ffill().dropna()

        # 2. 動能計算 (核心研究邏輯)
        mom_days = mom_period * 21
        df['Mom_STK'] = df['P_STK'].pct_change(mom_days)
        df['Mom_Smooth'] = df['Mom_STK'].rolling(window=mom_smooth).mean()
        df['Mom_Slope'] = df['Mom_Smooth'].diff() # 動能方向：正為增強，負為衰竭

        # 3. 塔木德回測
        dates = df.index
        holdings = {"RE": initial_capital/3, "STK": initial_capital/3, "CASH": initial_capital/3}
        history_equity, history_weights = [], []

        for i, d in enumerate(dates):
            if i > 0:
                holdings["RE"] *= (df["P_RE"].iloc[i] / df["P_RE"].iloc[i-1])
                holdings["STK"] *= (df["P_STK"].iloc[i] / df["P_STK"].iloc[i-1])
                holdings["CASH"] *= (df["P_CASH"].iloc[i] / df["P_CASH"].iloc[i-1])
            
            total_equity = sum(holdings.values())
            
            # 再平衡
            if (rebalance_freq == "每年 (Yearly)" and i > 0 and d.year != dates[i-1].year) or \
               (rebalance_freq == "每季 (Quarterly)" and i > 0 and d.month in [1,4,7,10] and d.month != dates[i-1].month):
                target = total_equity / 3
                holdings = {k: target for k in holdings}
            
            history_equity.append(total_equity)
            history_weights.append([holdings[k]/total_equity for k in ["RE", "STK", "CASH"]])

        df["Equity_Talmud"] = history_equity
        df["Equity_Benchmark"] = initial_capital * (df["P_BENCH"] / df["P_BENCH"].iloc[0])

        # ---------------- 顯示 KPI ----------------
        # (這裡省略部分重複的 KPI HTML 代碼，保持簡潔)
        st.success(f"回測完成！區間：{start_date} ~ {end_date}")

        # ---------------- 策略效益分析 ----------------
        tab1, tab2, tab3 = st.tabs(["資金成長曲線", "動態權重", "📈 動能雷達 (研究專用)"])

        with tab1:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Talmud"], name="塔木德策略", line=dict(color="#636EFA", width=3)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name=f"基準: {bench_label}", line=dict(color="#B0BEC5", width=2, dash='dash')))
            st.plotly_chart(fig_eq, use_container_width=True)

        with tab2:
            w_arr = np.array(history_weights)
            fig_w = go.Figure()
            colors = ['rgba(0, 204, 150, 0.5)', 'rgba(239, 85, 59, 0.5)', 'rgba(99, 110, 250, 0.5)']
            for idx, label in enumerate([f"土地: {re_label}", f"股票: {stk_label}", f"現金: {cash_label}"]):
                fig_w.add_trace(go.Scatter(x=df.index, y=w_arr[:, idx], name=label, stackgroup='one', fillcolor=colors[idx], line=dict(width=0)))
            st.plotly_chart(fig_w, use_container_width=True)

        with tab3:
            st.markdown(f"### 🔍 {stk_label} 動能強度與衰竭檢查")
            st.write("此圖表觀察 12 個月報酬率的走勢。當價格還在漲，但動能線（藍線）開始下滑時，即為動能衰竭訊號。")
            
            fig_mom = go.Figure()
            # 12個月動能
            fig_mom.add_trace(go.Scatter(x=df.index, y=df['Mom_STK'], name="12M 原始動能", line=dict(color="rgba(100,100,100,0.3)", width=1)))
            fig_mom.add_trace(go.Scatter(x=df.index, y=df['Mom_Smooth'], name="平滑動能線", line=dict(color="#FF4B4B", width=3)))
            
            # 零軸
            fig_mom.add_hline(y=0, line_dash="dash", line_color="black")
            
            # 動能方向 (用顏色區分)
            df['Color'] = df['Mom_Slope'].apply(lambda x: 'green' if x > 0 else 'red')
            
            fig_mom.update_layout(title="動能強度 (ROC 12M)", yaxis_title="報酬率", hovermode="x unified", template="plotly_white")
            st.plotly_chart(fig_mom, use_container_width=True)
            
            # 當前狀態儀表板
            curr_mom = df['Mom_Smooth'].iloc[-1]
            curr_slope = df['Mom_Slope'].iloc[-1]
            
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                status = "🔥 強勢續強" if curr_mom > 0 and curr_slope > 0 else \
                         "⚠️ 動能衰竭 (持平/下滑)" if curr_mom > 0 and curr_slope < 0 else \
                         "❄️ 弱勢盤整"
                st.metric("當前動能狀態", status)
            with c_col2:
                st.metric("12M 平滑報酬率", f"{curr_mom:.2%}", delta=f"{curr_slope:.4%}")

        # 下載區... (保留原代碼)
