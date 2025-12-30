###############################################################
# app.py — 0050 雙向乖離動態槓桿 (全參數網格搜尋版)
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

# --- 1. 環境與字型設定 ---
font_path = "./NotoSansTC-Bold.ttf"
st.set_page_config(page_title="0050 雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

# --- 2. 核心計算函數 ---
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

def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"

# --- 3. 最佳化專用高速引擎 (優化運算速度) ---
def run_fast_backtest(df_raw, dca_bias, dca_p, dca_c, arb_bias, arb_p, arb_c):
    p_base, ma_val, bias_val = df_raw["Price_base"].values, df_raw["MA"].values, df_raw["Bias"].values * 100
    price_lev = df_raw["Price_lev"].values
    
    pos = np.zeros(len(df_raw))
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
    last_eq = 1.0
    for i in range(1, len(df_raw)):
        ret = (price_lev[i] / price_lev[i-1]) - 1
        last_eq = last_eq * (1 + (ret * pos[i-1]))
        equity.append(last_eq)
    
    eq_s = pd.Series(equity)
    y = (df_raw.index[-1] - df_raw.index[0]).days / 365
    cagr = (1 + (eq_s.iloc[-1]-1))**(1/y) - 1
    mdd = 1 - (eq_s / eq_s.cummax()).min()
    return cagr, mdd, (cagr / mdd if mdd > 0 else 0)

# --- 4. 資料讀取 ---
def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

# --- 5. UI 介面 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 雙向乖離最佳化戰情室</h1>", unsafe_allow_html=True)

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

tab_demo, tab_opt = st.tabs(["🚀 策略細部展示", "🧬 全參數最佳化 (Optimizer)"])

# ------------------------------------------------------
# Tab 1: 策略展示 (原本的功能)
# ------------------------------------------------------
with tab_demo:
    # ... (此處保留您原本繪製雙軸圖、KPI卡片、分頁、以及帶獎盃表格的邏輯)
    st.info("此分頁用於單組參數的深度視覺化觀察。")

# ------------------------------------------------------
# Tab 2: 全參數最佳化 (網格搜尋增強版)
# ------------------------------------------------------
with tab_opt:
    st.write("### 🧪 網格搜尋範圍設定")
    
    with st.expander("🛠️ 定義測試網格 (注意：組合數過多會延長計算時間)", expanded=True):
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            st.markdown("**📉 負乖離加碼參數**")
            opt_dca_bias = st.multiselect("加碼觸發門檻 (%)", [-5, -10, -15, -20, -25], default=[-15])
            opt_dca_pcts = st.multiselect("加碼比例 (%)", [10, 20, 33, 50], default=[20, 33])
            opt_dca_cds = st.multiselect("加碼冷卻 (天)", [5, 10, 20, 40], default=[10])
        with row1_col2:
            st.markdown("**🚀 正乖離套利參數**")
            opt_arb_bias = st.multiselect("套利觸發門檻 (%)", [15, 25, 35, 45, 55], default=[35])
            opt_arb_pcts = st.multiselect("套利比例 (%)", [20, 50, 100], default=[100])
            opt_arb_cds = st.multiselect("套利冷卻 (天)", [5, 10, 20, 40], default=[10])

    if st.button("開始跑分 🧬 (Execute Grid Search)"):
        # 1. 準備資料
        df = df_base_raw.copy()
        df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
        df["MA"] = df["Price_base"].rolling(sma_window).mean()
        df["Bias"] = (df["Price_base"] - df["MA"]) / df["MA"]
        df = df.dropna(subset=["MA"]).loc[start:end]
        
        # 2. 建立參數組合
        combs = list(product(opt_dca_bias, opt_dca_pcts, opt_dca_cds, opt_arb_bias, opt_arb_pcts, opt_arb_cds))
        total = len(combs)
        results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 3. 執行網格運算
        for idx, (db, dp, dc, ab, ap, ac) in enumerate(combs):
            status_text.text(f"計算進度: {idx+1}/{total} 組組合...")
            c, m, clm = run_fast_backtest(df, db, dp, dc, ab, ap, ac)
            results.append({
                "加碼門檻%": db, "加碼%": dp, "加碼CD": dc,
                "套利門檻%": ab, "套利%": ap, "套利CD": ac,
                "CAGR": c, "MDD": m, "Calmar": clm
            })
            progress_bar.progress((idx + 1) / total)
            
        status_text.success(f"✅ 最佳化完成！已完成 {total} 組參數模擬。")
        
        # 4. 結果展現
        res_df = pd.DataFrame(results).sort_values(by="Calmar", ascending=False)
        
        st.write("#### 🏆 策略性價比排行榜 (Top 10)")
        st.dataframe(res_df.head(10).style.format({
            "CAGR": "{:.2%}", "MDD": "{:.2%}", "Calmar": "{:.3f}"
        }), use_container_width=True)
        
        # 5. 視覺化分析：門檻與效能的關係
        st.write("#### 📊 乖離率門檻效能分佈 (Bubble Chart)")
        fig_scatter = px.scatter(
            res_df, x="MDD", y="CAGR", color="加碼門檻%", 
            symbol="套利門檻%", size="Calmar",
            hover_data=["加碼%", "套利%"],
            title="各門檻組合之風險與回報 (球越大代表 Calmar Ratio 越高)",
            labels={"MDD": "最大回撤 (%)", "CAGR": "年化報酬 (%)"},
            color_continuous_scale="RdYlGn"
        )
        fig_scatter.update_layout(template="plotly_white")
        st.plotly_chart(fig_scatter, use_container_width=True)

# ------------------------------------------------------
# 8. Footer (保持專業宣告)
# ------------------------------------------------------
st.markdown("<br><hr>", unsafe_allow_html=True)
st.markdown("<div style='text-align: center; color: gray; font-size: 0.85rem;'>Copyright © 2025 hamr-lab.com. All rights reserved.</div>", unsafe_allow_html=True)
