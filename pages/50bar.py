###############################################################
# app.py — 0050 雙向乖離動態槓桿 (內建最佳化功能版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import sys
from itertools import product

# --- 環境設定 ---
font_path = "./NotoSansTC-Bold.ttf"
st.set_page_config(page_title="0050 雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (保持原樣)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

# --- 核心計算函數 ---
def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std, downside = daily.mean(), daily.std(), daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def get_stats(eq, rets, y):
    f_eq = eq.iloc[-1]
    f_ret = f_eq - 1
    cagr = (1 + f_ret)**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq / eq.cummax()).min()
    v, sh, so = calc_metrics(rets)
    calmar = cagr / mdd if mdd > 0 else 0
    return f_eq, f_ret, cagr, mdd, v, sh, so, calmar

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"

# --- 資料讀取 ---
def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

# --- 最佳化專用回測引擎 (高速版) ---
def run_fast_backtest(df_raw, dca_p, dca_c, arb_p, arb_c, dca_bias, arb_bias):
    p_base = df_raw["Price_base"].values
    ma_val = df_raw["MA"].values
    bias_val = df_raw["Bias"].values * 100
    price_lev = df_raw["Price_lev"].values
    
    sigs, pos = [0] * len(df_raw), [0.0] * len(df_raw)
    curr_pos = 1.0 # 預設一開局全倉
    pos[0] = curr_pos
    dca_wait, arb_wait = 0, 0
    
    for i in range(1, len(df_raw)):
        if dca_wait > 0: dca_wait -= 1
        if arb_wait > 0: arb_wait -= 1
        p, m, b = p_base[i], ma_val[i], bias_val[i]
        p0, m0 = p_base[i-1], ma_val[i-1]
        
        if p > m:
            if p0 <= m0: curr_pos = 1.0
            if b >= arb_bias and arb_wait == 0 and curr_pos > 0:
                curr_pos = max(0.0, curr_pos - (arb_p / 100.0))
                arb_wait = arb_c
            dca_wait = 0
        else:
            if p0 > m0: curr_pos, arb_wait = 0.0, 0
            elif curr_pos < 1.0:
                if b <= dca_bias and dca_wait == 0:
                    curr_pos = min(1.0, curr_pos + (dca_p / 100.0))
                    dca_wait = dca_c
        pos[i] = curr_pos

    equity = [1.0]
    for i in range(1, len(df_raw)):
        ret = (price_lev[i] / price_lev[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * pos[i-1])))
    
    eq_s = pd.Series(equity)
    y = (df_raw.index[-1] - df_raw.index[0]).days / 365
    cagr = (1 + (eq_s.iloc[-1]-1))**(1/y) - 1
    mdd = 1 - (eq_s / eq_s.cummax()).min()
    return cagr, mdd, (cagr / mdd if mdd > 0 else 0)

# --- UI Sidebar ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 雙向乖離動態槓桿系統</h1>", unsafe_allow_html=True)

# --- 參數設定區 ---
BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {"00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW"}

col1, col2 = st.columns(2)
base_label = col1.selectbox("趨勢訊號源 (原型)", list(BASE_ETFS.keys()))
lev_label = col2.selectbox("實際交易標的 (槓桿)", list(LEV_ETFS.keys()))

df_base_raw = load_csv(BASE_ETFS[base_label])
df_lev_raw = load_csv(LEV_ETFS[lev_label])
s_min, s_max = df_base_raw.index.min().date(), df_base_raw.index.max().date()

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 5000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

# --- Tabs 設計 ---
tab_backtest, tab_optimize = st.tabs(["🚀 策略回測展示", "🧬 參數最佳化 (Optimizer)"])

# ------------------------------------------------------
# Tab 1: 策略回測 (原有功能)
# ------------------------------------------------------
with tab_backtest:
    st.write("### ⚙️ 單組參數手動測試")
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        d_bias = st.number_input("加碼觸發乖離率 (%)", -30.0, 0.0, -15.0)
        d_pct = st.number_input("每次加碼比例 (%)", 5, 100, 20)
        d_cd = st.slider("加碼冷卻天數", 1, 60, 10)
    with c_set2:
        a_bias = st.number_input("套利觸發乖離率 (%)", 0.0, 100.0, 35.0)
        a_pct = st.number_input("每次減碼比例 (%)", 5, 100, 100)
        a_cd = st.slider("套利冷卻天數", 1, 60, 10)

    if st.button("執行單組回測"):
        # 此處放置您原本 app.py 內部的回測繪圖與 KPI 顯示邏輯 (略，已與之前一致)
        st.info("請參考原本回測邏輯...")

