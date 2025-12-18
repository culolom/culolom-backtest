import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 頁面設定 ---
st.set_page_config(page_title="0050LRS 策略三向比較", page_icon="📈", layout="wide")

# --- 資料讀取與常數 ---
BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {"00631L 元大台灣50正2": "00631L.TW", "00675L 富邦台灣加權正2": "00675L.TW"}
DATA_DIR = Path("data")
WINDOW = 200

def load_csv(symbol: str):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# --- 1. 主頁面參數設定 (不放在 Sidebar) ---
st.markdown("<h1 style='text-align: center;'>📊 策略績效三向比較</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>比較：買進持有 vs 標準 LRS vs LRS+乖離率套利</p>", unsafe_allow_html=True)

with st.container(border=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        base_label = st.selectbox("原型 ETF (訊號源)", list(BASE_ETFS.keys()), index=0)
    with col2:
        lev_label = st.selectbox("槓桿 ETF (交易標的)", list(LEV_ETFS.keys()), index=0)
    with col3:
        capital = st.number_input("本金 (元)", 1000, 10_000_000, 100000)

    col4, col5, col6 = st.columns(3)
    with col4:
        start_date = st.date_input("開始日期", dt.date(2020, 12, 18))
        end_date = st.date_input("結束日期", dt.date(2025, 12, 17))
    with col5:
        bias_high = st.slider("乖離率 高位套利點 (%)", 10, 60, 40)
    with col6:
        bias_low = st.slider("乖離率 低位抄底點 (%)", -50, -5, -20)

    btn_run = st.button("開始回測比較 🚀", use_container_width=True, type="primary")

# --- 2. 核心計算邏輯 ---
if btn_run:
    df_b = load_csv(BASE_ETFS[base_label])
    df_l = load_csv(LEV_ETFS[lev_label])
    
    if df_b.empty or df_l.empty:
        st.error("找不到資料檔案，請確認 data/*.csv 存在")
        st.stop()

    # 合併資料並計算指標
    df = df_b.loc[pd.to_datetime(start_date)-dt.timedelta(days=365):pd.to_datetime(end_date)].copy()
    df.rename(columns={"Price": "Price_base"}, inplace=True)
    df = df.join(df_l["Price"].rename("Price_lev"), how="inner")
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price_base"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_date):pd.to_datetime(end_date)]

    # --- 策略模擬迴圈 ---
    pos_lrs = 0
    pos_bias = 0
    hist_lrs = []
    hist_bias = []

    for i in range(len(df)):
        pb = df["Price_base"].iloc[i]
        ma = df["MA_200"].iloc[i]
        bias = df["Bias_200"].iloc[i]
        
        # A. 標準 LRS 邏輯
        pos_lrs = 1 if pb > ma else 0
        hist_lrs.append(pos_lrs)

        # B. LRS + 乖離率套利邏輯
        # 邏輯優先級：乖離極端值 > 均線判斷
        if bias > bias_high:
            pos_bias = 0  # 高位強制套利賣出
        elif bias < bias_low:
            pos_bias = 1  # 低位強制抄底買進
        else:
            pos_bias = 1 if pb > ma else 0 # 常態下遵循均線
        hist_bias.append(pos_bias)

    df["Pos_LRS"] = hist_lrs
    df["Pos_Bias"] = hist_bias

    # 計算權益曲線 (Equity Curves)
    # 策略都是「今天決定，明天開盤生效」，此處簡化為當日收盤同步
    ret_lev = df["Price_lev"].pct_change().fillna(0)
    
    # 1. 買進持有
    df["Eq_BH"] = (1 + ret_lev).cumprod()
    
    # 2. 標準 LRS
    eq_lrs = [1.0]
    for i in range(1, len(df)):
        r = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) if df["Pos_LRS"].iloc[i-1] == 1 else 1.0
        eq_lrs.append(eq_lrs[-1] * r)
    df["Eq_LRS"] = eq_lrs

    # 3. LRS + 乖離套利
    eq_bias = [1.0]
    for i in range(1, len(df)):
        r = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) if df["Pos_Bias"].iloc[i-1] == 1 else 1.0
        eq_bias.append(eq_bias[-1] * r)
    df["Eq_Bias"] = eq_bias

    # --- 3. 圖表呈現 ---
    st.divider()
    st.subheader("💰 三策略資金曲線比較 (%)")
    
    fig = go.Figure()
    # 買進持有 (灰色)
    fig.add_trace(go.Scatter(x=df.index, y=(df["Eq_BH"]-1), name="買入持有", line=dict(color="silver", width=1.5)))
    # 標準 LRS (淺紫色)
    fig.add_trace(go.Scatter(x=df.index, y=(df["Eq_LRS"]-1), name="標準 LRS", line=dict(color="#C084FC", width=2, dash="dash")))
    # LRS + 乖離套利 (深紫色)
    fig.add_trace(go.Scatter(x=df.index, y=(df["Eq_Bias"]-1), name="LRS + 乖離套利", line=dict(color="#7C3AED", width=3)))

    fig.update_layout(
        template="plotly_white",
        height=550,
        yaxis=dict(tickformat=".1%", title="累積報酬率"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 4. 績效結算表 ---
    def get_mdd(eq_series):
        return (1 - eq_series / eq_series.cummax()).max()

    kpi = {
        "策略名稱": ["買進持有", "標準 LRS", "LRS + 乖離套利"],
        "期末資產": [f"{df['Eq_BH'].iloc[-1]*capital:,.0f}", f"{df['Eq_LRS'].iloc[-1]*capital:,.0f}", f"{df['Eq_Bias'].iloc[-1]*capital:,.0f}"],
        "總報酬率": [f"{(df['Eq_BH'].iloc[-1]-1):.2%}", f"{(df['Eq_LRS'].iloc[-1]-1):.2%}", f"{(df['Eq_Bias'].iloc[-1]-1):.2%}"],
        "最大回撤 (MDD)": [f"{get_mdd(df['Eq_BH']):.2%}", f"{get_mdd(df['Eq_LRS']):.2%}", f"{get_mdd(df['Eq_Bias']):.2%}"]
    }
    st.table(pd.DataFrame(kpi))
