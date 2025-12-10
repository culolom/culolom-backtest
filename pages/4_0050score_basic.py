###############################################################
# pages/4_Macro_Strategy.py — 國發會景氣燈號策略 (真實延遲版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys



###############################################################
# 設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    import matplotlib.font_manager as fm
    import matplotlib
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"

st.set_page_config(page_title="景氣燈號策略", page_icon="🚦", layout="wide")

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.5em;'>🚦 國發會景氣燈號策略 (Macro Strategy)</h1>", unsafe_allow_html=True)
st.markdown("<b>股市名言：「藍燈買股票，紅燈數鈔票」。</b>", unsafe_allow_html=True)

# 燈號說明
st.info("""
**🚦 官方燈號定義：** 🔵藍燈(9-16) | 🔵🟡黃藍(17-22) | 🟢綠燈(23-31) | 🟡🔴黃紅(32-37) | 🔴紅燈(38-45)
""")

DATA_DIR = Path("data")

###############################################################
# 資料處理
###############################################################

def parse_magic_date(x):
    s = str(x).strip()
    try:
        return pd.to_datetime(s)
    except:
        pass
    try:
        if len(s) == 6 and s.isdigit(): return dt.datetime.strptime(s, "%Y%m")
        if len(s) == 5 and s.isdigit(): return dt.datetime(int(s[:3])+1911, int(s[3:]), 1)
        if "/" in s or "-" in s:
            parts = s.replace("/", "-").split("-")
            if len(parts) >= 2:
                y = int(parts[0])
                if y < 1911: y += 1911
                return dt.datetime(y, int(parts[1]), 1)
    except: return pd.NaT
    return pd.NaT

def load_csv_smart(symbol: str) -> pd.DataFrame:
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv", f"{symbol.lower()}.csv"]
    path = None
    for c in candidates:
        p = DATA_DIR / c
        if p.exists():
            path = p
            break
    if path is None: return pd.DataFrame()
    
    try:
        df = pd.read_csv(path)
        date_col = df.columns[0]
        for c in df.columns:
            if "date" in str(c).lower() or "日期" in str(c): date_col = c; break
        
        df["Date_Clean"] = df[date_col].apply(parse_magic_date)
        df = df.dropna(subset=["Date_Clean"]).set_index("Date_Clean").sort_index()
        
        target_col = None
        priority = ["Adj Close", "Close", "Score", "Price"]
        for p in priority:
            if p in df.columns: target_col = p; break
        if target_col is None:
            for c in df.columns:
                if "分" in str(c) or "score" in str(c).lower(): target_col = c; break
        if target_col is None: target_col = df.columns[-1]
            
        df["Price"] = pd.to_numeric(df[target_col], errors='coerce')
        return df[["Price"]].dropna()
    except: return pd.DataFrame()

###############################################################
# UI 設定
###############################################################

st.divider()
score_file = "SCORE" 

col1, col2 = st.columns(2)
with col1: 
    ticker = st.selectbox("📈 交易標的", ["0050.TW", "006208.TW"], index=0)
with col2: 
    initial_pos_option = st.radio("🚀 初始部位狀態", ["已持有 (滿倉起跑)","空手 (等待訊號)" ], horizontal=True)

df_check_p = load_csv_smart(ticker)
df_check_s = load_csv_smart(score_file)

valid_start, valid_end = dt.date(2003, 1, 1), dt.date.today()

if not df_check_p.empty and not df_check_s.empty:
    v_start = max(df_check_p.index.min().date(), df_check_s.index.min().date())
    v_end = min(df_check_p.index.max().date(), df_check_s.index.max().date())
    if v_start <= v_end:
        valid_start, valid_end = v_start, v_end
        st.info(f"📌 資料區間：{valid_start} ~ {valid_end}")
    else:
        st.error("❌ 資料日期無交集")
        st.stop()

col_d1, col_d2, col_d3 = st.columns(3)
with col_d1: start_date = st.date_input("開始日期", value=valid_start, min_value=valid_start, max_value=valid_end)
with col_d2: end_date = st.date_input("結束日期", value=valid_end, min_value=valid_start, max_value=valid_end)
with col_d3: initial_capital = st.number_input("初始本金", value=1_000_000, step=100_000)

