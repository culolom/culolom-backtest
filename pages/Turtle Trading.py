###############################################################
# app.py — 0050 海龜交易法 (修正版唐奇安通道系統)
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

st.set_page_config(page_title="海龜交易法 - 唐奇安通道系統", page_icon="🐢", layout="wide")

# 🔒 驗證守門員 (保留你的設定)
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

st.markdown("<h1 style='margin-bottom:0.1em;'>🐢 海龜交易法 (唐奇安通道)</h1>", unsafe_allow_html=True)

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

col_p1, col_p2, col_p3 = st.columns(3)
start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
end = col_p2.date_input("結束日期", value=s_max)
capital = col_p3.number_input("投入本金", 1000, 10000000, 100000, step=10000)

st.write("---")
st.markdown("### ⚙️ 策略參數設定")

turtle_mode = st.radio(
    "選擇海龜策略模式", 
    ["海龜短線 (20日突破進 / 10日跌破出)", "海龜長線 (55日突破進 / 20日跌破出)", "自訂參數"], 
    horizontal=True
)

col_set1, col_set2, col_set3 = st.columns(3)

# 根據選擇自動帶入參數
if "短線" in turtle_mode:
    def_entry, def_exit = 20, 10
elif "長線" in turtle_mode:
    def_entry, def_exit = 55, 20
else:
    def_entry, def_exit = 20, 10

with col_set1:
    entry_window = st.number_input("進場：唐奇安上軌 (突破 N 日最高價)", 5, 240, def_entry, step=1, disabled=("自訂" not in turtle_mode))
with col_set2:
    exit_window = st.number_input("出場：唐奇安下軌 (跌破 M 日最低價)", 5, 240, def_exit, step=1, disabled=("自訂" not in turtle_mode))
with col_set3:
    st.markdown("<br>", unsafe_allow_html=True)
    use_200sma_filter = st.checkbox("啟用 200 日均線趨勢濾網 (僅在均線之上做多)", value=True)

###############################################################
# 4. 回測執行邏輯
###############################################################

if st.button("啟動回測引擎 🚀"):
    # 預留緩衝天數以計算長週期指標 (確保 200MA 能算出來)
    max_window = max(entry_window, exit_window, 200 if use_200sma_filter else 0)
    start_buf = start - dt.timedelta(days=int(max_window * 2))
    df = load_csv(target_id).loc[start_buf:end]
    
    if df.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    # 計算唐奇安通道與指標 (shift(1) 是為了避免用到當天的最高/低價，形成未來函數)
    df["Donchian_High"] = df["Price"].rolling(entry_window).max().shift(1)
    df["Donchian_Low"] = df["Price"].rolling(exit_window).min().shift(1)
    df["Donchian_Mid"] = (df["Donchian_High"] + df["Donchian_Low"]) / 2
    df["SMA_200"] = df["Price"].rolling(200).mean()
    
    # 裁切回使用者選擇的時間段
    df = df.dropna(subset=["Donchian_High", "Donchian_Low", "SMA_200" if use_200sma_filter else "Price"]).loc[start:end]
    
    sigs, pos = [0] * len(df), [0.0] * len(df)
    in_position = False

    for i in range(1, len(df)):
        p = df["Price"].iloc[i]
        don_h = df["Donchian_High"].iloc[i]
        don_l = df["Donchian_Low"].iloc[i]
        sma200 = df["SMA_200"].iloc[i]
        
        sig = 0 # 0:無動作, 1:建倉, -1:平倉
        
        if not in_position:
            # 【進場】突破 N 日最高價
            trend_condition = (p > sma200) if use_200sma_filter else True
            if p > don_h and trend_condition:
                in_position = True
                curr_pos = 1.0 # 滿倉進場
                sig = 1
        else:
            # 【出場】跌破 M 日最低價
            if p < don_l:
                in_position = False
                curr_pos = 0.0 # 空倉
                sig = -1

        pos[i] = curr_pos if in_position else 0.0
        sigs[i] = sig

    df["Signal"], df["Position"] = sigs, pos
    
    # 計算資金曲線
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

    # KPI 卡片與績效總表
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

    st.markdown(f"### 🏆 策略績效總表：{ch_name}")
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    data_map = { f"<b>{ch_name}</b><br><small>海龜通道策略</small>": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()], f"<b>{ch_name}</b><br><small>Buy & Hold</small>": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0] }
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
    # 7. 整合圖表：唐奇安通道視覺化
    # ------------------------------------------------------
    st.markdown("### 📈 唐奇安通道與交易訊號")

    fig_master = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08,
        subplot_titles=("資金曲線比較", "唐奇安通道 (Donchian Channel) 與買賣點"),
        row_heights=[0.3, 0.7]
    )

    # --- 第一列：資金曲線 ---
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="海龜策略", line=dict(width=2.5, color="#00D494")), row=1, col=1)
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name="Buy & Hold", line=dict(color="#FF4D4F", dash='dash')), row=1, col=1)

    # --- 第二列：通道與訊號 ---
    # 1. 唐奇安上軌 (進場線)
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Donchian_High"], name=f"{entry_window}日上阻力線 (做多)", line=dict(color="#1890FF", width=1.5)), row=2, col=1)
    
    # 2. 唐奇安下軌 (出場線) - 畫在同一張圖並填滿顏色形成通道
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Donchian_Low"], name=f"{exit_window}日下支撐線 (平倉)", fill='tonexty', fillcolor='rgba(24, 144, 255, 0.05)', line=dict(color="#FF4D4F", width=1.5)), row=2, col=1)
    
    # 3. 200 SMA (若啟用)
    if use_200sma_filter:
        fig_master.add_trace(go.Scatter(x=df.index, y=df["SMA_200"], name="200日均線 (趨勢濾網)", line=dict(color="#FFA15A", width=2, dash='dot')), row=2, col=1)

    # 4. 股價
    fig_master.add_trace(go.Scatter(x=df.index, y=df["Price"], name=f"{ch_name} 股價", line=dict(color="#1F2937", width=1.5)), row=2, col=1)
    
    # 5. 交易訊號點
    colors = {1: ("突破進場", "#00C853", "triangle-up"), -1: ("跌破出場", "#D50000", "triangle-down")}
    for v, (l, c, s) in colors.items():
        pts = df[df["Signal"] == v]
        if not pts.empty:
            fig_master.add_trace(go.Scatter(x=pts.index, y=pts["Price"], mode="markers", name=l, marker=dict(color=c, size=12, symbol=s), showlegend=True), row=2, col=1)

    # 全域佈局
    fig_master.update_layout(height=800, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig_master.update_yaxes(title_text="累積報酬率", tickformat=".0%", row=1, col=1)
    fig_master.update_yaxes(title_text="價格", row=2, col=1)

    st.plotly_chart(fig_master, use_container_width=True)
    st.caption("免責聲明：本工具僅供策略研究參考，投資必有風險。")