# ------------------------------------------------------
# Tab 2: 參數最佳化 (新功能)
# ------------------------------------------------------
with tab_optimize:
    st.markdown("""
    ### 🧬 自動尋找最佳參數組合
    系統將針對您設定的範圍進行 **Grid Search (網格搜索)**，並以 **Calmar Ratio (性價比)** 排序。
    """)
    
    with st.expander("🔍 定義最佳化搜尋空間 (建議不要設太多組以免跑太久)", expanded=True):
        co1, co2 = st.columns(2)
        with co1:
            opt_dca_pcts = st.multiselect("加碼比例範圍 (%)", [10, 20, 25, 33, 50], default=[20, 33, 50])
            opt_dca_cds = st.multiselect("加碼冷卻天數範圍", [5, 10, 20, 30, 40], default=[10, 20])
        with co2:
            opt_arb_pcts = st.multiselect("套利比例範圍 (%)", [20, 50, 80, 100], default=[50, 100])
            opt_arb_cds = st.multiselect("套利冷卻天數範圍", [5, 10, 20, 30], default=[10, 20])
            
    if st.button("開始跑分 🧬 (Grid Search)"):
        # 1. 預處理資料 (只做一次)
        df = df_base_raw.copy()
        df["Price_base"] = df_base_raw["Price"]
        df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
        df["MA"] = df["Price_base"].rolling(sma_window).mean()
        df["Bias"] = (df["Price_base"] - df["MA"]) / df["MA"]
        df = df.dropna(subset=["MA"]).loc[start:end]
        
        # 2. 建立參數組合
        combs = list(product(opt_dca_pcts, opt_dca_cds, opt_arb_pcts, opt_arb_cds))
        total = len(combs)
        results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 3. 跑分循環
        for idx, (dp, dc, ap, ac) in enumerate(combs):
            status_text.text(f"正在計算第 {idx+1}/{total} 組參數...")
            c, m, clm = run_fast_backtest(df, dp, dc, ap, ac, d_bias, a_bias)
            results.append({
                "加碼%": dp, "加碼CD": dc, "套利%": ap, "套利CD": ac,
                "CAGR": c, "MDD": m, "Calmar": clm
            })
            progress_bar.progress((idx + 1) / total)
            
        status_text.success(f"✅ 最佳化完成！總共跑完 {total} 組組合。")
        
        # 4. 顯示結果表格
        res_df = pd.DataFrame(results).sort_values(by="Calmar", ascending=False)
        
        st.write("#### 🏆 最佳化排行榜 (Top 10)")
        styled_df = res_df.head(10).style.format({
            "CAGR": "{:.2%}", "MDD": "{:.2%}", "Calmar": "{:.3f}"
        })
        st.dataframe(styled_df, use_container_width=True)
        
        # 5. 視覺化分析：風險與報酬譜系圖
        st.write("#### 📊 參數效能分佈圖 (Risk-Return Spectrum)")
        fig_scatter = px.scatter(
            res_df, x="MDD", y="CAGR", color="Calmar",
            size="Calmar", hover_data=["加碼%", "加碼CD", "套利%", "套利CD"],
            title="各參數組合之風險回撤與報酬分佈 (越靠近左上角越強)",
            labels={"MDD": "最大回撤 (Risk)", "CAGR": "年化報酬 (Reward)"},
            color_continuous_scale="Viridis"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

# ------------------------------------------------------
# Footer (保持原樣)
# ------------------------------------------------------
st.markdown("<br><hr>", unsafe_allow_html=True)
st.markdown("<div style='text-align: center; color: gray; font-size: 0.85rem;'>Copyright © 2025 hamr-lab.com. All rights reserved.</div>", unsafe_allow_html=True)
