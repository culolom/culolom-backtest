###############################################################
# app.py — 0050LRS + 雙向乖離 (負加碼 DCA + 高位套利) 旗艦版
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
# 1. 環境與字型設定
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

# --- Sidebar ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿 (雙向乖離版)</h1>", unsafe_allow_html=True)

###############################################################
# 2. 資料讀取工具
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

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std, downside = daily.mean(), daily.std(), daily[daily < 0].std()
    return std * np.sqrt(252), (avg / std) * np.sqrt(252) if std > 0 else np.nan, (avg / downside) * np.sqrt(252) if downside > 0 else np.nan

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"
def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))

###############################################################
# 3. UI 參數設定
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1: start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col_p2: end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col_p3: capital = st.number_input("投入本金（元）", 1000, 5000000, 100000, step=10000)
with col_p4: sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
st.write("### ⚙️ 倉位管理設定")
position_mode = st.radio("策略初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑"], index=0)

col_set1, col_set2 = st.columns(2)
with col_set1:
    with st.expander("📉 均線下：負乖離 DCA 加碼", expanded=True):
        enable_dca = st.toggle("啟用 DCA 加碼", value=True)
        dca_bias_trigger = st.number_input("觸發加碼乖離率 (%)", max_value=0.0, min_value=-50.0, value=-15.0, step=0.5)
        dca_pct = st.number_input("每次加碼比例 (%)", 1, 100, 20, step=5)
        dca_cooldown = st.slider("加碼冷卻天數", 1, 60, 10)

