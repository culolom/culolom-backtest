###############################################################
# pages/3_Talmud_Strategy.py — 塔木德策略 (Talmud Strategy)
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

# ------------------------------------------------------
# 資料設定
# ------------------------------------------------------

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
    "QLD (兩倍做多QQQ)": "QLD",
    "TQQQ (三倍做多QQQ)": "TQQQ",
    "0050.TW (台灣50)": "0050.TW"
}

ASSETS_CASH = {
    "TBIL (3個月國債)": "TBIL", 
    "BIL (1-3月國債)": "BIL", 
    "SHV (短期國債)": "SHV", 
    "VGSH (短期公債)": "VGSH",
    "IEF (7-10年公債)": "IEF"
}

# 定義「對照組」清單 (通常是大盤指數)
ASSETS_BENCHMARK = {
    "SPY (標普500)": "SPY",
    "QQQ (納斯達克100)": "QQQ",
    "VT (全球股市)": "VT",
    "0050.TW (台灣50)": "0050.TW",
    "VTI (全美股市)": "VTI"
}

# 2. 讀取 CSV (相容模式)
def load_csv(symbol: str) -> pd.DataFrame:
    # 處理可能帶有 .TW 的檔名問題
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
        
        # 優先找 Adj Close
        if "Adj Close" in df.columns:
            df["Price"] = df["Adj Close"]
        elif "Close" in df.columns:
            df["Price"] = df["Close"]
        else:
            return pd.DataFrame()
            
        return df[["Price"]]
    except Exception:
        return pd.DataFrame()

# 3. 取得共同日期區間
def get_common_range(sym_list):
    dfs = []
    for s in sym_list:
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

st.markdown("<h1 style='margin-bottom:0.1em;'>⚖️ 塔木德資產配置 (Talmud Strategy)</h1>", unsafe_allow_html=True)
st.caption("策略核心：將資產分為「不動產、股票、現金」三等份，定期再平衡 (Rebalance) 實現高出低進。")

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
    # 👇 新增：對照組選擇
    bench_label = st.selectbox("📊 比較基準 (Benchmark)", list(ASSETS_BENCHMARK.keys()), index=0)
    sym_bench = ASSETS_BENCHMARK[bench_label]

# 計算日期範圍 (包含對照組)
s_min, s_max = get_common_range([sym_re, sym_stk, sym_cash, sym_bench])

col_d1, col_d2, col_d3 = st.columns(3)
with col_d1:
    start_date = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=365*5)), min_value=s_min, max_value=s_max)
with col_d2:
    end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col_d3:
    rebalance_freq = st.selectbox("再平衡頻率", ["每年 (Yearly)", "每季 (Quarterly)", "不平衡 (Buy & Hold)"], index=0)

initial_capital = 1_000_000 # 固定本金方便計算，顯示時再調整

###############################################################
# 回測核心邏輯
###############################################################

