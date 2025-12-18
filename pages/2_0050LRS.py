import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 字型與頁面設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC"]

st.set_page_config(
    page_title="0050LRS+Bias 回測系統",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證守門員
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except:
    st.stop()

###############################################################
# ETF 名稱清單與工具函式
###############################################################

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}
WINDOW = 200
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1, df2 = load_csv(base_symbol), load_csv(lev_symbol)
    if df1.empty or df2.empty: return dt.date(2012, 1, 1), dt.date.today()
    return max(df1.index.min().date(), df2.index.min().date()), min(df1.index.max().date(), df2.index.max().date())

###############################################################
# UI 側邊欄設定
###############################################################

with st.sidebar:
    st.header("⚙️ 核心設定")
    base_label = st.selectbox("原型 ETF (訊號源)", list(BASE_ETFS.keys()))
    lev_label = st.selectbox("槓桿 ETF (交易標的)", list(LEV_ETFS.keys()))
    
    s_min, s_max = get_full_range_from_csv(BASE_ETFS[base_label], LEV_ETFS[lev_label])
    start = st.date_input("開始日期", max(s_min, s_max - dt.timedelta(days=5*365)))
    end = st.date_input("結束日期", s_max)
    capital = st.number_input("本金", 1000, 10_000_000, 100_000)

    st.divider()
    st.header("🎯 乖離率套利設定")
    enable_bias = st.toggle("開啟乖離率抄底/套利", value=True)
    bias_sell_pct = st.slider("高位套利賣出點 (%)", 10, 60, 40)
    bias_buy_pct = st.slider("低位抄底買進點 (%)", -50, -5, -20)

st.markdown("<h1>📊 0050LRS + 乖離套利進階回測</h1>", unsafe_allow_html=True)

###############################################################
# 回測邏輯
###############################################################

if st.button("啟動回測 🚀"):
    df_b = load_csv(BASE_ETFS[base_label])
    df_l = load_csv(LEV_ETFS[lev_label])
    
    if df_b.empty or df_l.empty:
        st.error("找不到資料 CSV"); st.stop()

    df = df_b.loc[start - dt.timedelta(days=365):end].copy()
    df.rename(columns={"Price": "Price_base"}, inplace=True)
    df = df.join(df_l["Price"].rename("Price_lev"), how="inner")
    
    # 計算均線與乖離率
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price_base"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[start:end]

    # 訊號與持倉邏輯 (包含 LRS 與 Bias)
    df["Signal"] = 0
    df["Signal_Note"] = ""
    current_pos = 0 # 0: 空手, 1: 持倉
    
    for i in range(1, len(df)):
        pb, ma, bias = df["Price_base"].iloc[i], df["MA_200"].iloc[i], df["Bias_200"].iloc[i]
        pb0, ma0 = df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]
        
        # 1. 判斷乖離率 (套利/抄底)
        if enable_bias:
            if bias > bias_sell_pct and current_pos == 1:
                df.iloc[i, df.columns.get_loc("Signal")] = -1
                df.iloc[i, df.columns.get_loc("Signal_Note")] = "Bias 套利賣出"
                current_pos = 0
                continue # 今日已賣，跳過 LRS 判斷
            elif bias < bias_buy_pct and current_pos == 0:
                df.iloc[i, df.columns.get_loc("Signal")] = 1
                df.iloc[i, df.columns.get_loc("Signal_Note")] = "Bias 抄底買進"
                current_pos = 1
                continue # 今日已買，跳過 LRS 判斷

        # 2. 判斷標準 LRS (趨勢)
        if pb > ma and pb0 <= ma0 and current_pos == 0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
            df.iloc[i, df.columns.get_loc("Signal_Note")] = "LRS 買進"
            current_pos = 1
        elif pb < ma and pb0 >= ma0 and current_pos == 1:
            df.iloc[i, df.columns.get_loc("Signal")] = -1
            df.iloc[i, df.columns.get_loc("Signal_Note")] = "LRS 賣出"
            current_pos = 0

    # 計算資產曲線
    pos = 0
    pos_history = []
    for s in df["Signal"]:
        if s == 1: pos = 1
        elif s == -1: pos = 0
        pos_history.append(pos)
    df["Position"] = pos_history
    
    equity = [1.0]
    for i in range(1, len(df)):
        r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1] if df["Position"].iloc[i-1] == 1 else 1.0
        equity.append(equity[-1] * r)
    df["Equity"] = equity

    ###############################################################
    # 圖表呈現 (修正後的 Plotly 語法)
    ###############################################################

    # A. 乖離率監控圖
    st.markdown("<h3>📊 200MA 乖離率監測</h3>", unsafe_allow_html=True)
    fig_bias = go.Figure()
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率", fill='tozeroy', 
                                 line=dict(color='rgba(100, 149, 237, 0.8)'), fillcolor='rgba(100, 149, 237, 0.1)'))
    if enable_bias:
        fig_bias.add_hline(y=bias_sell_pct, line_dash="dash", line_color="red", annotation_text="套利線")
        fig_bias.add_hline(y=bias_buy_pct, line_dash="dash", line_color="green", annotation_text="抄底線")
    
    # ✅ 修正語法：將 yaxis_suffix 移入 yaxis 字典中的 ticksuffix
    fig_bias.update_layout(height=350, template="plotly_white", 
                           yaxis=dict(ticksuffix="%", title="乖離率"),
                           margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_bias, use_container_width=True)

    # B. 價格與訊號標註圖
    st.markdown("<h3>🎯 策略訊號執行點</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="收盤價", line=dict(color="#FF8C00")))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200SMA", line=dict(color="silver", dash="dash")))

    # 買進/賣出點
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers+text", name="買進訊號", 
                                 text=buys["Signal_Note"], textposition="top center",
                                 marker=dict(symbol="triangle-up", size=12, color="green")))
    fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers+text", name="賣出訊號", 
                                 text=sells["Signal_Note"], textposition="bottom center",
                                 marker=dict(symbol="triangle-down", size=12, color="red")))
    
    fig_price.update_layout(height=450, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_price, use_container_width=True)

    # C. 績效彙整 KPI
    st.divider()
    mdd = 1 - (df["Equity"] / df["Equity"].cummax()).min()
    final_val = df["Equity"].iloc[-1] * capital
    st.metric("最終資產價值", f"{final_val:,.0f} 元", f"{(df['Equity'].iloc[-1]-1):.2%}")
    st.write(f"最大回撤 (MDD): {mdd:.2%}")