# 補充說明與參數
st.info("""
💡 **交易規則說明**：
景氣對策信號通常於每月 **27號** 公佈「上個月」的分數。
本策略設定為 **「公佈日下個月的第一個交易日」** 進行買賣，以符合真實操作。
(例如：1月分數 -> 2/27 公佈 -> 3/1 進場，資料延遲約 2 個月)
""")

col_p1, col_p2 = st.columns(2)
with col_p1: buy_threshold = st.number_input("🔵 買進門檻 (<=)", 9, 45, 16)
with col_p2: sell_threshold = st.number_input("🔴 賣出門檻 (>=)", 9, 45, 32)

###############################################################
# 回測與繪圖
###############################################################

if st.button("開始回測 🚀", type="primary"):
    with st.spinner("正在計算..."):
        # 1. 準備資料
        df_price = df_check_p.loc[str(start_date):str(end_date)]
        df_score = df_check_s
        
        if df_price.empty: st.error("無資料"); st.stop()

        df = df_price.rename(columns={"Price": "Close"}).copy()
        df_score_daily = df_score.reindex(df.index, method='ffill')
        df["Score_Raw"] = df_score_daily["Price"]
        
        # 3. 處理延遲 (固定 2 個月)
        # 1月分數(1/1) -> 3月交易(3/1)，相差約 40 個交易日
        shift_days = 40 
        df["Score_Signal"] = df["Score_Raw"].shift(shift_days)
        df = df.dropna()

        if df.empty: st.error("資料不足"); st.stop()

        # 2. 訊號
        current_pos = 1 if "已持有" in initial_pos_option else 0
        pos_list = []
        for s in df["Score_Signal"].values:
            if s <= buy_threshold: current_pos = 1
            elif s >= sell_threshold: current_pos = 0
            pos_list.append(current_pos)
        df["Position"] = pos_list
        
        # 3. 績效
        df["Ret"] = df["Close"].pct_change().fillna(0)
        df["Strategy_Ret"] = df["Position"].shift(1) * df["Ret"]
        df["Equity_Strategy"] = initial_capital * (1 + df["Strategy_Ret"]).cumprod()
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret"]).cumprod()

        # 4. KPI
        def calc_metrics(s):
            tr = (s.iloc[-1]/initial_capital)-1
            days = (s.index[-1]-s.index[0]).days
            cagr = (1+tr)**(365/days)-1 if days>0 else 0
            mdd = (s/s.cummax()-1).min()
            vol = s.pct_change().std()*np.sqrt(252)
            sharpe = (cagr-0.04)/vol if vol>0 else 0
            return tr, cagr, mdd, sharpe

        ret_s, cagr_s, mdd_s, sharpe_s = calc_metrics(df["Equity_Strategy"])
        ret_b, cagr_b, mdd_b, sharpe_b = calc_metrics(df["Equity_Benchmark"])

        # 顯示 KPI
        st.markdown("""<style>.kpi-card {background-color: var(--secondary-background-color); border-radius: 12px; padding: 15px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: 1px solid rgba(128,128,128,0.1);} .kpi-val {font-size: 1.6rem; font-weight: 700;} .kpi-lbl {opacity: 0.7;} .kpi-sub {font-size: 0.8rem; color: #666;}</style>""", unsafe_allow_html=True)
        def kpi(l, v, b, p=True):
            vs, bs = (f"{v:.1%}", f"{b:.1%}") if p else (f"{v:.2f}", f"{b:.2f}")
            return f"""<div class="kpi-card"><div class="kpi-lbl">{l}</div><div class="kpi-val">{vs}</div><div class="kpi-sub">基準: {bs}</div></div>"""

        r1 = st.columns(4)
        with r1[0]: st.markdown(kpi("總報酬率", ret_s, ret_b), unsafe_allow_html=True)
        with r1[1]: st.markdown(kpi("CAGR (年化)", cagr_s, cagr_b), unsafe_allow_html=True)
        with r1[2]: st.markdown(kpi("最大回撤", mdd_s, mdd_b), unsafe_allow_html=True)
        with r1[3]: st.markdown(kpi("夏普值", sharpe_s, sharpe_b, False), unsafe_allow_html=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # 📊 雙圖表合併顯示
        # ---------------------------------------------------------
        tab1, tab2 = st.tabs(["🚦 買賣點位與燈號 (主圖)", "💰 資金成長曲線"])

        with tab1:
            # 準備買賣點
            buys = df[(df["Position"] == 1) & (df["Position"].shift(1) == 0)]
            sells = df[(df["Position"] == 0) & (df["Position"].shift(1) == 1)]

            # 建立雙軸圖表
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, row_heights=[0.7, 0.3],
                                subplot_titles=(f"{ticker} 股價與進出場點", "景氣對策信號 (五色區間)"))

            # 1. 上圖：股價 + 買賣點
            fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="股價", line=dict(color="#333", width=1)), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=buys.index, y=buys["Close"], mode="markers", name="買進 (藍燈)",
                marker=dict(symbol="triangle-up", color="#0044FF", size=12, line=dict(width=1, color="white"))
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=sells.index, y=sells["Close"], mode="markers", name="賣出 (紅燈)",
                marker=dict(symbol="triangle-down", color="#FF0044", size=12, line=dict(width=1, color="white"))
            ), row=1, col=1)

            # 2. 下圖：分數 + 五色背景
            fig.add_trace(go.Scatter(x=df.index, y=df["Score_Signal"], name="分數", line=dict(color="#555", width=2)), row=2, col=1)
            
            bands = [
                (9, 16, "藍", "#2E86C1"), (17, 22, "黃藍", "#76D7C4"), 
                (23, 31, "綠", "#28B463"), (32, 37, "黃紅", "#F1C40F"), 
                (38, 55, "紅", "#E74C3C")
            ]
            for y0, y1, txt, color in bands:
                fig.add_hrect(
                    y0=y0, y1=y1, fillcolor=color, opacity=0.2, layer="below", 
                    row=2, col=1
                )

            fig.add_hline(y=buy_threshold, line_dash="dash", line_color="blue", row=2, col=1)
            fig.add_hline(y=sell_threshold, line_dash="dash", line_color="red", row=2, col=1)

            fig.update_layout(height=600, template="plotly_white", hovermode="x unified", showlegend=True)
            fig.update_yaxes(title_text="股價", row=1, col=1)
            fig.update_yaxes(title_text="分數", range=[9, 48], row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="策略資產", line=dict(color="#00C853", width=2)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name="買進持有", line=dict(color="#B0BEC5", width=2, dash='dot')))
            fig_eq.update_layout(height=450, template="plotly_white", hovermode="x unified", title="資產成長比較")
            st.plotly_chart(fig_eq, use_container_width=True)

        # 交易列表
        st.markdown("### 📋 交易明細")
        trades = []
        temp_buy = None
        signals = df[df["Position"] != df["Position"].shift(1)]
        
        if not df.empty and df["Position"].iloc[0] == 1 and (df.index[0] not in signals.index):
             temp_buy = (df.index[0], df["Close"].iloc[0])

        for date, row in signals.iterrows():
            if row["Position"] == 1: 
                temp_buy = (date, row["Close"])
            elif row["Position"] == 0 and temp_buy:
                b_d, b_p = temp_buy
                ret = (row["Close"]-b_p)/b_p
                trades.append({"買入": b_d.strftime("%Y-%m-%d"), "買價": b_p, "賣出": date.strftime("%Y-%m-%d"), "賣價": row["Close"], "報酬率": ret})
                temp_buy = None
        
        if trades:
            st.dataframe(pd.DataFrame(trades).style.format({"買價":"{:.2f}","賣價":"{:.2f}","報酬率":"{:.2%}"}).background_gradient(cmap="RdYlGn", subset=["報酬率"]), use_container_width=True)
        else:
            st.info("區間內無完整一進一出之交易")