with col_set2:
    with st.expander("🚀 均線上：高位乖離套利減碼", expanded=True):
        enable_arb = st.toggle("啟用套利減碼", value=False)
        arb_bias_trigger = st.number_input("觸發減碼乖離率 (%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5)
        arb_reduce_pct = st.number_input("每次減碼比例 (%)", 1, 100, 20, step=5)
        arb_cooldown = st.slider("減碼冷卻天數", 1, 60, 10)

###############################################################
# 4. 核心回測運算
###############################################################

if st.button("開始回測 🚀"):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    df_base_raw = load_csv(base_symbol).loc[start_early:end]
    df_lev_raw = load_csv(lev_symbol).loc[start_early:end]

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗"); st.stop()

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()

    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df["Bias"] = (df["Price_base"] - df["MA_Signal"]) / df["MA_Signal"]
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]
    
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # 策略迴圈
    executed_signals, positions = [0] * len(df), [0.0] * len(df)
    current_pos, can_buy_perm = (1.0, True) if "全倉" in position_mode else (0.0, False)
    dca_cd, arb_cd = 0, 0

    for i in range(1, len(df)):
        p, m, bias = df["Price_base"].iloc[i], df["MA_Signal"].iloc[i], df["Bias"].iloc[i] * 100
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_Signal"].iloc[i-1]
        
        if dca_cd > 0: dca_cd -= 1
        if arb_cd > 0: arb_cd -= 1
        sig = 0

        if p > m:
            if p0 <= m0: # 黃金交叉
                current_pos = 1.0 if can_buy_perm else 0.0
                if can_buy_perm: sig = 1
            else: # 均線上判斷套利
                if enable_arb and current_pos > 0:
                    if bias >= arb_bias_trigger and arb_cd == 0:
                        current_pos = max(0.0, current_pos - (arb_reduce_pct / 100.0))
                        sig, arb_cd = 3, arb_cooldown
            dca_cd = 0
        else: # 均線下
            can_buy_perm = True 
            if p0 > m0: # 死亡交叉
                current_pos, sig, arb_cd = 0.0, -1, 0
            else: # 均線下判斷 DCA
                if enable_dca and current_pos < 1.0:
                    if bias <= dca_bias_trigger and dca_cd == 0:
                        current_pos = min(1.0, current_pos + (dca_pct / 100.0))
                        sig, dca_cd = 2, dca_cooldown
        
        positions[i], executed_signals[i] = round(current_pos, 4), sig

    df["Signal"], df["Position"] = executed_signals, positions

    # 績效計算
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity_lrs.append(equity_lrs[-1] * (1 + (lev_ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()
    
    # ------------------------------------------------------
    # 5. 視覺化：雙軸圖與 Tabs
    # ------------------------------------------------------
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label}(左)", line=dict(color="#636EFA", width=2)))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label}(右)", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.3))
    
    # 標記訊號
    s_map = {1: ("全倉買進", "#00C853", "triangle-up", 12), -1: ("清倉賣出", "#D50000", "triangle-down", 12), 
             2: ("DCA加碼", "#2E7D32", "circle", 8), 3: ("套利減碼", "#FF9800", "diamond", 10)}
    for s_val, (name, color, symbol, size) in s_map.items():
        pts = df[df["Signal"] == s_val]
        if not pts.empty:
            fig_p.add_trace(go.Scatter(x=pts.index, y=pts["Price_base"], mode="markers", name=name, 
                                       marker=dict(color=color, size=size, symbol=symbol),
                                       hovertext=[f"乖離率: {b:.2%}<br>持倉: {p:.0%}" for b, p in zip(pts["Bias"], pts["Position"])]))

    fig_p.update_layout(template="plotly_white", height=500, yaxis2=dict(overlaying="y", side="right"), hovermode="x unified")
    st.plotly_chart(fig_p, use_container_width=True)

    # 四大分析頁面
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])
    with tab1:
        fe = go.Figure()
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型BH"))
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿BH"))
        fe.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="動態 LRS", line=dict(width=3, color="#00D494")))
        fe.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=450)
        st.plotly_chart(fe, use_container_width=True)
    with tab2:
        fd = go.Figure()
        fd.add_trace(go.Scatter(x=df.index, y=(df["Equity_LRS"]/df["Equity_LRS"].cummax()-1)*100, name="LRS", fill='tozeroy', line=dict(color='red')))
        fd.update_layout(template="plotly_white", height=450)
        st.plotly_chart(fd, use_container_width=True)
    with tab4:
        fh = go.Figure()
        fh.add_trace(go.Histogram(x=df["Return_LRS"]*100, name="LRS", opacity=0.75, marker_color="#00D494"))
        fh.add_trace(go.Histogram(x=df["Return_lev"]*100, name="槓桿BH", opacity=0.4))
        fh.update_layout(barmode="overlay", template="plotly_white", title="日報酬分佈 (%)", height=450)
        st.plotly_chart(fh, use_container_width=True)

    # ------------------------------------------------------
    # 6. KPI 卡片與高級 HTML 表格
    # ------------------------------------------------------
    years_len = (df.index[-1] - df.index[0]).days / 365
    stats_lrs = get_stats(df["Equity_LRS"], df["Return_LRS"], years_len)
    stats_lev = get_stats(df["Equity_BH_Lev"], df["Return_lev"], years_len)
    stats_base = get_stats(df["Equity_BH_Base"], df["Return_base"], years_len)

    st.markdown("""<style>.kpi-card {background: var(--secondary-background-color); border-radius: 16px; padding: 24px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-val {font-size:2.2rem; font-weight:900; margin:10px 0;} .delta-p {color:#21c354; background:#21c3541a; padding:4px 12px; border-radius:12px; font-weight:700;}</style>""", unsafe_allow_html=True)
    kc = st.columns(4)
    with kc[0]: st.markdown(f'<div class="kpi-card">期末資產<div class="kpi-val">{fmt_money(stats_lrs[0]*capital)}</div><span class="delta-p">+{ (stats_lrs[0]/stats_lev[0]-1):.2%} (vs 槓桿)</span></div>', unsafe_allow_html=True)
    with kc[1]: st.markdown(f'<div class="kpi-card">CAGR<div class="kpi-val">{stats_lrs[2]:.2%}</div><span class="delta-p">+{ (stats_lrs[2]-stats_lev[2]):.2%}</span></div>', unsafe_allow_html=True)
    with kc[2]: st.markdown(f'<div class="kpi-card">年化波動<div class="kpi-val">{stats_lrs[4]:.2%}</div></div>', unsafe_allow_html=True)
    with kc[3]: st.markdown(f'<div class="kpi-card">最大回撤<div class="kpi-val">{stats_lrs[3]:.2%}</div></div>', unsafe_allow_html=True)

    # 冠軍獎盃表格
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    dt_table = {
        f"{lev_label}<br>LRS+DCA": [stats_lrs[0]*capital, stats_lrs[1], stats_lrs[2], stats_lrs[7], stats_lrs[3], stats_lrs[4], stats_lrs[5], (df["Signal"]!=0).sum()],
        f"{lev_label}<br>Buy & Hold": [stats_lev[0]*capital, stats_lev[1], stats_lev[2], stats_lev[7], stats_lev[3], stats_lev[4], stats_lev[5], 0],
        f"{base_label}<br>Buy & Hold": [stats_base[0]*capital, stats_base[1], stats_base[2], stats_base[7], stats_base[3], stats_base[4], stats_base[5], 0]
    }
    df_v = pd.DataFrame(dt_table, index=metrics)
    
    html = '<style>.ctable {width:100%; border-collapse:separate; border-spacing:0; border-radius:12px; border:1px solid rgba(128,128,128,0.1); overflow:hidden;} .ctable th {background:#80808010; padding:15px; text-align:center;} .ctable td {padding:12px; text-align:center; border-bottom:1px solid rgba(128,128,128,0.05);} .mname {text-align:left !important; background:#80808005; font-weight:500;}</style>'
    html += '<table class="ctable"><thead><tr><th style="text-align:left">指標</th>'
    for col in df_v.columns: html += f'<th>{col}</th>'
    html += '</tr></thead><tbody>'

    for m in metrics:
        html += f'<tr><td class="mname">{m}</td>'
        rv = df_v.loc[m].values
        is_inv = m in ["最大回撤 (MDD)", "年化波動", "交易次數"]
        best = min(rv) if is_inv else max(rv)
        for v in rv:
            is_win = (v == best and m != "交易次數")
            if "資產" in m: txt = fmt_money(v)
            elif any(x in m for x in ["率", "報酬", "波動", "MDD"]): txt = fmt_pct(v)
            elif "次數" in m: txt = fmt_int(v)
            else: txt = fmt_num(v)
            html += f'<td {"style=\'font-weight:bold;\'" if is_win else ""}>{txt} {"🏆" if is_win else ""}</td>'
        html += '</tr>'
    st.write(html + '</tbody></table>', unsafe_allow_html=True)

def get_stats(eq, rets, y):
    f_eq, f_ret = eq.iloc[-1], eq.iloc[-1] - 1
    cagr = (1 + f_ret)**(1/y) - 1 if y > 0 else 0
    mdd = 1 - (eq / eq.cummax()).min()
    v, sh, so = calc_metrics(rets)
    return f_eq, f_ret, cagr, mdd, v, sh, so, cagr/mdd if mdd > 0 else 0
