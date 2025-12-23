###############################################################
# app.py — 塔木德策略 (Talmud Strategy) 回測系統
# 核心邏輯：三分法 (不動產/股票/現金) + 定期再平衡 + 自選對照組
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
# 🔒 驗證守門員 (確保能找到 auth.py)
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

st.set_page_config(page_title="塔木德策略回測", page_icon="⚖️", layout="wide")

# ==========================================
# 🛑 務必保留的 Sidebar 區域
# ==========================================
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# ==========================================
# 主頁面標題
# ==========================================
st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 塔木德資產配置 (Talmud Strategy)</h1>", unsafe_allow_html=True)
st.markdown("""
<b>猶太經典《塔木德》智慧：將資產分為三等份。</b><br>
1️⃣ <b>不動產 (Real Estate)</b>：如 VNQ, IYR<br>
2️⃣ <b>股票事業 (Stocks)</b>：如 QQQ, SPY, VT<br>
3️⃣ <b>現金 (Cash/Bonds)</b>：如 TBIL, SGOV, BIL (作為避風港與再平衡籌碼)<br>
<small>策略核心：定期將三個籃子的資金「再平衡 (Rebalance)」回 33% 權重，實現自動化的「高出低進」。</small>
""", unsafe_allow_html=True)

###############################################################
# 資料設定
###############################################################

DATA_DIR = Path("data")

# 1. 定義資產選項
ASSETS_REAL_ESTATE = {
    "VNQ (房地產信託ETF)": "VNQ", 
    "IYR (美國地產ETF)": "IYR"
}

ASSETS_STOCKS = {
    "QQQ (納斯達克100)": "QQQ", 
    "SPY (標普500)": "SPY", 
    "VTI (全美股市)": "VTI", 
    "VT (全球股市)": "VT",
    "0050.TW (台灣50)": "0050.TW"
}

# ✨ 已更新：加入 SGOV 與 純現金
ASSETS_CASH = {
    "USD Cash (純現金 0利率)": "USD_CASH",
    "SGOV (0-3月國債)": "SGOV", 
    "TBIL (3個月國債)": "TBIL", 
    "BIL (1-3月國債)": "BIL", 
    "SHV (短期國債)": "SHV", 
    "IEF (7-10年公債)": "IEF"
}

ASSETS_BENCHMARK = {
    "SPY (標普500)": "SPY",
    "QQQ (納斯達克100)": "QQQ",
    "VT (全球股市)": "VT",
    "0050.TW (台灣50)": "0050.TW",
    "VTI (全美股市)": "VTI"
}

# 2. 讀取 CSV (相容模式)
def load_csv(symbol: str) -> pd.DataFrame:
    if symbol == "USD_CASH":
        return pd.DataFrame() # 純現金不從 CSV 讀取
        
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv"]
    path = None
    for c in candidates:
        p = DATA_DIR / c
        if p.exists():
            path = p
            break
            
    if path is None:
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        df = df.sort_index()
        
        if "Adj Close" in df.columns:
            df["Price"] = df["Adj Close"]
        elif "Close" in df.columns:
            df["Price"] = df["Close"]
        else:
            return pd.DataFrame()
            
        return df[["Price"]]
    except:
        return pd.DataFrame()

# 3. 取得共同日期區間 (排除純現金的影響)
def get_common_range(sym_list):
    dfs = []
    for s in sym_list:
        if s == "USD_CASH": continue # ✨ 純現金跳過，由其他資產決定區間
        d = load_csv(s)
        if not d.empty:
            dfs.append(d)
    
    if not dfs:
        return dt.date(2015, 1, 1), dt.date.today()
    
    start = max([d.index.min() for d in dfs]).date()
    end = min([d.index.max() for d in dfs]).date()
    return start, end

###############################################################
# UI 輸入區
###############################################################

st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    re_label = st.selectbox("1️⃣ 土地 (REITs)", list(ASSETS_REAL_ESTATE.keys()))
    sym_re = ASSETS_REAL_ESTATE[re_label]
with col2:
    stk_label = st.selectbox("2️⃣ 事業 (Stocks)", list(ASSETS_STOCKS.keys()), index=0)
    sym_stk = ASSETS_STOCKS[stk_label]
with col3:
    cash_label = st.selectbox("3️⃣ 現金 (Cash)", list(ASSETS_CASH.keys()), index=0)
    sym_cash = ASSETS_CASH[cash_label]
