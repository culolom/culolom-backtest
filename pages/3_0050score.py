###############################################################
# pages/4_Macro_Strategy.py — 國發會景氣燈號策略 (分批進出 + 真實延遲版)
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

st.markdown("<h1 style='margin-bottom:0.5em;'>🚦 國發會景氣燈號策略 (分批進出版)</h1>", unsafe_allow_html=True)
st.markdown("<b>進階策略：「藍燈分批買，紅燈分批賣」。平滑成本，降低風險。</b>", unsafe_allow_html=True)

# 燈號說明
st.info("""
**🚦 官方燈號定義：** 🔵藍燈(9-16) | 🔵🟡黃藍(17-22) | 🟢綠燈(23-31) | 🟡🔴黃紅(32-37) | 🔴紅燈(38-45)

景氣對策信號通常於每月 **27號** 公佈「上個月」的分數。
本策略設定為 **「公佈日下個月的第一個交易日」** 進行買賣，以符合真實操作。
(例如：1月分數 → 2/27 公佈 → 3/1 進場，資料延遲約 2 個月)
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

# 1. 定義對照表 (Key 是程式要用的代號, Value 是顯示給人看的名稱)
ticker_map = {
    "0050.TW": "0050 元大寶來台灣卓越50證券投資信託基金",
    "006208.TW": "006208 富邦台灣采吉50基金"
}

col1, col2 = st.columns(2)
with col1: 
    # 2. 修改 selectbox
    ticker = st.selectbox(
        "📈 交易標的", 
        options=list(ticker_map.keys()),  # 選項清單給 Key (0050.TW...)
        format_func=lambda x: ticker_map.get(x), # 顯示時轉換成中文名稱
        index=0
    )

with col2: 
    initial_pos_option = st.radio("🚀 初始部位狀態", ["已持有 (滿倉起跑)","空手 (等待訊號)" ], horizontal=True)

# 這裡 ticker 變數依然會是 "0050.TW" 或 "006208.TW"，所以讀檔邏輯不用改
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



c1, c2 = st.columns(2)
with c1:
    st.markdown("#### 🔵 買進設定 (藍燈)")
    buy_threshold = st.number_input("觸發分數 (<=)", 9, 45, 16)
    buy_batches = st.number_input("分批買進次數", 1, 12, 5, help="分成幾筆資金進場")
    buy_interval = st.number_input("買進間隔 (天)", 1, 90, 30, help="每隔幾天買一筆")

with c2:
    st.markdown("#### 🔴 賣出設定 (紅燈)")
    sell_threshold = st.number_input("觸發分數 (>=)", 9, 45, 32)
    sell_batches = st.number_input("分批賣出次數", 1, 12, 5, help="分成幾筆賣出")
    sell_interval = st.number_input("賣出間隔 (天)", 1, 90, 30, help="每隔幾天賣一筆")

st.caption(f"💡 邏輯：當分數 <= {buy_threshold}，每 {buy_interval} 天買進 1/{buy_batches} 資金。若脫離藍燈區尚未買滿，則一次補滿(歐印)。賣出同理。")

###############################################################
# 回測與繪圖
###############################################################

if st.button("開始回測 🚀", type="primary"):
    with st.spinner("正在模擬分批交易..."):
        # 1. 準備資料
        df_price = df_check_p.loc[str(start_date):str(end_date)]
        df_score = df_check_s
        
        if df_price.empty: st.error("無資料"); st.stop()

        df = df_price.rename(columns={"Price": "Close"}).copy()
        df_score_daily = df_score.reindex(df.index, method='ffill')
        df["Score_Raw"] = df_score_daily["Price"]
        
        # 3. 處理延遲 (固定 2 個月 = 40 交易日)
        shift_days = 40 
        df["Score_Signal"] = df["Score_Raw"].shift(shift_days)
        df = df.dropna()

        if df.empty: st.error("資料不足"); st.stop()

        # ==========================================
        # 核心邏輯：分批進出狀態機
        # ==========================================
        
        current_pos = 1.0 if "已持有" in initial_pos_option else 0.0
        pos_series = []
        mode = 'neutral'
        last_trade_idx = -9999
        batch_count_done = 0 
        
        scores = df["Score_Signal"].values
        
        for i in range(len(df)):
            s = scores[i]
            
            # --- 判斷觸發條件 ---
            # 1. 藍燈區 (買進訊號)
            if s <= buy_threshold:
                if mode != 'buying' and current_pos < 1.0:
                    mode = 'buying'
                    batch_count_done = 0
                    last_trade_idx = i - buy_interval - 1 
            
            # 2. 紅燈區 (賣出訊號)
            elif s >= sell_threshold:
                if mode != 'selling' and current_pos > 0.0:
                    mode = 'selling'
                    batch_count_done = 0
                    last_trade_idx = i - sell_interval - 1
            
            # 3. 綠燈/中間區
            else:
                if mode == 'buying': # 脫離藍燈 -> 一次補滿
                    current_pos = 1.0
                    mode = 'neutral'
                elif mode == 'selling': # 脫離紅燈 -> 一次清空
                    current_pos = 0.0
                    mode = 'neutral'
            
            # --- 執行分批動作 ---
            if mode == 'buying':
                if current_pos >= 1.0:
                    current_pos = 1.0
                    mode = 'neutral'
                else:
                    if (i - last_trade_idx) >= buy_interval:
                        step_size = 1.0 / buy_batches
                        current_pos += step_size
                        if current_pos > 1.0: current_pos = 1.0
                        last_trade_idx = i
                        batch_count_done += 1
                        if batch_count_done >= buy_batches:
                            current_pos = 1.0
                            mode = 'neutral'

            elif mode == 'selling':
                if current_pos <= 0.0:
                    current_pos = 0.0
                    mode = 'neutral'
                else:
                    if (i - last_trade_idx) >= sell_interval:
                        step_size = 1.0 / sell_batches
                        current_pos -= step_size
                        if current_pos < 0.0: current_pos = 0.0
                        last_trade_idx = i
                        batch_count_done += 1
                        if batch_count_done >= sell_batches:
                            current_pos = 0.0
                            mode = 'neutral'
            
            pos_series.append(current_pos)
            
        df["Position"] = pos_series
        
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
        with r1[0]: st.markdown(kpi("期末總資產", df["Equity_Strategy"].iloc[-1], df["Equity_Benchmark"].iloc[-1], False), unsafe_allow_html=True)
        with r1[1]: st.markdown(kpi("年化報酬 (CAGR)", cagr_s, cagr_b), unsafe_allow_html=True)
        with r1[2]: st.markdown(kpi("最大回撤", mdd_s, mdd_b), unsafe_allow_html=True)
        with r1[3]: st.markdown(kpi("夏普值", sharpe_s, sharpe_b, False), unsafe_allow_html=True)

        st.markdown("---")

        # 圖表
        tab1, tab2 = st.tabs(["🚦 買賣點位與燈號", "💰 資金與持倉"])

        with tab1:
            pos_diff = df["Position"].diff().fillna(0)
            buys = df[pos_diff > 0.01]
            sells = df[pos_diff < -0.01]

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3],
                                subplot_titles=(f"{ticker} 股價與分批點位", "景氣對策信號"))

            fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="股價", line=dict(color="#333", width=1)), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=buys.index, y=buys["Close"], mode="markers", name="買進",
                marker=dict(symbol="triangle-up", color="#0044FF", size=8, line=dict(width=1, color="white")),
                text=pos_diff[pos_diff>0].apply(lambda x: f"加碼 {x:.0%}")
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=sells.index, y=sells["Close"], mode="markers", name="賣出",
                marker=dict(symbol="triangle-down", color="#FF0044", size=8, line=dict(width=1, color="white")),
                text=pos_diff[pos_diff<0].apply(lambda x: f"減碼 {abs(x):.0%}")
            ), row=1, col=1)

            fig.add_trace(go.Scatter(x=df.index, y=df["Score_Signal"], name="分數", line=dict(color="#555", width=2)), row=2, col=1)
            
            bands = [(9, 16, "藍", "#2E86C1"), (17, 22, "黃藍", "#76D7C4"), (23, 31, "綠", "#28B463"), (32, 37, "黃紅", "#F1C40F"), (38, 55, "紅", "#E74C3C")]
            for y0, y1, txt, color in bands:
                fig.add_hrect(y0=y0, y1=y1, fillcolor=color, opacity=0.2, layer="below", row=2, col=1)

            fig.add_hline(y=buy_threshold, line_dash="dash", line_color="blue", row=2, col=1)
            fig.add_hline(y=sell_threshold, line_dash="dash", line_color="red", row=2, col=1)

            fig.update_layout(height=600, template="plotly_white", hovermode="x unified", showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="策略資產", line=dict(color="#00C853", width=2)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name="買進持有", line=dict(color="#B0BEC5", width=2, dash='dot')))
            
            # 持倉副圖
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Position"]*df["Equity_Strategy"].max(), name="持倉水位(示意)", 
                                        line=dict(width=0), fill='tozeroy', fillcolor='rgba(0,0,255,0.1)', yaxis="y2"))
            
            fig_eq.update_layout(height=450, template="plotly_white", hovermode="x unified", 
                                 title="資產成長與持倉變化",
                                 yaxis=dict(title="資產"),
                                 yaxis2=dict(title="持倉比例", overlaying="y", side="right", range=[0, 1.2], showgrid=False))
            st.plotly_chart(fig_eq, use_container_width=True)

        # 交易列表
        st.markdown("### 📋 資金變動明細")
        changes = df[df["Position"].diff().abs() > 0.001].copy()
        changes["動作"] = changes["Position"].diff().apply(lambda x: "買進/加碼" if x>0 else "賣出/減碼")
        changes["變動幅度"] = changes["Position"].diff().abs()
        changes["目前持倉"] = changes["Position"]
        
        if not changes.empty:
            df_log = changes[["Close", "動作", "變動幅度", "目前持倉", "Score_Signal"]]
            df_log.columns = ["成交價", "動作", "加減碼比例", "持倉水位", "當時燈號分"]
            st.dataframe(df_log.style.format({"成交價":"{:.2f}", "加減碼比例":"{:.1%}", "持倉水位":"{:.1%}", "當時燈號分":"{:.0f}"}).background_gradient(cmap="Blues", subset=["持倉水位"]), use_container_width=True)
        else:
            st.info("區間內無交易動作")
