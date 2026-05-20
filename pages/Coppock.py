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
# 字型與 Streamlit 設定
###############################################################
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="正2 LRS+DCA 回測系統", page_icon="📈", layout="wide")

###############################################################
# 資料設定
###############################################################
BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

def get_full_range_from_csv(base_symbol, lev_symbol):
    df1, df2 = load_csv(base_symbol), load_csv(lev_symbol)
    if df1.empty or df2.empty: return dt.date(2012, 1, 1), dt.date.today()
    return max(df1.index.min().date(), df2.index.min().date()), min(df1.index.max().date(), df2.index.max().date())

###############################################################
# UI 介面
###############################################################
st.markdown("<h1>📊 正2 ETF 動態槓桿回測系統</h1>", unsafe_allow_html=True)
col1, col2 = st.columns(2)
with col1: base_symbol = BASE_ETFS[st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))]
with col2: lev_symbol = LEV_ETFS[st.selectbox("正2 ETF（實際交易標的）", list(LEV_ETFS.keys()))]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
c1, c2, c3, c4 = st.columns(4)
start = c1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)), min_value=s_min, max_value=s_max)
end = c2.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
capital = c3.number_input("投入本金", 1000, 5_000_000, 100_000, step=10_000)
sma_window = c4.number_input("均線週期", 10, 240, 200, step=10)

position_mode = st.radio("初始狀態", ["全倉正2 ETF", "空手起跑"], index=0)
enable_dca = st.toggle("啟用 DCA 定期定額 (跌破均線時)")
dca_interval = st.number_input("買進間隔(日)", 1, 60, 3, disabled=not enable_dca)
dca_pct = st.number_input("每次買進比例(%)", 1, 100, 10, step=5, disabled=not enable_dca)

###############################################################
# 核心運算
###############################################################
if st.button("開始回測 🚀"):
    df_base = load_csv(base_symbol).loc[start - dt.timedelta(days=365):end]
    df_lev = load_csv(lev_symbol).loc[start - dt.timedelta(days=365):end]
    df = pd.DataFrame(index=df_base.index).join(df_base["Price"].rename("Price_base")).join(df_lev["Price"].rename("Price_lev")).dropna()
    df["MA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start:end]

    pos, signals = [0.0] * len(df), [0] * len(df)
    current_pos = 1.0 if "全倉" in position_mode else 0.0
    can_buy = True if "全倉" in position_mode else False
    dca_cnt = 0

    for i in range(1, len(df)):
        p, m, p0, m0 = df["Price_base"].iloc[i], df["MA"].iloc[i], df["Price_base"].iloc[i-1], df["MA"].iloc[i-1]
        if p > m:
            if can_buy: current_pos = 1.0
            dca_cnt = 0
        else:
            can_buy = True
            if p0 > m0: 
                current_pos, signals[i] = 0.0, -1
            elif enable_dca and current_pos < 1.0:
                dca_cnt += 1
                if dca_cnt >= dca_interval:
                    current_pos = min(1.0, current_pos + (dca_pct/100))
                    signals[i], dca_cnt = 2, 0
        pos[i] = current_pos

    df["Position"], df["Signal"] = pos, signals
    
    # 資金曲線計算 (正2直接乘權重)
    equity = [1.0]
    for i in range(1, len(df)):
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + lev_ret * df["Position"].iloc[i-1]))
    
    df["Equity"] = equity
    df["BH_Lev"] = (1 + (df["Price_lev"].pct_change().fillna(0))).cumprod()

    # 圖表呈現
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity"], name="策略績效"))
    fig.add_trace(go.Scatter(x=df.index, y=df["BH_Lev"], name="正2 Buy&Hold", line=dict(dash='dot')))
    st.plotly_chart(fig, use_container_width=True)
    
    st.success(f"回測結束：最終累積淨值 {df['Equity'].iloc[-1]:.2f} 倍")
