###############################################################
# app.py — 0050 雙向乖離 (三模式最佳化：CAGR / Calmar / MDD)
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

###############################################################
# 1. 環境設定與字型
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
st.set_page_config(page_title="0050 雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

###############################################################
# 2. 核心計算與統計函數
###############################################################

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

# --- 最佳化專用高速引擎 (Numpy 加速版) ---
def run_fast_backtest(df_raw, dca_bias, dca_p, dca_c, arb_bias, arb_p, arb_c):
    p_base, ma_val, bias_val = df_raw["Price_base"].values, df_raw["MA"].values, df_raw["Bias"].values * 100
    price_lev = df_raw["Price_lev"].values
    
    pos = np.zeros(len(df_raw))
    curr_pos = 1.0 
    pos[0] = curr_pos
    dca_wait, arb_wait = 0, 0
    
    for i in range(1, len(df_raw)):
        if dca_wait > 0: dca_wait -= 1
        if arb_wait > 0: arb_wait -= 1
        p, m, b = p_base[i], ma_val[i], bias_val[i]
        p0, m0 = p_base[i-1], ma_val[i-1]
        
        if p > m:
            if p0 <= m0: curr_pos = 1.0 # 站上均線
            if arb_bias != 0 and b >= arb_bias and arb_wait == 0 and curr_pos > 0:
                curr_pos = max(0.0, curr_pos - (arb_p / 100.0))
                arb_wait = arb_c
            dca_wait = 0
        else:
            if p0 > m0: curr_pos, arb_wait = 0.0, 0 # 跌破均線
            elif curr_pos < 1.0:
                if b <= dca_bias and dca_wait == 0:
                    curr_pos = min(1.0, curr_pos + (dca_p / 100.0))
                    dca_wait = dca_c
        pos[i] = curr_pos

    # 計算淨值與回撤
    equity = np.ones(len(df_raw))
    for i in range(1, len(df_raw)):
        ret = (price_lev[i] / price_lev[i-1]) - 1
        equity[i] = equity[i-1] * (1 + (ret * pos[i-1]))
    
    y = (df_raw.index[-1] - df_raw.index[0]).days / 365
    cagr = (equity[-1])**(1/y) - 1 if y > 0 else 0
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    mdd = np.abs(np.min(drawdown))
    
    return cagr, mdd, (cagr / mdd if mdd > 0 else 0)

###############################################################
# 3. UI 介面與數據加載
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 雙向乖離最佳化戰情室</h1>", unsafe_allow_html=True)

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {"00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW"}

def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

c1, c2 = st.columns(2)
base_label = c1.selectbox("訊號源 (原型)", list(BASE_ETFS.keys()))
lev_label = c2.selectbox("交易標的 (槓桿)", list(LEV_ETFS.keys()))

df_base_raw = load_csv(BASE_ETFS[base_label])
df_lev_raw = load_csv(LEV_ETFS[lev_label])

if df_base_raw.empty or df_lev_raw.empty:
    st.error("⚠️ CSV 資料讀取失敗，請確認 data 資料夾。"); st.stop()

s_min = max(df_base_raw.index.min().date(), df_lev_raw.index.min().date())
s_max = min(df_base_raw.index.max().date(), df_lev_raw.index.max().date())

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 5000000, 100000)
sma_window = col_p4.number_input("SMA 週期", 10, 240, 200)

tab_demo, tab_opt = st.tabs(["🚀 策略展示與回測", "🧬 最佳化跑分 (Three-Way)"])

###############################################################
# Tab 1: 原有細節回測 (略，保持您之前的視覺化邏輯)
###############################################################
with tab_demo:
    st.info("此分頁用於單組參數的視覺化對照。請在下方最佳化分頁找到參數後回到此處測試。")

