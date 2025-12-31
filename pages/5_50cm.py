###############################################################
# app.py — 0050 雙向乖離動態槓桿 (三圖連動 + 布林通道版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys

###############################################################
# 1. 環境設定與名稱映射
###############################################################

TICKER_NAMES = {
    "0050.TW": "0050 元大台灣50",
    "006208.TW": "006208 富邦台50",
    "00631L.TW": "00631L 元大台灣50正2",
    "00635U.TW": "00635U 元大標普500",
    "00646.TW": "00646 元大標普500",
    "00647L.TW": "00647L 元大標普500正2",
    "00662.TW": "00662 富邦 NASDAQ",
    "00663L.TW": "00663L 國泰台灣加權正2",
    "00670L.TW": "00670L 富邦 NASDAQ 正2",
    "00675L.TW": "00675L 富邦台灣加權正2",
    "00685L.TW": "00685L 群益台灣加權正2",
    "00878.TW": "00878 國泰永續高股息",
    "BTC-USD": "BTC-USD 比特幣"
}

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="0050 雙向乖離動態槓桿系統", page_icon="📈", layout="wide")

# 🔒 驗證守門員
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import auth 
    if not auth.check_password(): st.stop()
except: pass 

###############################################################
# 2. 核心計算函數
###############################################################

DATA_DIR = Path("data")

def get_csv_list():
    if not DATA_DIR.exists(): return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

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
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"

###############################################################
# 3. UI 介面
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.1em;'>📊 單一標的動態槓桿系統</h1>", unsafe_allow_html=True)

available_ids = get_csv_list()
if not available_ids:
    st.error("❌ data 資料夾內找不到任何 CSV 檔案"); st.stop()

st.markdown("##### 原型 ETF（訊號來源）")
target_id = st.selectbox(
    "", 
    available_ids, 
    label_visibility="collapsed",
    index=available_ids.index("00631L.TW") if "00631L.TW" in available_ids else 0,
    format_func=lambda x: TICKER_NAMES.get(x, x)
)

ch_name = TICKER_NAMES.get(target_id, target_id)
df_preview = load_csv(target_id)
s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

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
# 4. 回測執行邏輯
###############################################################

