###############################################################
# app.py — 0050LRS + DCA (乖離率觸發 + 高級視覺化全功能版)
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

st.set_page_config(page_title="0050LRS 回測系統", page_icon="📈", layout="wide")

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

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿 (乖離率 DCA)</h1>", unsafe_allow_html=True)

###############################################################
# ETF 資料讀取與工具函式
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

# 格式化工具
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"
def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))

###############################################################
# UI 輸入
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

col3, col4, col5, col6 = st.columns(4)
with col3: start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4: end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5: capital = st.number_input("投入本金（元）", 1000, 5000000, 100000, step=10000)
with col6: sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)

st.write("---")
st.write("### ⚙️ 策略進階設定")
position_mode = st.radio("策略初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑"], index=0)

with st.expander("📉 跌破均線後的「負乖離加碼」設定", expanded=True):
    col_dca1, col_dca2, col_dca3 = st.columns([1, 2, 2])
    with col_dca1: enable_dca = st.toggle("啟用乖離率 DCA", value=True)
    with col_dca2: dca_bias_trigger = st.number_input("觸發加碼乖離率 (%)", max_value=0.0, min_value=-50.0, value=-5.0, step=0.5, disabled=not enable_dca)
    with col_dca3: dca_pct = st.number_input("每次加碼比例 (%)", 1, 100, 20, step=5, disabled=not enable_dca)
    dca_cooldown = st.slider("加碼冷卻天數", 1, 20, 5)

###############################################################
# 主程式
###############################################################