if st.button("開始回測 🚀", type="primary", use_container_width=True):
    with st.spinner("正在模擬資產配置與基準比較..."):
        # 1. 讀取數據
        df_re = load_csv(sym_re).loc[start_date:end_date]
        df_stk = load_csv(sym_stk).loc[start_date:end_date]
        df_cash = load_csv(sym_cash).loc[start_date:end_date]
        df_bench = load_csv(sym_bench).loc[start_date:end_date]

        # 檢查資料完整性
        missing = []
        if df_re.empty: missing.append(sym_re)
        if df_stk.empty: missing.append(sym_stk)
        if df_cash.empty: missing.append(sym_cash)
        if df_bench.empty: missing.append(sym_bench)
        
        if missing:
            st.error(f"❌ 資料不足，無法執行回測！缺少的 CSV: {', '.join(missing)}")
            st.stop()

        # 2. 合併資料 (取交集)
        df = pd.DataFrame(index=df_re.index)
        df["P_RE"] = df_re["Price"]
        df = df.join(df_stk["Price"].rename("P_STK"), how="inner")
        df = df.join(df_cash["Price"].rename("P_CASH"), how="inner")
        df = df.join(df_bench["Price"].rename("P_BENCH"), how="inner")
        
        # 計算日報酬
        df["Ret_RE"] = df["P_RE"].pct_change().fillna(0)
        df["Ret_STK"] = df["P_STK"].pct_change().fillna(0)
        df["Ret_CASH"] = df["P_CASH"].pct_change().fillna(0)
        df["Ret_BENCH"] = df["P_BENCH"].pct_change().fillna(0)

        # 3. 模擬回測 (塔木德策略)
        dates = df.index
        # 初始化：資金均分三份
        holdings = {
            "RE": initial_capital / 3,
            "STK": initial_capital / 3,
            "CASH": initial_capital / 3
        }
        
        history_equity = []     # 記錄總資產
        history_weights = []    # 記錄權重分佈
        
        for i, d in enumerate(dates):
            # A. 計算當日資產變化
            if i > 0:
                holdings["RE"] *= (1 + df["Ret_RE"].iloc[i])
                holdings["STK"] *= (1 + df["Ret_STK"].iloc[i])
                holdings["CASH"] *= (1 + df["Ret_CASH"].iloc[i])
            
            total_equity = sum(holdings.values())
            
            # B. 判斷是否需要再平衡
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

        # 4. 整理結果 DataFrame
        df["Equity_Talmud"] = history_equity
        # 計算基準組 (Buy & Hold) 績效
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret_BENCH"]).cumprod()
        
        # 權重拆解
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
            sharpe = (cagr - 0.04) / vol if vol > 0 else 0 # 假設無風險 4%
            return total_ret, cagr, mdd, vol, sharpe

        res_tal = calc_metrics(df["Equity_Talmud"])
        res_bench = calc_metrics(df["Equity_Benchmark"])

        # ==========================================================
        # 顯示結果
        # ==========================================================

        # CSS 樣式
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
            .pos { color: #21c354; font-weight: bold; }
            .neg { color: #ff3c3c; font-weight: bold; }
        </style>
        """, unsafe_allow_html=True)

        def kpi_html(label, val, bench_val, is_pct=False):
            val_str = f"{val:.2%}" if is_pct else f"${val:,.0f}"
            bench_str = f"{bench_val:.2%}" if is_pct else f"${bench_val:,.0f}"
            
            # 計算差異顏色
            diff = val - bench_val
            color_class = "pos" if diff > 0 else "neg"
            # MDD 和 波動率 是越小越好，邏輯相反
            if "回撤" in label or "波動" in label:
                color_class = "pos" if diff < 0 else "neg"
                
            return f"""
            <div class="kpi-card">
                <div class="kpi-lbl">{label}</div>
                <div class="kpi-val">{val_str}</div>
                <div class="kpi-sub">基準: {bench_str}</div>
            </div>
            """

        # 1. KPI 卡片
        row_kpi = st.columns(4)
        with row_kpi[0]: st.markdown(kpi_html("期末總資產", res_tal[0]*initial_capital + initial_capital, res_bench[0]*initial_capital + initial_capital), unsafe_allow_html=True)
        with row_kpi[1]: st.markdown(kpi_html("年化報酬 (CAGR)", res_tal[1], res_bench[1], True), unsafe_allow_html=True)
        with row_kpi[2]: st.markdown(kpi_html("最大回撤 (MDD)", res_tal[2], res_bench[2], True), unsafe_allow_html=True)
        with row_kpi[3]: st.markdown(kpi_html("波動率 (Risk)", res_tal[3], res_bench[3], True), unsafe_allow_html=True)

        st.markdown("---")

        # 2. 資金曲線圖
        st.markdown("### 📈 績效走勢圖")
        tab1, tab2 = st.tabs(["💰 資金成長比較", "🥧 動態權重變化"])

        with tab1:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Talmud"], name="塔木德策略", line=dict(color="#636EFA", width=3)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name=f"基準: {bench_label}", line=dict(color="#B0BEC5", width=2, dash='dash')))
            
            fig_eq.update_layout(
                template="plotly_white", 
                height=450, 
                hovermode="x unified", 
                title_text=f"策略 vs {bench_label} 累積報酬",
                legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right")
            )
            st.plotly_chart(fig_eq, use_container_width=True)

        with tab2:
            st.caption("💡 觀察重點：當某一資產價格大漲，權重會超過 33%，再平衡機制會將其賣出並買入落後資產。")
            fig_w = go.Figure()
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_RE"], name=f"土地: {re_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(0, 204, 150, 0.6)'))
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_STK"], name=f"股票: {stk_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(239, 85, 59, 0.6)'))
            fig_w.add_trace(go.Scatter(x=df.index, y=df["W_CASH"], name=f"現金: {cash_label}", stackgroup='one', line=dict(width=0), fillcolor='rgba(99, 110, 250, 0.6)'))
            
            fig_w.update_layout(
                template="plotly_white", 
                height=400, 
                yaxis=dict(tickformat=".0%", range=[0, 1], title="資產配置比例"), 
                hovermode="x unified",
                legend=dict(orientation="h", y=-0.1)
            )
            st.plotly_chart(fig_w, use_container_width=True)

        # 3. 詳細數據表格
        st.markdown("### 📋 詳細數據")
        
        comparison_data = {
            "策略名稱": ["塔木德策略", f"基準 ({bench_label})"],
            "總報酬率": [res_tal[0], res_bench[0]],
            "CAGR (年化)": [res_tal[1], res_bench[1]],
            "最大回撤 (MDD)": [res_tal[2], res_bench[2]],
            "年化波動率": [res_tal[3], res_bench[3]],
            "Sharpe Ratio": [res_tal[4], res_bench[4]]
        }
        df_comp = pd.DataFrame(comparison_data).set_index("策略名稱")
        
        st.dataframe(
            df_comp.style
            .format("{:.2%}", subset=["總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動率"])
            .format("{:.2f}", subset=["Sharpe Ratio"])
            .background_gradient(cmap="RdYlGn", subset=["總報酬率", "CAGR (年化)", "Sharpe Ratio"])
            .background_gradient(cmap="RdYlGn_r", subset=["最大回撤 (MDD)", "年化波動率"]),
            use_container_width=True
        )
