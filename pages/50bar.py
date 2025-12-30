###############################################################
# app.py — 0050 雙向乖離動態槓桿 (修正 KeyError 與 全參數跑分)
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
# 1. 字型與驗證設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm_font = "Noto Sans TC"
else:
    fm_font = "Microsoft JhengHei"

st.set_page_config(page_title="0050 雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

###############################################################
# 2. 核心計算函數
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

# --- 最佳化專用高速引擎 (優化運算速度) ---
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
            can_buy_perm = True
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
    cagr = (1 + (eq_s.iloc[-1]-1))**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq_s / eq_s.cummax()).min()
    return cagr, mdd, (cagr / mdd if mdd > 0 else 0)

###############################################################
# 3. UI 與 資料讀取
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 雙向乖離動態槓桿系統</h1>", unsafe_allow_html=True)

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW", "00685L 群益台灣加權正2": "00685L.TW",
}

def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

col1, col2 = st.columns(2)
base_label = col1.selectbox("原型 ETF (趨勢訊號源)", list(BASE_ETFS.keys()))
lev_label = col2.selectbox("槓桿 ETF (實際交易標的)", list(LEV_ETFS.keys()))

df_base_raw = load_csv(BASE_ETFS[base_label])
df_lev_raw = load_csv(LEV_ETFS[lev_label])

if df_base_raw.empty or df_lev_raw.empty:
    st.error("⚠️ CSV 數據讀取失敗，請確認 data 資料夾路徑。")
    st.stop()

s_min = max(df_base_raw.index.min().date(), df_lev_raw.index.min().date())
s_max = min(df_base_raw.index.max().date(), df_lev_raw.index.max().date())

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 5000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

tab_demo, tab_opt = st.tabs(["🚀 策略展示 (單組回測)", "🧬 跑分最佳化 (Grid Search)"])

###############################################################
# Tab 1: 策略展示
###############################################################
with tab_demo:
    col_set1, col_set2 = st.columns(2)
    with col_set1:
        with st.expander("📉 負乖離加碼設定", expanded=True):
            enable_dca = st.toggle("啟用 DCA", value=True, key="dca_t1")
            d_bias = st.number_input("加碼觸發乖離率 (%)", max_value=0.0, value=-15.0)
            d_pct = st.number_input("每次加碼比例 (%)", 1, 100, 20)
            d_cd = st.slider("加碼冷卻天數", 1, 60, 10)
    with col_set2:
        with st.expander("🚀 高位套利減碼設定", expanded=True):
            enable_arb = st.toggle("啟用套利", value=False, key="arb_t1")
            a_bias = st.number_input("套利觸發乖離率 (%)", min_value=0.0, value=35.0)
            a_pct = st.number_input("每次減碼比例 (%)", 1, 100, 100)
            a_cd = st.slider("套利冷卻天數", 1, 60, 10)

    if st.button("啟動單組回測展示"):
        # 資料合併與處理
        start_buf = start - dt.timedelta(days=int(sma_window * 2))
        df = pd.DataFrame(index=df_base_raw.index)
        df["Price_base"] = df_base_raw["Price"]
        df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
        df["MA"] = df["Price_base"].rolling(sma_window).mean()
        df["Bias"] = (df["Price_base"] - df["MA"]) / df["MA"]
        df = df.dropna(subset=["MA"]).loc[start:end]

        # 策略運算
        sigs, pos = [0] * len(df), [0.0] * len(df)
        curr_pos = 1.0; pos[0] = curr_pos; dca_cd, arb_cd = 0, 0
        for i in range(1, len(df)):
            p, m, b = df["Price_base"].iloc[i], df["MA"].iloc[i], df["Bias"].iloc[i]*100
            p0, m0 = df["Price_base"].iloc[i-1], df["MA"].iloc[i-1]
            if dca_cd > 0: dca_cd -= 1
            if arb_cd > 0: arb_cd -= 1
            sig = 0
            if p > m:
                if p0 <= m0: curr_pos = 1.0; sig = 1
                if enable_arb and b >= a_bias and arb_cd == 0 and curr_pos > 0:
                    curr_pos = max(0.0, curr_pos - (a_pct / 100.0)); sig, arb_cd = 3, a_cd
            else:
                if p0 > m0: curr_pos, sig, arb_cd = 0.0, -1, 0
                elif enable_dca and curr_pos < 1.0:
                    if b <= d_bias and dca_cd == 0:
                        curr_pos = min(1.0, curr_pos + (d_pct / 100.0)); sig, dca_cd = 2, d_cd
            pos[i], sigs[i] = curr_pos, sig
        df["Signal"], df["Position"] = sigs, pos

        # 資金曲線
        equity = [1.0]
        for i in range(1, len(df)):
            r = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
            equity.append(equity[-1] * (1 + (r * df["Position"].iloc[i-1])))
        df["Equity_LRS"] = equity
        df["Equity_BH_Lev"] = df["Price_lev"] / df["Price_lev"].iloc[0]
        df["Equity_BH_Base"] = df["Price_base"] / df["Price_base"].iloc[0]
        
        # 繪圖與結果 (補回 KPI 與高級表格)
        y_len = (df.index[-1] - df.index[0]).days / 365
        sl, sv, sb = get_stats(df["Equity_LRS"], df["Equity_LRS"].pct_change(), y_len), \
                     get_stats(df["Equity_BH_Lev"], df["Equity_BH_Lev"].pct_change(), y_len), \
                     get_stats(df["Equity_BH_Base"], df["Equity_BH_Base"].pct_change(), y_len)

        st.markdown("""<style>.kpi-card {background: var(--secondary-background-color); border-radius: 16px; padding: 20px; text-align:center; border: 1px solid rgba(128,128,128,0.1);} .kpi-val {font-size:2rem; font-weight:900;}</style>""", unsafe_allow_html=True)
        kc = st.columns(4)
        kc[0].markdown(f'<div class="kpi-card">期末資產<div class="kpi-val">{fmt_money(sl[0]*capital)}</div></div>', unsafe_allow_html=True)
        kc[1].markdown(f'<div class="kpi-card">CAGR<div class="kpi-val">{sl[2]:.2%}</div></div>', unsafe_allow_html=True)
        kc[2].markdown(f'<div class="kpi-card">最大回撤<div class="kpi-val">{sl[3]:.2%}</div></div>', unsafe_allow_html=True)
        kc[3].markdown(f'<div class="kpi-card">Calmar<div class="kpi-val">{sl[7]:.2f}</div></div>', unsafe_allow_html=True)

        st.markdown("#### 📈 資金曲線比較")
        fig_fe = go.Figure()
        fig_fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿持有", line=dict(color="#FF4B4B")))
        fig_fe.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="本策略", line=dict(color="#00D494", width=3)))
        st.plotly_chart(fig_fe, use_container_width=True)

