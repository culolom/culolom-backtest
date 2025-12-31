###############################################################
# app.py — 0050 雙向乖離動態槓桿 (單一標的判定版)
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
# 1. 環境設定與字型
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="單一標的：雙向乖離動態槓桿", page_icon="📈", layout="wide")

# 🔒 驗證守門員 (若無 auth.py 則跳過)
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import auth 
    if not auth.check_password(): st.stop()
except: pass 

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
# 3. 自動讀取 Data 資料夾 CSV 檔案
###############################################################

DATA_DIR = Path("data")

def get_csv_list():
    if not DATA_DIR.exists():
        return []
    # 取得所有 .csv 檔案並移除副檔名作為選單顯示
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    if "Close" in df.columns:
        df["Price"] = df["Close"]
    return df[["Price"]]

available_etfs = get_csv_list()

###############################################################
# 4. UI 與 Sidebar
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### ⚙️ 系統設定")
    if not available_etfs:
        st.error("❌ data 資料夾內找不到任何 CSV 檔案")
        st.stop()
    
    target_label = st.selectbox("選擇交易標的 (同步作為訊號源)", available_etfs, index=available_etfs.index("00631L.TW") if "00631L.TW" in available_etfs else 0)
    
    st.divider()
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown(f"<h1 style='margin-bottom:0.5em;'>📊 {target_label} 單一標的動態槓桿系統</h1>", unsafe_allow_html=True)

# 載入預覽數據以取得日期範圍
df_preview = load_csv(target_label)
s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 10000000, 100000, step=10000)
sma_window = col_p4.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
position_mode = st.radio("初始狀態選擇", ["一開局就全倉", "空手起跑 (等待下次金叉)"], index=0, horizontal=True)

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 均線下：負乖離 DCA 加碼設定", expanded=True):
        enable_dca = st.toggle("啟用 DCA 加碼", value=True)
        dca_bias_trigger = st.number_input("加碼觸發乖離率 (%)", max_value=0.0, value=-15.0)
        dca_pct = st.number_input("每次加碼資金比例 (%)", 1, 100, 20)
        dca_cooldown = st.slider("加碼冷卻天數 (CD)", 1, 60, 10)
with col_set2:
    with st.expander("🚀 均線上：高位乖離套利減碼設定", expanded=True):
        enable_arb = st.toggle("啟用套利減碼", value=False)
        arb_bias_trigger = st.number_input("減碼觸發乖離率 (%)", min_value=0.0, value=35.0)
        arb_reduce_pct = st.number_input("每次減碼資金比例 (%)", 1, 100, 100)
        arb_cooldown = st.slider("套利冷卻天數 (CD)", 1, 60, 10)

###############################################################
# 5. 回測執行 (單一標的邏輯)
###############################################################