if st.button("啟動回測引擎 🚀"):
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df = load_csv(target_id).loc[start_buf:end]
    
    if df.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    # 計算均線與乖離率
    df["MA"] = df["Price"].rolling(sma_window).mean()
    df["Bias"] = (df["Price"] - df["MA"]) / df["MA"]
    
    # --- 新增：計算布林通道 (Bollinger Bands) ---
    df["Std"] = df["Price"].rolling(sma_window).std()
    df["Upper"] = df["MA"] + (df["Std"] * 2)
    df["Lower"] = df["MA"] - (df["Std"] * 2)
    
    df = df.dropna(subset=["MA"]).loc[start:end]
    
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
                if p0 <= m0: curr_pos, sig = 1.0, 1
                if enable_arb and bias_pct >= arb_bias_trigger and arb_cd == 0 and curr_pos > 0:
                    curr_pos = max(0.0, curr_pos - (arb_reduce_pct / 100.0))
                    sig, arb_cd = 3, arb_cooldown
            else: curr_pos = 0.0
        else:
            can_buy = True 
            if p0 > m0: curr_pos, sig = 0.0, -1
            elif enable_dca and curr_pos < 1.0:
                if bias_pct <= dca_bias_trigger and dca_cd == 0:
                    curr_pos = min(1.0, curr_pos + (dca_pct / 100.0))
                    sig, dca_cd = 2, dca_cooldown
        pos[i], sigs[i] = round(curr_pos, 4), sig

    df["Signal"], df["Position"] = sigs, pos
    equity = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity_Strategy"] = equity
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Equity_BH"] = (df["Price"] / df["Price"].iloc[0])
    df["Return_BH"] = df["Price"].pct_change().fillna(0)
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity_Strategy"], df["Return_Strategy"], y_len)
    sb = get_stats(df["Equity_BH"], df["Return_BH"], y_len)

    # KPI 卡片渲染 (略過不變)
    st.markdown("""<style>.kpi-card { background: white; border-radius: 16px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; text-align: left; } .kpi-label { color: #8c8c8c; font-size: 1rem; margin-bottom: 12px; font-weight: 500; } .kpi-val { font-size: 2.3rem; font-weight: 900; color: #1a1a1a; margin-bottom: 15px; } .delta-tag { display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 0.9rem; font-weight: 700; } .delta-pos { background: #e6f7ed; color: #21c354; } .delta-neg { background: #fff1f0; color: #ff4d4f; } </style> """, unsafe_allow_html=True)
    k_cols = st.columns(4)
    def render_kpi(col, label, val, delta, is_better_if_higher=True):
        is_good = (delta >= 0) if is_better_if_higher else (delta <= 0)
        style = "delta-pos" if is_good else "delta-neg"
        col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-val">{val}</div><div class="delta-tag {style}">{delta:+.2%} (vs 標的)</div></div>', unsafe_allow_html=True)
    render_kpi(k_cols[0], "期末資產", fmt_money(sl[0]*capital), (sl[0]/sb[0]-1))
    render_kpi(k_cols[1], "CAGR", fmt_pct(sl[2]), (sl[2]-sb[2]))
    render_kpi(k_cols[2], "波動率", fmt_pct(sl[4]), (sl[4]-sb[4]), is_better_if_higher=False)
    render_kpi(k_cols[3], "最大回撤", fmt_pct(sl[3]), (sl[3]-sb[3]), is_better_if_higher=False)

    # 績效總表 (略過不變)
    st.markdown(f"### 🏆 策略績效總表：{ch_name}")
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    data_map = { f"<b>{ch_name}</b><br><small>LRS+DCA</small>": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()], f"<b>{ch_name}</b><br><small>Buy & Hold</small>": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0] }
    html = '<style>.ctable { width: 100%; border-collapse: collapse; border: 1px solid #f0f0f0; margin-top:10px; } .ctable th { background: #ffffff; padding: 20px; border-bottom: 1px solid #f0f0f0; color: #595959; } .ctable td { padding: 18px; text-align: center; border-bottom: 1px solid #f0f0f0; } .m-name { text-align: left !important; font-weight: 500; }</style>'
    html += '<table class="ctable"><thead><tr><th style="text-align:left">指標</th>'
    for col in data_map.keys(): html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for idx, m in enumerate(metrics):
        html += f"<tr><td class='m-name'>{m}</td>"
        row_vals = [data_map[k][idx] for k in data_map.keys()]
        for i, v in enumerate(row_vals):
            if "資產" in m: txt = fmt_money(v)
            elif any(x in m for x in ["率", "報酬", "MDD", "波動"]): txt = fmt_pct(v)
            elif "次數" in m: txt = fmt_int(v)
            else: txt = fmt_num(v)
            is_win = (i == 0 and ((idx in [0,1,2,3,6] and row_vals[0] >= row_vals[1]) or (idx in [4,5] and row_vals[0] <= row_vals[1])))
            style = "font-weight:800; color:#1a1a1a;" if i == 0 else "color:#595959;"
            html += f"<td style='{style}'>{txt}{' 🏆' if is_win else ''}</td>"
        html += "</tr>"
    st.write(html + "</tbody></table>", unsafe_allow_html=True)

    # ------------------------------------------------------
    # 7. 整合圖表：三圖連動版 (含布林通道)
    # ------------------------------------------------------
    st.markdown("### 📈 策略深度視覺化 (時間軸連動 + 布林通道)")

    fig_master = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05,
        subplot_titles=("資金曲線比較", "策略訊號與執行價格 (含布林通道)", "乖離率變動與觸發門檻"),
        row_heights=[0.3, 0.4, 0.3]
    )

    # --- 第一列：資金曲線 ---
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="LRS+DCA", line=dict(width=2.5, color="#00D494")), row=1, col=1)
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name="Buy & Hold", line=dict(color="#FF4D4F", dash='dash')), row=1, col=1)

    # --- 第二列：股價與訊號 + 布林通道 ---
    # 1. 布林上軌 (隱藏圖例，因為重點在區間)
    fig_master.add_trace(
        go.Scatter(x=df.index, y=df["Upper"], name="布林上軌", line=dict(color="rgba(173, 181, 189, 0.2)", width=1), showlegend=False), 
        row=2, col=1
    )
    # 2. 布林下軌 (與上軌之間填滿顏色)
    fig_master.add_trace(
        go.Scatter(x=df.index, y=df["Lower"], name="布林通道區間", fill='tonexty', fillcolor='rgba(173, 181, 189, 0.1)', line=dict(color="rgba(173, 181, 189, 0.2)", width=1)), 
        row=2, col=1
    )
    
    # 3. 股價與均線
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Price"], name=f"{ch_name} 股價", line=dict(color="#636EFA", width=1.5)), row=2, col=1)
    fig_master.add_trace(go.Scatter(x=df.index, y=df["MA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)), row=2, col=1)
    
    # 4. 交易訊號點
    colors = {1: ("買進", "#00C853", "triangle-up"), -1: ("賣出", "#D50000", "triangle-down"), 2: ("加碼", "#2E7D32", "circle"), 3: ("減碼", "#FF9800", "diamond")}
    for v, (l, c, s) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty:
            fig_master.add_trace(go.Scatter(x=pts.index, y=pts["Price"], mode="markers", name=l, marker=dict(color=c, size=10, symbol=s), showlegend=False), row=2, col=1)

    # --- 第三列：乖離率走勢 ---
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Bias"] * 100, name="乖離率 (%)", line=dict(color="#AB63FA"), fill='tozeroy', fillcolor='rgba(171, 99, 250, 0.1)'), row=3, col=1)
    fig_master.add_hline(y=0, line_dash="dash", line_color="#7f7f7f", opacity=0.5, row=3, col=1)
    if enable_dca: fig_master.add_hline(y=dca_bias_trigger, line_dash="dot", line_color="#2E7D32", row=3, col=1, annotation_text="加碼區")
    if enable_arb: fig_master.add_hline(y=arb_bias_trigger, line_dash="dot", line_color="#D50000", row=3, col=1, annotation_text="減碼區")
    for v, (l, c, s) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty: fig_master.add_trace(go.Scatter(x=pts.index, y=pts["Bias"] * 100, mode="markers", showlegend=False, marker=dict(color=c, size=8, symbol=s)), row=3, col=1)

    # 全域佈局
    fig_master.update_layout(height=1000, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig_master.update_yaxes(title_text="累積報酬率", tickformat=".0%", row=1, col=1)
    fig_master.update_yaxes(title_text="價格", row=2, col=1)
    fig_master.update_yaxes(title_text="乖離率 (%)", ticksuffix="%", row=3, col=1)

    st.plotly_chart(fig_master, use_container_width=True)
    st.caption("免責聲明：本工具僅供策略研究參考，投資必有風險。")
