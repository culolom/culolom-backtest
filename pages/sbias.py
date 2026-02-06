###############################################################
# app.py — 單一標的雙向乖離動態策略 (含 SMA 過濾開關)
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
# 1. 字型與驗證設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="雙向乖離動態策略", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (若無 auth 模組則跳過)
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

###############################################################
# 3. Sidebar 與 UI 配置
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 單一標的雙向乖離動態策略 </h1>", unsafe_allow_html=True)

# 整合所有標的清單
ETF_OPTIONS = {
    "0050 元大台灣50": "0050.TW",
    "2330 台積電": "2330.TW",
    "00878 國泰永續高股息": "00878.TW",
    "00662 富邦 NASDAQ": "00662.TW",
    "00646 元大 S&P 500": "00646.TW",
    "00670L 富邦 NASDAQ 正2": "00670L.TW",
    "00647L 元大 S&P 500 正2": "00647L.TW",
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
    "00708L 元大 S&P 原油正2": "00708L.TW",
    "00635U 元大 S&P 黃金": "00635U.TW",
    "QQQ (Nasdaq 100)": "QQQ",
    "QLD (Nasdaq 100 2x)": "QLD",
    "TQQQ (Nasdaq 100 3x)": "TQQQ",
    "SPY (S&P 500)": "SPY",
    "BTC-USD (Bitcoin)": "BTC-USD",
}

def load_csv(symbol: str) -> pd.DataFrame:
    path = Path("data") / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

# 單一標的選擇
etf_label = st.selectbox("選擇交易標的", list(ETF_OPTIONS.keys()))
df_tmp = load_csv(ETF_OPTIONS[etf_label])

if df_tmp.empty:
    st.error(f"找不到標的 {etf_label} 的資料檔案，請確認 data 資料夾內有 {ETF_OPTIONS[etf_label]}.csv")
    st.stop()

s_min, s_max = df_tmp.index.min().date(), df_tmp.index.max().date()

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 10000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
col_cfg1, col_cfg2 = st.columns(2)
with col_cfg1:
    position_mode = st.radio("策略初始狀態", ["一開局就全倉標的 ETF", "空手起跑"], index=0)
with col_cfg2:
    # 🌟 新增開關：是否利用 SMA 做趨勢過濾
    use_sma_filter = st.toggle("啟用 SMA 趨勢過濾", value=True, help="開啟：跌破均線強制清倉避險。關閉：僅參考乖離率加減碼，無視均線多空。")

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 負乖離 DCA 加碼設定", expanded=True):
        enable_dca = st.toggle("啟用 DCA", value=True)
        dca_bias_trigger = st.number_input("加碼門檻乖離率 (%)", max_value=0.0, value=-15.0)
        dca_pct = st.number_input("每次加碼比例 (%)", 1, 100, 20)
        dca_cooldown = st.slider("加碼冷卻天數", 1, 60, 10)
with col_set2:
    with st.expander("🚀 高位乖離套利減碼設定", expanded=True):
        enable_arb = st.toggle("啟用套利", value=True)
        arb_bias_trigger = st.number_input("套利門檻乖離率 (%)", min_value=0.0, value=35.0)
        arb_reduce_pct = st.number_input("每次減碼比例 (%)", 1, 100, 100)
        arb_cooldown = st.slider("套利冷卻天數", 1, 60, 10)

###############################################################
# 4. 回測核心執行
###############################################################

if st.button("開始回測 🚀"):
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df = load_csv(ETF_OPTIONS[etf_label]).loc[start_buf:end].copy()
    
    df["MA"] = df["Price"].rolling(sma_window).mean()
    df["Bias"] = (df["Price"] - df["MA"]) / df["MA"]
    df = df.dropna(subset=["MA"]).loc[start:end]
    
    # 策略運算核心
    sigs, pos = [0] * len(df), [0.0] * len(df)
    curr_pos = 1.0 if "一開局" in position_mode else 0.0
    # 若啟用 SMA 過濾且初始在均線下，需修正初始部位
    if use_sma_filter and df["Price"].iloc[0] < df["MA"].iloc[0]:
        curr_pos = 0.0
        
    pos[0], dca_cd, arb_cd = curr_pos, 0, 0

    for i in range(1, len(df)):
        p, m, bias = df["Price"].iloc[i], df["MA"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price"].iloc[i-1], df["MA"].iloc[i-1]
        
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        sig = 0

        # === 邏輯 A：SMA 趨勢判斷 (若開啟開關) ===
        if use_sma_filter:
            if p > m and p0 <= m0: # 黃金交叉 -> 買入/回補至全倉
                curr_pos = 1.0
                sig = 1
            elif p < m and p0 >= m0: # 死亡交叉 -> 清倉避險
                curr_pos = 0.0
                sig = -1
        
        # === 邏輯 B：乖離率動態調整 ===
        # 1. 高位套利 (不論均線多空皆可觸發，除非已被 SMA 清倉)
        if enable_arb and bias >= arb_bias_trigger and arb_cd == 0 and curr_pos > 0:
            curr_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
            sig, arb_cd = 3, arb_cooldown
        
        # 2. 低位 DCA (當價格相對於均線過低時加碼)
        if enable_dca and bias <= dca_bias_trigger and dca_cd == 0 and curr_pos < 1.0:
            curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
            sig, dca_cd = 2, dca_cooldown
        
        pos[i], sigs[i] = round(curr_pos, 4), sig

    df["Signal"], df["Position"] = sigs, pos

    # 計算策略淨值
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) - 1
        # 使用前一天的持倉比例計算今日報酬
        equity_lrs.append(equity_lrs[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_Strategy"] = equity_lrs
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Equity_BH"] = (df["Price"] / df["Price"].iloc[0])
    df["Return_BH"] = df["Price"].pct_change().fillna(0)
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity_Strategy"], df["Return_Strategy"], y_len)
    sb = get_stats(df["Equity_BH"], df["Return_BH"], y_len)

    # ------------------------------------------------------
    # 5. KPI 與 圖表
    # ------------------------------------------------------
    st.markdown("""<style>.kpi-card {background: var(--secondary-background-color); border-radius: 16px; padding: 24px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-val {font-size:2.2rem; font-weight:900; margin:10px 0;} .delta {color:#21c354; background:#21c3541a; padding:4px 12px; border-radius:12px; font-weight:700;}</style>""", unsafe_allow_html=True)
    kc = st.columns(4)
    kc[0].markdown(f'<div class="kpi-card">策略期末資產<div class="kpi-val">{fmt_money(sl[0]*capital)}</div><span class="delta">vs {fmt_money(sb[0]*capital)} (BH)</span></div>', unsafe_allow_html=True)
    kc[1].markdown(f'<div class="kpi-card">策略 CAGR<div class="kpi-val">{sl[2]:.2%}</div><span class="delta">BH: {sb[2]:.2%}</span></div>', unsafe_allow_html=True)
    kc[2].markdown(f'<div class="kpi-card">策略波動<div class="kpi-val">{sl[4]:.2%}</div></div>', unsafe_allow_html=True)
    kc[3].markdown(f'<div class="kpi-card">策略最大回撤<div class="kpi-val">{sl[3]:.2%}</div></div>', unsafe_allow_