if st.button("啟動回測引擎 🚀"):
    # 緩衝期讀取數據
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df = load_csv(target_label).loc[start_buf:end]
    
    if df.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    df["MA"] = df["Price"].rolling(sma_window).mean()
    df["Bias"] = (df["Price"] - df["MA"]) / df["MA"]
    df = df.dropna(subset=["MA"]).loc[start:end]
    
    # 策略核心循環
    sigs, pos = [0] * len(df), [0.0] * len(df)
    curr_pos, can_buy = (1.0, True) if "一開局" in position_mode else (0.0, False)
    pos[0], dca_cd, arb_cd = curr_pos, 0, 0

    for i in range(1, len(df)):
        p, m, bias_pct = df["Price"].iloc[i], df["MA"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price"].iloc[i-1], df["MA"].iloc[i-1]
        
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        sig = 0

        if p > m:
            if can_buy:
                if p0 <= m0: # 金叉
                    curr_pos = 1.0 
                    sig = 1
                # 套利邏輯
                if enable_arb and bias_pct >= arb_bias_trigger and arb_cd == 0 and curr_pos > 0:
                    curr_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
                    sig, arb_cd = 3, arb_cooldown
            else: curr_pos = 0.0
            dca_cd = 0
        else: # 均線下
            can_buy = True 
            if p0 > m0: # 死叉
                curr_pos, sig, arb_cd = 0.0, -1, 0
            elif enable_dca and curr_pos < 1.0: # DCA
                if bias_pct <= dca_bias_trigger and dca_cd == 0:
                    curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
                    sig, dca_cd = 2, dca_cooldown
        
        pos[i], sigs[i] = round(curr_pos, 4), sig

    df["Signal"], df["Position"] = sigs, pos

    # 計算資金曲線
    equity_strategy = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) - 1
        equity_strategy.append(equity_strategy[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_Strategy"] = equity_strategy
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Equity_BH"] = (df["Price"] / df["Price"].iloc[0])
    df["Return_BH"] = df["Price"].pct_change().fillna(0)
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity_Strategy"], df["Return_Strategy"], y_len)
    sb = get_stats(df["Equity_BH"], df["Return_BH"], y_len)

    # ------------------------------------------------------
    # 6. 視覺化 KPI 與 圖表
    # ------------------------------------------------------
    st.markdown("""<style>.kpi-card {background: rgba(128,128,128,0.05); border-radius: 16px; padding: 20px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-val {font-size:2rem; font-weight:900; margin:5px 0;} .delta {font-size:0.9rem; font-weight:700; color:#21c354;}</style>""", unsafe_allow_html=True)
    
    kc = st.columns(4)
    kc[0].markdown(f'<div class="kpi-card">期末資產<div class="kpi-val">{fmt_money(sl[0]*capital)}</div><span class="delta">vs B&H: { (sl[0]/sb[0]-1):+.2%}</span></div>', unsafe_allow_html=True)
    kc[1].markdown(f'<div class="kpi-card">CAGR<div class="kpi-val">{sl[2]:.2%}</div><span class="delta">超額: { (sl[2]-sb[2]):+.2%}</span></div>', unsafe_allow_html=True)
    kc[2].markdown(f'<div class="kpi-card">最大回撤<div class="kpi-val">{sl[3]:.2%}</div><span class="delta">B&H: {sb[3]:.2%}</span></div>', unsafe_allow_html=True)
    kc[3].markdown(f'<div class="kpi-card">Sharpe<div class="kpi-val">{sl[5]:.2f}</div><span class="delta">B&H: {sb[5]:.2f}</span></div>', unsafe_allow_html=True)

    st.markdown("### 📌 訊號對照圖")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price"], name=f"{target_label} 股價", line=dict(color="#636EFA")))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A")))
    
    colors = {1: ("買進", "#00C853", "triangle-up", 12), -1: ("賣出", "#D50000", "triangle-down", 12), 
              2: ("DCA 加碼", "#2E7D32", "circle", 8), 3: ("套利減碼", "#FF9800", "diamond", 10)}
    for v, (l, c, s, sz) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty: fig.add_trace(go.Scatter(x=pts.index, y=pts["Price"], mode="markers", name=l, marker=dict(color=c, size=sz, symbol=s)))
    fig.update_layout(template="plotly_white", height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 分頁解析
    tab1, tab2, tab3 = st.tabs(["資金曲線", "回撤與乖離", "績效總表"])
    
    with tab1:
        fe = go.Figure()
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="本策略", line=dict(width=3, color="#00D494")))
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name="標的 Buy & Hold", line=dict(color="gray", dash='dash')))
        fe.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=450, title="累積報酬率比較")
        st.plotly_chart(fe, use_container_width=True)
    
    with tab2:
        col_sub1, col_sub2 = st.columns(2)
        with col_sub1:
            fd = go.Figure()
            fd.add_trace(go.Scatter(x=df.index, y=(df["Equity_Strategy"]/df["Equity_Strategy"].cummax()-1)*100, name="本策略", fill='tozeroy', line=dict(color='red')))
            fd.update_layout(template="plotly_white", height=400, title="策略回撤 (%)")
            st.plotly_chart(fd, use_container_width=True)
        with col_sub2:
            fb = go.Figure()
            fb.add_trace(go.Scatter(x=df.index, y=df["Bias"]*100, name="乖離率", line=dict(color="#AB63FA"), fill='tozeroy'))
            fb.add_hline(y=0, line_color="black")
            fb.update_layout(template="plotly_white", height=400, title="乖離率走勢 (%)")
            st.plotly_chart(fb, use_container_width=True)

    with tab3:
        metrics_list = ["期末資產", "總報酬率", "CAGR", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Calmar Ratio", "交易次數"]
        table_data = {
            "本策略": [sl[0]*capital, sl[1], sl[2], sl[3], sl[4], sl[5], sl[7], (df["Signal"]!=0).sum()],
            f"{target_label} B&H": [sb[0]*capital, sb[1], sb[2], sb[3], sb[4], sb[5], sb[7], 0]
        }
        res_df = pd.DataFrame(table_data, index=metrics_list)
        st.table(res_df.style.format(precision=2))

    # 免責聲明
    st.markdown("<br><hr><div style='text-align:center; color:gray; font-size:0.8rem;'>本研究僅供參考，投資有風險，過去績效不代表未來。</div>", unsafe_allow_html=True)
