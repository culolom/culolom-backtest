###############################################################
# app.py — 0050LRS + 雙向乖離 (精確對齊修正版)
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
# 1. 核心工具函數 (放在最上方，防止 NameError)
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
    f_eq, f_ret = eq.iloc[-1], eq.iloc[-1] - 1
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
# 2. 字型與驗證設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="0050LRS 戰情室", page_icon="📈", layout="wide")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass 

###############################################################
# 3. UI 設定
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
    df = df.sort_index(); df["Price"] = df["Close"]
    return df[["Price"]]

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿 (精確對齊版)</h1>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
base_label = col1.selectbox("原型 ETF (訊號源)", list(BASE_ETFS.keys()))
lev_label = col2.selectbox("槓桿 ETF (實際交易)", list(LEV_ETFS.keys()))

# 獲取時間範圍
df1_tmp, df2_tmp = load_csv(BASE_ETFS[base_label]), load_csv(LEV_ETFS[lev_label])
s_min = max(df1_tmp.index.min().date(), df2_tmp.index.min().date())
s_max = min(df1_tmp.index.max().date(), df2_tmp.index.max().date())

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 5000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
position_mode = st.radio("策略初始狀態", ["一開局就全倉槓桿 ETF", "空手起跑 (等待金叉)"], index=0)

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 均線下：負乖離 DCA 加碼", expanded=True):
        enable_dca = st.toggle("啟用 DCA", value=True)
        dca_bias_trigger = st.number_input("加碼門檻 (%)", max_value=0.0, value=-15.0)
        dca_pct = st.number_input("每次買進比例 (%)", 1, 100, 20)
        dca_cooldown = st.slider("加碼冷卻天數", 1, 60, 10)
with col_set2:
    with st.expander("🚀 均線上：高位乖離套利減碼", expanded=True):
        enable_arb = st.toggle("啟用套利", value=False)
        arb_bias_trigger = st.number_input("套利門檻 (%)", min_value=0.0, value=20.0)
        arb_reduce_pct = st.number_input("每次減碼比例 (%)", 1, 100, 20)
        arb_cooldown = st.slider("套利冷卻天數", 1, 60, 10)

###############################################################
# 4. 回測執行
###############################################################

