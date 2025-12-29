###############################################################
# app.py — 0050LRS + 雙向乖離 (負加碼 DCA + 高位套利) 修正版
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

st.set_page_config(page_title="0050LRS 戰情室", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

###############################################################
# 2. 核心計算函數 (Utility Functions) - 放在這裡避免 NameError
###############################################################

def calc_metrics(series: pd.Series):
    """計算年化波動率、夏普比率與索提諾比率"""
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std = daily.mean(), daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def get_stats(eq, rets, y):
    """統整策略績效指標"""
    f_eq = eq.iloc[-1]
    f_ret = f_eq - 1
    cagr = (1 + f_ret)**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq / eq.cummax()).min()
    v, sh, so = calc_metrics(rets)
    calmar = cagr / mdd if mdd > 0 else 0
    return f_eq, f_ret, cagr, mdd, v, sh, so, calmar

# 格式化工具
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"
def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))

###############################################################
# 3. 資料讀取工具
###############################################################

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW", "00685L 群益台灣加權正2": "00685L.TW",
}
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1, df2 = load_csv(base_symbol), load_csv(lev_symbol)
    if df1.empty or df2.empty: return dt.date(2012, 1, 1), dt.date.today()
    return max(df1.index.min().date(), df2.index.min().date()), min(df1.index.max().date(), df2.index.max().date())

###############################################################
# 4. UI 介面配置
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿 (雙向乖離旗艦版)</h1>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（實際交易）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1: start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)))
with col_p2: end = st.date_input("結束日期", value=s_max)
with col_p3: capital = st.number_input("本金（元）", 1000, 5000000, 100000, step=10000)
with col_p4: sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
st.write("### ⚙️ 策略參數")
position_mode = st.radio("初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑"], index=0)

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 均線下：負乖離 DCA 加碼", expanded=True):
        enable_dca = st.toggle("啟用 DCA", value=True)
        dca_bias_trigger = st.number_input("加碼門檻 (%)", max_value=0.0, min_value=-50.0, value=-15.0)
        dca_pct = st.number_input("每次買進比例 (%)", 1, 100, 20)
        dca_cooldown = st.slider("加碼冷卻天數", 1, 60, 10)

with col_set2:
    with st.expander("🚀 均線上：高位套利減碼", expanded=True):
        enable_arb = st.toggle("啟用減碼", value=False)
        arb_bias_trigger = st.number_input("減碼門檻 (%)", min_value=0.0, max_value=100.0, value=20.0)
        arb_reduce_pct = st.number_input("每次賣出比例 (%)", 1, 100, 20)
        arb_cooldown = st.slider("減碼冷卻天數", 1, 60, 10)

###############################################################
# 5. 回測核心執行
###############################################################

if st.button("開始回測 🚀"):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    df_base = load_csv(base_symbol).loc[start_early:end]
    df_lev = load_csv(lev_symbol).loc[start_early:end]

    if df_base.empty or df_lev.empty:
        st.error("資料不足"); st.stop()

    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_lev["Price"].rename("Price_lev"), how="inner").sort_index()

    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df["Bias"] = (df["Price_base"] - df["MA_Signal"]) / df["MA_Signal"]
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]
    
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # 模擬持倉
    sigs, pos = [0] * len(df), [0.0] * len(df)
    curr_pos, can_buy = (1.0, True) if "全倉" in position_mode else (0.0, False)
    dca_cd, arb_cd = 0, 0

    for i in range(1, len(df)):
        p, m, bias = df["Price_base"].iloc[i], df["MA_Signal"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_Signal"].iloc[i-1]
        
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        s = 0

        if p > m:
            if p0 <= m0: # 金叉
                curr_pos = 1.0 if can_buy else 0.0
                if can_buy: s = 1
            else: # 套利判斷
                if enable_arb and curr_pos > 0:
                    if bias >= arb_bias_trigger and arb_cd == 0:
                        curr_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
                        s, arb_cd = 3, arb_cooldown
            dca_cd = 0
        else:
            can_buy = True 
            if p0 > m0: # 死叉
                curr_pos, s, arb_cd = 0.0, -1, 0
            else: # DCA 判斷
                if enable_dca and curr_pos < 1.0:
                    if bias <= dca_bias_trigger and dca_cd == 0:
                        curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
                        s, dca_cd = 2, dca_cooldown
        
        pos[i], sigs[i] = round(curr_pos, 4), s

    df["Signal"], df["Position"] = sigs, pos

    # 計算資產
    equity = [1.0]
    for i in range(1, len(df)):
        r = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (r * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()
    
    # ------------------------------------------------------
    # 6. 視覺化
    # ------------------------------------------------------
    st.markdown("### 📌 策略訊號圖")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="原型(左)", line=dict(color="#636EFA")))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name="SMA", line=dict(color="#FFA15A")))
    
    # 標記訊號
    colors = {1: ("買進", "#00C853", "triangle-up"), -1: ("清倉", "#D50000", "triangle-down"), 
              2: ("DCA", "#2E7D32", "circle"), 3: ("套利", "#FF9800", "diamond")}
    for v, (label, color, sym) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty:
            fig.add_trace(go.Scatter(x=pts.index, y=pts["Price_base"], mode="markers", name=label, marker=dict(color=color, size=10, symbol=sym)))
    
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # KPI 區
    years = (df.index[-1] - df.index[0]).days / 365
    s_lrs = get_stats(df["Equity_LRS"], df["Return_LRS"], years)
    s_lev = get_stats(df["Equity_BH_Lev"], df["Return_lev"], years)
    s_base = get_stats(df["Equity_BH_Base"], df["Return_base"], years)

    st.markdown("### 📊 關鍵績效指標")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("期末資產", fmt_money(s_lrs[0]*capital), f"{(s_lrs[0]/s_lev[0]-1):.2%} vs 槓桿")
    c2.metric("CAGR", f"{s_lrs[2]:.2%}", f"{(s_lrs[2]-s_lev[2]):.2%}")
    c3.metric("最大回撤", f"{s_lrs[3]:.2%}")
    c4.metric("夏普比率", f"{s_lrs[5]:.2f}")

    # 表格
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    dt_table = {
        "LRS+雙向乖離": [s_lrs[0]*capital, s_lrs[1], s_lrs[2], s_lrs[7], s_lrs[3], s_lrs[4], s_lrs[5], (df["Signal"]!=0).sum()],
        "槓桿 BH": [s_lev[0]*capital, s_lev[1], s_lev[2], s_lev[7], s_lev[3], s_lev[4], s_lev[5], 0],
        "原型 BH": [s_base[0]*capital, s_base[1], s_base[2], s_base[7], s_base[3], s_base[4], s_base[5], 0]
    }
    st.table(pd.DataFrame(dt_table, index=metrics))
