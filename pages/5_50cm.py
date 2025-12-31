###############################################################
# app.py — 0050 雙向乖離動態槓桿 (完整還原 UI 版)
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

def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"

###############################################################
# 3. UI 介面佈局
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 單一標的動態槓桿系統</h1>", unsafe_allow_html=True)

available_etfs = get_csv_list()
if not available_etfs:
    st.error("❌ data 資料夾內找不到任何 CSV 檔案"); st.stop()

# --- 標的與區間 ---
target_label = st.selectbox("選擇交易標的 (訊號來源)", available_etfs, 
                            index=available_etfs.index("00631L.TW") if "00631L.TW" in available_etfs else 0)

df_preview = load_csv(target_label)
s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()

# 📌 樣式還原：可回測區間藍框
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

# --- 參數設定 ---
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
# 4. 回測執行
###############################################################

if st.button("啟動回測引擎 🚀"):
    start_buf = start - dt.timedelta(days=int(sma_window * 2))
    df = load_csv(target_label).loc[start_buf:end]
    # 額外讀取 0050 作為固定對照基準
    df_ref = load_csv("0050.TW").loc[start:end] if "0050.TW" in available_etfs else pd.DataFrame()

    if df.empty: st.error("⚠️ 數據讀取失敗"); st.stop()

    df["MA"] = df["Price"].rolling(sma_window).mean()
    df["Bias"] = (df["Price"] - df["MA"]) / df["MA"]
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
    
    # 基準 0050 計算
    if not df_ref.empty:
        df_ref["Equity"] = df_ref["Price"] / df_ref["Price"].iloc[0]
        s_ref = get_stats(df_ref["Equity"], df_ref["Price"].pct_change().fillna(0), y_len)
    else: s_ref = sb # 若無 0050 則用標的自身替代

    # ------------------------------------------------------
    # 5. UI 還原：KPI 卡片
    # ------------------------------------------------------
    st.markdown("""
        <style>
        .kpi-container { display: flex; gap: 20px; margin-bottom: 25px; }
        .kpi-card { 
            background: white; border-radius: 16px; padding: 24px; flex: 1;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; text-align: left;
        }
        .kpi-label { color: #666; font-size: 0.95rem; margin-bottom: 8px; font-weight: 500; }
        .kpi-val { font-size: 2.2rem; font-weight: 900; color: #1a1a1a; margin-bottom: 12px; }
        .delta-tag { 
            display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 700;
        }
        .delta-pos { background: #e6f7ed; color: #21c354; }
        .delta-neg { background: #fff1f0; color: #ff4d4f; }
        </style>
    """, unsafe_allow_html=True)

    k_cols = st.columns(4)
    
    def render_kpi(col, label, val, delta, is_better_if_higher=True):
        style = "delta-pos" if (delta >= 0 if is_better_if_higher else delta <= 0) else "delta-neg"
        col.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-val">{val}</div>
                <div class="delta-tag {style}">{delta:+.2%} (vs 標的)</div>
            </div>
        """, unsafe_allow_html=True)

    render_kpi(k_cols[0], "期末資產", fmt_money(sl[0]*capital), (sl[0]/sb[0]-1))
    render_kpi(k_cols[1], "CAGR", fmt_pct(sl[2]), (sl[2]-sb[2]))
    render_kpi(k_cols[2], "波動率", fmt_pct(sl[4]), (sl[4]-sb[4]), is_better_if_higher=False)
    render_kpi(k_cols[3], "最大回撤", fmt_pct(sl[3]), (sl[3]-sb[3]), is_better_if_higher=False)

    # ------------------------------------------------------
    # 6. UI 還原：績效總表 (HTML Table)
    # ------------------------------------------------------
    st.markdown("### 🏆 策略績效總表")
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "交易次數"]
    
    # 準備表格數據
    data_map = {
        f"<b>{target_label}</b><br><small>LRS+DCA</small>": [sl[0]*capital, sl[1], sl[2], sl[7], sl[3], sl[4], sl[5], (df["Signal"]!=0).sum()],
        f"<b>{target_label}</b><br><small>Buy & Hold</small>": [sb[0]*capital, sb[1], sb[2], sb[7], sb[3], sb[4], sb[5], 0],
        f"<b>0050 元大台灣50</b><br><small>Buy & Hold</small>": [s_ref[0]*capital, s_ref[1], s_ref[2], s_ref[7], s_ref[3], s_ref[4], s_ref[5], 0]
    }
    
    html = """
    <style>
    .ctable { width: 100%; border-collapse: collapse; border: 1px solid #eee; font-size: 0.95rem; border-radius: 8px; overflow: hidden; }
    .ctable th { background: #f8f9fa; padding: 15px; text-align: center; border-bottom: 2px solid #eee; color: #444; }
    .ctable td { padding: 12px; text-align: center; border-bottom: 1px solid #eee; }
    .m-name { background: #fcfcfc; text-align: left !important; font-weight: 500; width: 150px; }
    .win-cell { font-weight: bold; color: #1a1a1a; }
    </style>
    <table class="ctable">
        <thead><tr><th>指標</th>"""
    for col in data_map.keys(): html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"

    for idx, m in enumerate(metrics):
        html += f"<tr><td class='m-name'>{m}</td>"
        row_vals = [data_map[k][idx] for k in data_map.keys()]
        
        # 判斷誰是贏家 (i=0 是我們的策略)
        is_winning = False
        if idx < 4 or m == "Sharpe Ratio": # 越高越好
            if row_vals[0] == max(row_vals): is_winning = True
        elif idx in [4, 5]: # 越低越好
            if row_vals[0] == min(row_vals): is_winning = True

        for i, v in enumerate(row_vals):
            if "資產" in m: txt = fmt_money(v)
            elif any(x in m for x in ["率", "報酬", "MDD", "波動"]): txt = fmt_pct(v)
            elif "次數" in m: txt = fmt_int(v)
            else: txt = fmt_num(v)
            
            win_icon = " 🏆" if (i == 0 and is_winning) else ""
            style = "class='win-cell'" if i == 0 else ""
            html += f"<td {style}>{txt}{win_icon}</td>"
        html += "</tr>"
    
    st.write(html + "</tbody></table>", unsafe_allow_html=True)

    # --- 圖表部分 ---
    st.write("### 📈 走勢圖分析")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="本策略", line=dict(width=3, color="#00D494")))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]-1, name=f"{target_label} B&H", line=dict(color="gray", dash='dash')))
    fig.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.caption("免責聲明：本工具僅供策略研究參考，投資必有風險。")