if st.button("開始回測 🚀"):
    # 讀取資料
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df_base = load_csv(BASE_ETFS[base_label]).loc[start_buf:end]
    df_lev = load_csv(LEV_ETFS[lev_label]).loc[start_buf:end]
    
    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_lev["Price"].rename("Price_lev"), how="inner").sort_index()
    df["MA"] = df["Price_base"].rolling(sma_window).mean()
    df["Bias"] = (df["Price_base"] - df["MA"]) / df["MA"]
    df = df.dropna(subset=["MA"]).loc[start:end]
    
    # ------------------------------------------------------
    # 核心策略邏輯 (修正第一天對齊問題)
    # ------------------------------------------------------
    sigs, pos = [0] * len(df), [0.0] * len(df)
    
    # 初始狀態設定
    if "一開局" in position_mode:
        curr_pos, can_buy = 1.0, True
    else:
        curr_pos, can_buy = 0.0, False
    
    # 第一天的持倉位置
    pos[0] = curr_pos
    dca_cd, arb_cd = 0, 0

    for i in range(1, len(df)):
        p, m, bias = df["Price_base"].iloc[i], df["MA"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price_base"].iloc[i-1], df["MA"].iloc[i-1]
        
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        sig = 0

        if p > m:
            # === 均線上：應持有部位 ===
            if can_buy:
                # 關鍵修正：進入均線上的預設狀態應為全倉，除非觸發減碼
                target_pos = 1.0 
                if enable_arb and bias >= arb_bias_trigger and arb_cd == 0:
                    target_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
                    sig, arb_cd = 3, arb_cooldown
                
                # 如果是剛從均線下站上來（或第一天站上），標記買進訊號
                if p0 <= m0: sig = 1
                curr_pos = target_pos
            else:
                curr_pos = 0.0
            dca_cd = 0
        else:
            # === 均線下：應清倉或 DCA ===
            can_buy = True # 跌破後自動解鎖下次站上的買入權
            if p0 > m0: # 死亡交叉
                curr_pos, sig, arb_cd = 0.0, -1, 0
            elif enable_dca and curr_pos < 1.0:
                if bias <= dca_bias_trigger and dca_cd == 0:
                    curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
                    sig, dca_cd = 2, dca_cooldown
        
        pos[i] = round(curr_pos, 4)
        sigs[i] = sig

    df["Signal"], df["Position"] = sigs, pos

    # 計算資產淨值 (Equity)
    equity = [1.0]
    for i in range(1, len(df)):
        # 使用 Position[i-1] (昨天的持倉) 來參與今天 (i) 的漲跌
        ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity
    df["Equity_BH_Base"] = (df["Price_base"] / df["Price_base"].iloc[0])
    df["Equity_BH_Lev"] = (df["Price_lev"] / df["Price_lev"].iloc[0])
    
    # ------------------------------------------------------
    # 5. 視覺化組件 (KPI, 圖表, 表格)
    # ------------------------------------------------------
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl, sv, sb = get_stats(df["Equity_LRS"], df["Equity_LRS"].pct_change(), y_len), \
                 get_stats(df["Equity_BH_Lev"], df["Equity_BH_Lev"].pct_change(), y_len), \
                 get_stats(df["Equity_BH_Base"], df["Equity_BH_Base"].pct_change(), y_len)

    # KPI 卡片
    st.markdown("""<style>.kpi-card {background: var(--secondary-background-color); border-radius: 16px; padding: 24px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-val {font-size:2.2rem; font-weight:900; margin:10px 0;} .delta {color:#21c354; background:#21c3541a; padding:4px 12px; border-radius:12px; font-weight:700;}</style>""", unsafe_allow_html=True)
    kc = st.columns(4)
    kc[0].markdown(f'<div class="kpi-card">期末資產<div class="kpi-val">{fmt_money(sl[0]*capital)}</div><span class="delta">+{ (sl[0]/sv[0]-1):.2%} (vs 槓桿)</span></div>', unsafe_allow_html=True)
    kc[1].markdown(f'<div class="kpi-card">CAGR<div class="kpi-val">{sl[2]:.2%}</div><span class="delta">+{ (sl[2]-sv[2]):.2%}</span></div>', unsafe_allow_html=True)
    kc[2].markdown(f'<div class="kpi-card">年化波動<div class="kpi-val">{sl[4]:.2%}</div></div>', unsafe_allow_html=True)
    kc[3].markdown(f'<div class="kpi-card">最大回撤<div class="kpi-val">{sl[3]:.2%}</div></div>', unsafe_allow_html=True)

    # 雙軸信號圖
    st.markdown("### 📌 策略訊號對照圖")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="原型(左)", line=dict(color="#636EFA")))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA"], name="SMA", line=dict(color="#FFA15A")))
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name="槓桿(右)", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.3))
    
    colors = {1: ("買進", "#00C853", "triangle-up"), -1: ("清倉", "#D50000", "triangle-down"), 
              2: ("DCA", "#2E7D32", "circle"), 3: ("套利", "#FF9800", "diamond")}
    for v, (l, c, s) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty: fig.add_trace(go.Scatter(x=pts.index, y=pts["Price_base"], mode="markers", name=l, marker=dict(color=c, size=10, symbol=s)))
    fig.update_layout(template="plotly_white", height=500, yaxis2=dict(overlaying="y", side="right"), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 資金曲線分析
    st.markdown("### 📊 資金曲線比較")
    fe = go.Figure()
    fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型BH"))
    fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿BH"))
    fe.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="LRS+DCA (修正版)", line=dict(width=3, color="#00D494")))
    fe.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=450)
    st.plotly_chart(fe, use_container_width=True)

    # 冠軍表格
    st.markdown("### 🏆 策略詳細數據")
    metrics_list = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    dt_table = {
        "LRS+DCA": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()],
        "槓桿 BH": [sv[0]*capital, sv[1], sv[2], sv[7], sv[3], sv[4], sv[5], 0],
        "原型 BH": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0]
    }
    st.table(pd.DataFrame(dt_table, index=metrics_list))