if st.button("開始回測 🚀"):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    df_base_raw = load_csv(base_symbol).loc[start_early:end]
    df_lev_raw = load_csv(lev_symbol).loc[start_early:end]

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料不足"); st.stop()

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()

    # 計算 SMA 與 乖離率
    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df["Bias"] = (df["Price_base"] - df["MA_Signal"]) / df["MA_Signal"]
    
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # ------------------------------------------------------
    # 核心策略邏輯
    # ------------------------------------------------------
    executed_signals, positions = [0] * len(df), [0.0] * len(df)
    current_pos, can_buy_permission = (1.0, True) if "全倉" in position_mode else (0.0, False)
    positions[0], cooldown_counter = current_pos, 0

    for i in range(1, len(df)):
        p, m, bias = df["Price_base"].iloc[i], df["MA_Signal"].iloc[i], df["Bias"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_Signal"].iloc[i-1]
        daily_signal = 0
        if cooldown_counter > 0: cooldown_counter -= 1

        if p > m:
            if can_buy_permission:
                current_pos = 1.0
                if p0 <= m0: daily_signal = 1
            else: current_pos = 0.0
            cooldown_counter = 0
        else:
            can_buy_permission = True 
            if p0 > m0: current_pos, daily_signal, cooldown_counter = 0.0, -1, 0
            elif enable_dca and current_pos < 1.0:
                if bias <= (dca_bias_trigger / 100.0) and cooldown_counter == 0:
                    current_pos = min(1.0, current_pos + (dca_pct / 100.0))
                    daily_signal, cooldown_counter = 2, dca_cooldown

        executed_signals[i], positions[i] = daily_signal, round(current_pos, 4)

    df["Signal"], df["Position"] = executed_signals, positions

    # ------------------------------------------------------
    # 績效運算
    # ------------------------------------------------------
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity_lrs.append(equity_lrs[-1] * (1 + (lev_ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()
    df["Pct_Base"], df["Pct_Lev"], df["Pct_LRS"] = df["Equity_BH_Base"]-1, df["Equity_BH_Lev"]-1, df["Equity_LRS"]-1

    # 數據統計
    years_len = (df.index[-1] - df.index[0]).days / 365
    def get_stats(eq, rets):
        final_eq, final_ret = eq.iloc[-1], eq.iloc[-1] - 1
        cagr = (1 + final_ret)**(1/years_len) - 1 if years_len > 0 else 0
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        return final_eq, final_ret, cagr, mdd, vol, sharpe, sortino, cagr/mdd if mdd > 0 else 0

    stats_lrs = get_stats(df["Equity_LRS"], df["Return_LRS"])
    stats_lev = get_stats(df["Equity_BH_Lev"], df["Return_lev"])
    stats_base = get_stats(df["Equity_BH_Base"], df["Return_base"])

    # ------------------------------------------------------
    # 視覺化輸出 1: 雙軸圖
    # ------------------------------------------------------
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label} (左)", line=dict(color="#636EFA", width=2)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label} (右)", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.4))
    
    buys, sells, dcas = df[df["Signal"]==1], df[df["Signal"]==-1], df[df["Signal"]==2]
    if not buys.empty: fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="全倉買進", marker=dict(color="#00C853", size=12, symbol="triangle-up")))
    if not sells.empty: fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="清倉賣出", marker=dict(color="#D50000", size=12, symbol="triangle-down")))
    if not dcas.empty: fig_price.add_trace(go.Scatter(x=dcas.index, y=dcas["Price_base"], mode="markers", name="DCA 加碼", marker=dict(color="#2E7D32", size=8), hovertext=[f"乖離率: {b:.2%}" for b in dcas["Bias"]]))

    fig_price.update_layout(template="plotly_white", height=450, yaxis2=dict(overlaying="y", side="right"), hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_price, use_container_width=True)

    # ------------------------------------------------------
    # 視覺化輸出 2: 四大 Tabs
    # ------------------------------------------------------
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])
    with t1:
        feq = go.Figure()
        feq.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], name="原型BH"))
        feq.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], name="槓桿BH"))
        feq.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], name="LRS+DCA", line=dict(width=3)))
        feq.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(feq, use_container_width=True)
    with t2:
        fdd = go.Figure()
        fdd.add_trace(go.Scatter(x=df.index, y=(df["Equity_LRS"]/df["Equity_LRS"].cummax()-1)*100, name="LRS+DCA", fill='tozeroy', line=dict(color='red')))
        fdd.update_layout(template="plotly_white", height=420, title="最大回撤 (%)")
        st.plotly_chart(fdd, use_container_width=True)
    with t3:
        radar_cat = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反)"]
        r_lrs = [nz(stats_lrs[2]), nz(stats_lrs[5]), nz(stats_lrs[6]), nz(-stats_lrs[3]), nz(-stats_lrs[4])]
        fr = go.Figure()
        fr.add_trace(go.Scatterpolar(r=r_lrs, theta=radar_cat, fill='toself', name='LRS+DCA'))
        fr.update_layout(polar=dict(radialaxis=dict(visible=True)), height=450)
        st.plotly_chart(fr, use_container_width=True)
    with t4:
        fh = go.Figure()
        fh.add_trace(go.Histogram(x=df["Return_LRS"]*100, name="LRS+DCA", opacity=0.7))
        fh.add_trace(go.Histogram(x=df["Return_lev"]*100, name="槓桿BH", opacity=0.5))
        fh.update_layout(barmode="overlay", template="plotly_white", height=450, title="日報酬分佈 (%)")
        st.plotly_chart(fh, use_container_width=True)

    # ------------------------------------------------------
    # 視覺化輸出 3: KPI 卡片
    # ------------------------------------------------------
    gap_a = (stats_lrs[0]/stats_lev[0]-1)*100
    gap_c = (stats_lrs[2]-stats_lev[2])*100
    st.markdown("""<style>.kpi-card {background-color: var(--secondary-background-color); border-radius: 16px; padding: 24px 20px; border: 1px solid rgba(128,128,128,0.1); text-align:center;} .kpi-value {font-size:2.2rem; font-weight:900; margin-bottom:12px;} .delta-pos {background:#21c3541f; color:#21c354; padding:4px 10px; border-radius:12px; font-weight:700;}</style>""", unsafe_allow_html=True)
    ck = st.columns(4)
    with ck[0]: st.markdown(f'<div class="kpi-card"><div style="opacity:0.7">期末資產</div><div class="kpi-value">{fmt_money(stats_lrs[0]*capital)}</div><span class="delta-pos">+{gap_a:.2f}% (vs 槓桿)</span></div>', unsafe_allow_html=True)
    with ck[1]: st.markdown(f'<div class="kpi-card"><div style="opacity:0.7">CAGR</div><div class="kpi-value">{stats_lrs[2]:.2%}</div><span class="delta-pos">+{gap_c:.2f}%</span></div>', unsafe_allow_html=True)
    with ck[2]: st.markdown(f'<div class="kpi-card"><div style="opacity:0.7">波動率</div><div class="kpi-value">{stats_lrs[4]:.2%}</div></div>', unsafe_allow_html=True)
    with ck[3]: st.markdown(f'<div class="kpi-card"><div style="opacity:0.7">最大回撤</div><div class="kpi-value">{stats_lrs[3]:.2%}</div></div>', unsafe_allow_html=True)

    # ------------------------------------------------------
    # 視覺化輸出 4: 高級 HTML 獎盃表格
    # ------------------------------------------------------
    st.write("<br>", unsafe_allow_html=True)
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    data_table = {
        f"<b>{lev_label}</b> (LRS+DCA)": [stats_lrs[0]*capital, stats_lrs[1], stats_lrs[2], stats_lrs[7], stats_lrs[3], stats_lrs[4], stats_lrs[5], stats_lrs[6], (df["Signal"]!=0).sum()],
        f"<b>{lev_label}</b> (BH)": [stats_lev[0]*capital, stats_lev[1], stats_lev[2], stats_lev[7], stats_lev[3], stats_lev[4], stats_lev[5], stats_lev[6], 0],
        f"<b>{base_label}</b> (BH)": [stats_base[0]*capital, stats_base[1], stats_base[2], stats_base[7], stats_base[3], stats_base[4], stats_base[5], stats_base[6], 0]
    }
    df_v = pd.DataFrame(data_table, index=metrics_order)

    # 生成 HTML 表格
    html = '<style>.comp-table {width:100%; border-collapse:separate; border-spacing:0; border-radius:12px; border:1px solid rgba(128,128,128,0.1); overflow:hidden;} .comp-table th {background:#80808010; padding:15px; text-align:center;} .comp-table td {padding:12px; text-align:center; border-bottom:1px solid rgba(128,128,128,0.05);} .metric-name {text-align:left !important; font-weight:500; background:#80808005;} .win {font-weight:bold; color:var(--text-color);}</style>'
    html += '<table class="comp-table"><thead><tr><th style="text-align:left">指標</th>'
    for col in df_v.columns: html += f'<th>{col}</th>'
    html += '</tr></thead><tbody>'

    for metric in metrics_order:
        html += f'<tr><td class="metric-name">{metric}</td>'
        row_vals = df_v.loc[metric].values
        # 判斷好壞邏輯
        is_inv = metric in ["最大回撤 (MDD)", "年化波動", "交易次數"]
        best_val = min(row_vals) if is_inv else max(row_vals)
        
        for val in row_vals:
            is_win = (val == best_val) and (metric != "交易次數")
            # 格式化
            if "資產" in metric: d_txt = fmt_money(val)
            elif any(x in metric for x in ["率", "報酬", "波動", "MDD"]): d_txt = fmt_pct(val)
            elif "次數" in metric: d_txt = fmt_int(val)
            else: d_txt = fmt_num(val)
            
            win_tag = '🏆' if is_win else ''
            style = 'class="win"' if is_win else ''
            html += f'<td {style}>{d_txt} {win_tag}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    st.write(html, unsafe_allow_html=True)