###############################################################
# Tab 2: 三模式最佳化
###############################################################
with tab_opt:
    st.write("### 🧬 全方位參數搜尋引擎")
    
    # 選擇最佳化目標
    opt_goal = st.radio(
        "🏆 最佳化導向選擇",
        ["追求最大報酬 (CAGR Focus)", "追求最高性價比 (Calmar Ratio)", "追求最小風險 (Min MDD)"],
        horizontal=True,
        help="最大報酬：追求絕對獲利。性價比：追求穩定增長。最小風險：追求抗震防禦。"
    )

    with st.expander("🛠️ 定義跑分網格區間", expanded=True):
        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("**📉 負乖離加碼區**")
            opt_db = st.multiselect("加碼門檻 (%)", [-10, -15, -20, -25], default=[-15, -20])
            opt_dp = st.multiselect("每次加碼比例 (%)", [20, 33, 50], default=[33, 50])
            opt_dc = st.multiselect("加碼冷卻天數", [10, 20, 40], default=[20])
        with oc2:
            st.markdown("**🚀 正乖離套利區**")
            opt_ab = st.multiselect("套利門檻 (%)", [25, 35, 45, 55], default=[35, 45])
            opt_ap = st.multiselect("每次減碼比例 (%)", [50, 100], default=[100])
            opt_ac = st.multiselect("套利冷卻天數", [10, 20, 40], default=[20])

    if st.button("啟動跑分網格 🧬"):
        # 1. 數據對齊
        df_opt = pd.DataFrame(index=df_base_raw.index)
        df_opt["Price_base"] = df_base_raw["Price"]
        df_opt = df_opt.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
        df_opt["MA"] = df_opt["Price_base"].rolling(sma_window).mean()
        df_opt["Bias"] = (df_opt["Price_base"] - df_opt["MA"]) / df_opt["MA"]
        df_opt = df_opt.dropna(subset=["MA"]).loc[start:end]
        
        # 2. 生成組合
        combs = list(product(opt_db, opt_dp, opt_dc, opt_ab, opt_ap, opt_ac))
        total = len(combs)
        results = []
        progress = st.progress(0); status = st.empty()
        
        # 3. 跑分循環
        for idx, (db, dp, dc, ab, ap, ac) in enumerate(combs):
            status.text(f"計算中: {idx+1}/{total}...")
            c, m, clm = run_fast_backtest(df_opt, db, dp, dc, ab, ap, ac)
            results.append({
                "加碼門檻": db, "加碼%": dp, "加碼CD": dc,
                "套利門檻": ab, "套利%": ap, "套利CD": ac,
                "CAGR": c, "MDD": m, "Calmar": clm
            })
            progress.progress((idx + 1) / total)
            
        status.success(f"✅ 完成 {total} 組模擬！")
        
        # 4. 多重排序邏輯
        res_df = pd.DataFrame(results)
        if "最大報酬" in opt_goal:
            sort_key, asc = "CAGR", False
        elif "性價比" in opt_goal:
            sort_key, asc = "Calmar", False
        else: # 最小風險
            sort_key, asc = "MDD", True
            
        top_df = res_df.sort_values(by=sort_key, ascending=asc).head(15)
        
        # 5. 數據呈現
        st.write(f"#### 🏆 最佳組合排行榜 (按 {sort_key} 優先排序)")
        st.dataframe(top_df.style.format({
            "CAGR": "{:.2%}", "MDD": "{:.2%}", "Calmar": "{:.3f}"
        }), use_container_width=True)
        
        # 6. 視覺化分析
        if "最小風險" in opt_goal:
            st.write("#### 🛡️ 低風險組合分佈 (按 MDD 排序)")
            fig = px.bar(top_df, x=top_df.index.astype(str), y="MDD", color="MDD",
                         title="低回撤組合排名 (數值越低越安全)", color_continuous_scale="RdYlGn_r",
                         hover_data=["加碼門檻", "套利門檻"])
            st.plotly_chart(fig, use_container_width=True)
        elif "最大報酬" in opt_goal:
            st.write("#### 📊 高報酬組合分佈 (按 CAGR 排序)")
            fig = px.bar(top_df, x=top_df.index.astype(str), y="CAGR", color="CAGR",
                         title="高年化報酬排名 (數值越高賺越多)", color_continuous_scale="Plasma")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("#### 📈 性價比分佈圖 (Efficiency Frontier)")
            fig = px.scatter(res_df, x="MDD", y="CAGR", size="Calmar", color="Calmar",
                             title="風險 vs 報酬分析 (右上或左上之大型球體為優選)", color_continuous_scale="Viridis")
            st.plotly_chart(fig, use_container_width=True)

# Footer
st.markdown("<br><hr><div style='text-align:center; color:gray; font-size:0.8rem;'>Copyright © 2025 hamr-lab.com | 0050 雙向乖離系統專屬版</div>", unsafe_allow_html=True)