###############################################################
# Tab 2: 全參數最佳化 (修正 KeyError 位置)
###############################################################
with tab_opt:
    st.write("### 🧪 全參數網格搜尋")
    with st.expander("🛠️ 定義搜尋空間 (組合數越大計算越久)", expanded=True):
        o_c1, o_c2 = st.columns(2)
        with o_c1:
            opt_d_bias = st.multiselect("加碼門檻 (%)", [-10, -15, -20, -25], default=[-15])
            opt_d_pcts = st.multiselect("加碼比例 (%)", [10, 20, 33, 50], default=[20, 33])
            opt_d_cds = st.multiselect("加碼 CD (天)", [5, 10, 20], default=[10])
        with o_c2:
            opt_a_bias = st.multiselect("套利門檻 (%)", [25, 35, 45, 55], default=[35])
            opt_a_pcts = st.multiselect("套利比例 (%)", [50, 100], default=[100])
            opt_a_cds = st.multiselect("套利 CD (天)", [5, 10, 20], default=[10])

    if st.button("執行全參數跑分 🧬"):
        # 1. 準備資料 (修正點：確保欄位名稱正確)
        start_buf = start - dt.timedelta(days=int(sma_window * 2))
        df_opt = pd.DataFrame(index=df_base_raw.index)
        df_opt["Price_base"] = df_base_raw["Price"] # 重要：這裡命名為 Price_base
        df_opt = df_opt.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
        df_opt["MA"] = df_opt["Price_base"].rolling(sma_window).mean()
        df_opt["Bias"] = (df_opt["Price_base"] - df_opt["MA"]) / df_opt["MA"]
        df_opt = df_opt.dropna(subset=["MA"]).loc[start:end]
        
        # 2. 建立組合
        combs = list(product(opt_d_bias, opt_d_pcts, opt_d_cds, opt_a_bias, opt_a_pcts, opt_a_cds))
        total = len(combs)
        results = []
        progress = st.progress(0)
        status = st.empty()
        
        # 3. 執行
        for idx, (db, dp, dc, ab, ap, ac) in enumerate(combs):
            status.text(f"計算中: {idx+1}/{total}...")
            c, m, clm = run_fast_backtest(df_opt, db, dp, dc, ab, ap, ac)
            results.append({"加碼門檻%": db, "加碼%": dp, "加碼CD": dc, "套利門檻%": ab, "套利%": ap, "套利CD": ac, "CAGR": c, "MDD": m, "Calmar": clm})
            progress.progress((idx + 1) / total)
            
        status.success(f"✅ 完成 {total} 組模擬！")
        res_df = pd.DataFrame(results).sort_values(by="Calmar", ascending=False)
        st.write("#### 🏆 最佳性價比 (Calmar) 排行榜")
        st.dataframe(res_df.head(10).style.format({"CAGR": "{:.2%}", "MDD": "{:.2%}", "Calmar": "{:.3f}"}), use_container_width=True)
        
        # 散佈圖
        fig_scat = px.scatter(res_df, x="MDD", y="CAGR", size="Calmar", color="加碼門檻%", 
                              hover_data=["加碼%", "套利門檻%"], title="全組合風險報酬分析")
        st.plotly_chart(fig_scat, use_container_width=True)

# Footer
st.markdown("<br><hr><div style='text-align:center; color:gray; font-size:0.8rem;'>Copyright © 2025 hamr-lab.com. All rights reserved.</div>", unsafe_allow_html=True)