with col4:
    bench_label = st.selectbox("📊 比較基準 (Benchmark)", list(ASSETS_BENCHMARK.keys()), index=0)
    sym_bench = ASSETS_BENCHMARK[bench_label]

# 計算日期範圍 (包含對照組)
s_min, s_max = get_common_range([sym_re, sym_stk, sym_cash, sym_bench])
st.info(f"📌 {sym_re} + {sym_stk} + {sym_cash} + {sym_bench} 的共同資料區間：{s_min} ~ {s_max}")

# 參數設定
col_d1, col_d2, col_d3 = st.columns(3)
with col_d1:
    start_date = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=365*5)), min_value=s_min, max_value=s_max)
with col_d2:
    end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col_d3:
    initial_capital = st.number_input("初始本金 (元)", value=1_000_000, step=100_000)

rebalance_freq = st.radio(
    "再平衡頻率 (策略靈魂)", 
    ["每年 (Yearly)", "每季 (Quarterly)", "不平衡 (Buy & Hold)"], 
    horizontal=True
)

###############################################################
# 回測核心邏輯
###############################################################

if st.button("開始回測 🚀", type="primary"):
    with st.spinner("正在模擬資產配置..."):
        # 1. 讀取數據
        df_re = load_csv(sym_re).loc[start_date:end_date]
        df_stk = load_csv(sym_stk).loc[start_date:end_date]
        df_bench = load_csv(sym_bench).loc[start_date:end_date]

        # ✨ 處理現金數據邏輯
        if sym_cash == "USD_CASH":
            df_cash = pd.DataFrame(index=df_stk.index)
            df_cash["Price"] = 1.0 # 純現金價格固定為 1
        else:
            df_cash = load_csv(sym_cash).loc[start_date:end_date]

        # 檢查資料完整性
        missing = []
        if df_re.empty: missing.append(sym_re)
        if df_stk.empty: missing.append(sym_stk)
        if df_cash.empty: missing.append(sym_cash)
        if df_bench.empty: missing.append(sym_bench)

        if missing:
            st.error(f"❌ 資料不足！請確認 data 資料夾內是否有: {', '.join(missing)}")
            st.stop()

        # 2. 合併資料
        df = pd.DataFrame(index=df_re.index)
        df["P_RE"] = df_re["Price"]
        df = df.join(df_stk["Price"].rename("P_STK"), how="inner")
        df = df.join(df_cash["Price"].rename("P_CASH"), how="inner")
        df = df.join(df_bench["Price"].rename("P_BENCH"), how="inner")
        
        # 計算個別資產日報酬
        df["Ret_RE"] = df["P_RE"].pct_change().fillna(0)
        df["Ret_STK"] = df["P_STK"].pct_change().fillna(0)
        df["Ret_CASH"] = df["P_CASH"].pct_change().fillna(0)
        df["Ret_BENCH"] = df["P_BENCH"].pct_change().fillna(0)

        # 3. 模擬回測
        dates = df.index
        holdings = {
            "RE": initial_capital / 3,
            "STK": initial_capital / 3,
            "CASH": initial_capital / 3
        }
        
        history_equity = []
        history_weights = []
        
        for i, d in enumerate(dates):
            # A. 計算當日資產變化
            if i > 0:
                holdings["RE"] *= (1 + df["Ret_RE"].iloc[i])
                holdings["STK"] *= (1 + df["Ret_STK"].iloc[i])
                holdings["CASH"] *= (1 + df["Ret_CASH"].iloc[i])
            
            total_equity = sum(holdings.values())
            
            # B. 判斷再平衡
            do_rebalance = False
            if rebalance_freq == "每年 (Yearly)":
                if i > 0 and d.year != dates[i-1].year:
                    do_rebalance = True
            elif rebalance_freq == "每季 (Quarterly)":
                if i > 0 and d.quarter != dates[i-1].quarter:
                    do_rebalance = True
            
            # C. 執行再平衡
            if do_rebalance:
                target_amount = total_equity / 3
                holdings["RE"] = target_amount
                holdings["STK"] = target_amount
                holdings["CASH"] = target_amount
            
            # D. 記錄
            history_equity.append(total_equity)
            history_weights.append([
                holdings["RE"]/total_equity, 
                holdings["STK"]/total_equity, 
                holdings["CASH"]/total_equity
            ])

        df["Equity_Talmud"] = history_equity
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret_BENCH"]).cumprod()
        
        w_arr = np.array(history_weights)
        df["W_RE"] = w_arr[:, 0]
        df["W_STK"] = w_arr[:, 1]
        df["W_CASH"] = w_arr[:, 2]

        # ---------------- KPI 計算 ----------------
        def calc_metrics(equity_series):
            total_ret = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1
            years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
            cagr = (1 + total_ret) ** (1/years) - 1 if years > 0 else 0
            mdd = (equity_series / equity_series.cummax() - 1).min()
            daily_ret = equity_series.pct_change().fillna(0)
            vol = daily_ret.std() * np.sqrt(252)
            sharpe = (cagr - 0.04) / vol if vol > 0 else 0
            return total_ret, cagr, mdd, vol, sharpe

        res_tal = calc_metrics(df["Equity_Talmud"])
        res_bench = calc_metrics(df["Equity_Benchmark"])

        # ---------------- 顯示結果 ----------------
        st.markdown("""
        <style>
            .kpi-card {
                background-color: var(--secondary-background-color);
                border-radius: 12px; padding: 15px; text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: 1px solid rgba(128,128,128,0.1);
            }
            .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--text-color); }
            .kpi-lbl { font-size: 0.9rem; opacity: 0.7; }
            .kpi-sub { font-size: 0.8rem; color: #666; margin-top: 5px; }
        </style>
        """, unsafe_allow_html=True)

        def kpi_html(label, val, bench_val, is_pct=False):
            val_str = f"{val:.2%}" if is_pct else f"${val:,.0f}"
            bench_str = f"{bench_val:.2%}" if is_pct else f"${bench_val:,.0f}"
            return f"""
            <div class="kpi-card">
                <div class="kpi-lbl">{label}</div>
                <div class="kpi-val">{val_str}</div>
                <div class="kpi-sub">基準: {bench_str}</div>
            </div>
            """

        row_kpi = st.columns(4)
        with row_kpi[0]: st.markdown(kpi_html("期末總資產", res_tal[0]*initial_capital + initial_capital, res_bench[0]*initial_capital + initial_capital), unsafe_allow_html=True)
        with row_kpi[1]: st.markdown(kpi_html("年化報酬 (CAGR)", res_tal[1], res_bench[1], True), unsafe_allow_html=True)
        with row_kpi[2]: st.markdown(kpi_html("最大回撤 (MDD)", res_tal[2], res_bench[2], True), unsafe_allow_html=True)
        with row_kpi[3]: st.markdown(kpi_html("波動率 (Risk)", res_tal[3], res_bench[3], True), unsafe_allow_html=True)

        st.markdown("---")

        st.markdown("### 📈 策略效益分析")
        tab1, tab2 = st.tabs(["資金成長曲線", "動態權重 (再平衡視覺化)"])

        with tab1:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Talmud"], name="塔木德策略", line=dict(color="#636EFA", width=3)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name=f"基準: {bench_label}", line=dict(color="#B0BEC5", width=2, dash='dash')))
            fig_eq.update_layout(template="plotly_white", height=450, hovermode="x unified", title=f"策略 vs {bench_label}", legend=dict(orientation="h", y=1.02, x=1, xanchor="right"))
            st.plotly_chart(fig_eq, use_container_width=True)

        with tab2:
            fig_w = go.Figure()
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_RE"], name=f"土地: {re_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(0, 204, 150, 0.5)'))
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_STK"], name=f"股票: {stk_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(239, 85, 59, 0.5)'))
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_CASH"], name=f"現金: {cash_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(99, 110, 250, 0.5)'))
            fig_w.update_layout(template="plotly_white", height=400, yaxis=dict(tickformat=".0%", range=[0, 1], title="資產權重"), hovermode="x unified", legend=dict(orientation="h"))
            st.plotly_chart(fig_w, use_container_width=True)

        st.markdown("### 📋 詳細數據")
        comparison_data = {
            "策略": ["塔木德策略", f"基準 ({bench_label})"],
            "總報酬率": [res_tal[0], res_bench[0]],
            "CAGR (年化)": [res_tal[1], res_bench[1]],
            "最大回撤 (MDD)": [res_tal[2], res_bench[2]],
            "年化波動率": [res_tal[3], res_bench[3]],
            "Sharpe Ratio": [res_tal[4], res_bench[4]]
        }
        df_comp = pd.DataFrame(comparison_data).set_index("策略")
        st.dataframe(
            df_comp.style
            .format("{:.2%}", subset=["總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動率"])
            .format("{:.2f}", subset=["Sharpe Ratio"])
            .background_gradient(cmap="RdYlGn", subset=["總報酬率", "CAGR (年化)", "Sharpe Ratio"]),
            use_container_width=True
        )
