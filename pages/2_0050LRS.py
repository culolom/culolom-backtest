import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面與 Sidebar 設定 ---
st.set_page_config(page_title="0050LRS 策略三向比較", page_icon="📈", layout="wide")

# 🔒 側邊欄導覽功能 (追加回到首頁)
with st.sidebar:
    st.markdown("### 🚀 導覽")
    st.page_link("Home.py", label="回到首頁", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# --- 2. 資料讀取與常數 ---
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

# --- 3. 主頁面參數設定 ---
st.markdown("<h1 style='text-align: center;'>📊 策略績效三向比較 (含乖離率監控)</h1>", unsafe_allow_html=True)

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
        # 預設區間參考圖片設定
        start_date = st.date_input("開始日期", dt.date(2020, 12, 18))
        end_date = st.date_input("結束日期", dt.date(2025, 12, 17))
    with col5:
        bias_high = st.slider("乖離率 高位套利點 (%)", 10, 60, 40)
    with col6:
        bias_low = st.slider("乖離率 低位抄底點 (%)", -50, -5, -20)

    btn_run = st.button("開始回測比較 🚀", use_container_width=True, type="primary")

# --- 4. 核心計算邏輯 ---
if btn_run:
    df_b = load_csv(BASE_ETFS[base_label])
    df_l = load_csv(LEV_ETFS[lev_label])
    
    if df_b.empty or df_l.empty:
        st.error("找不到資料檔案，請確認 data/*.csv 存在")
        st.stop()

    # 計算均線與乖離率 (需包含預熱期)
    df = df_b.loc[pd.to_datetime(start_date)-dt.timedelta(days=365):pd.to_datetime(end_date)].copy()
    df.rename(columns={"Price": "Price_base"}, inplace=True)
    df = df.join(df_l["Price"].rename("Price_lev"), how="inner")
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price_base"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_date):pd.to_datetime(end_date)]

    # 策略路徑計算
    pos_lrs = 0; pos_bias = 0
    h_lrs = []; h_bias = []

    for i in range(len(df)):
        pb = df["Price_base"].iloc[i]; ma = df["MA_200"].iloc[i]; bias = df["Bias_200"].iloc[i]
        
        # LRS 邏輯
        pos_lrs = 1 if pb > ma else 0
        h_lrs.append(pos_lrs)

        # LRS + Bias 邏輯
        if bias > bias_high: pos_bias = 0 # 高位賣
        elif bias < bias_low: pos_bias = 1 # 低位買
        else: pos_bias = 1 if pb > ma else 0 # 趨勢
        h_bias.append(pos_bias)

    df["Pos_LRS"] = h_lrs; df["Pos_Bias"] = h_bias
    ret_lev = df["Price_lev"].pct_change().fillna(0)
    
    # 權益曲線計算
    df["Eq_BH"] = (1 + ret_lev).cumprod() # 買進持有
    
    eq_lrs = [1.0]; eq_bias = [1.0]
    for i in range(1, len(df)):
        r_lrs = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) if df["Pos_LRS"].iloc[i-1] == 1 else 1.0
        r_bias = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) if df["Pos_Bias"].iloc[i-1] == 1 else 1.0
        eq_lrs.append(eq_lrs[-1] * r_lrs)
        eq_bias.append(eq_bias[-1] * r_bias)
    df["Eq_LRS"] = eq_lrs; df["Eq_Bias"] = eq_bias

    # --- 5. 追加圖表：乖離率與價格對照 (復刻 image_b1348a.png) ---
    st.divider()
    st.subheader("🎯 歷史乖離率與價格對照 (雙軸)")
    
    fig_dual = go.Figure()
    # 左軸：乖離率藍色填充區域
    fig_dual.add_trace(go.Scatter(
        x=df.index, y=df["Bias_200"], name="乖離率 (%)",
        fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)',
        line=dict(color='rgba(100, 149, 237, 0.8)', width=1.5), yaxis="y1"
    ))
    # 右軸：收盤價橘色線
    fig_dual.add_trace(go.Scatter(
        x=df.index, y=df["Price_base"], name=f"{base_label} 收盤價",
        line=dict(color='#FF8C00', width=2), yaxis="y2"
    ))
    # 右軸：200SMA 灰色虛線
    fig_dual.add_trace(go.Scatter(
        x=df.index, y=df["MA_200"], name="200SMA",
        line=dict(color='silver', width=1.5, dash='dash'), yaxis="y2"
    ))

    fig_dual.update_layout(
        height=500, template="plotly_white", hovermode="x unified",
        yaxis=dict(title="乖離率 %", ticksuffix="%", side="left", showgrid=True),
        yaxis2=dict(title="價格 (元)", side="right", overlaying="y", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_dual, use_container_width=True)

    # --- 6. 三策略資金曲線比較 (復刻 image_b13028.png) ---
    st.divider()
    st.subheader("💰 三策略累積報酬率比較 (%)")
    
    fig_perf = go.Figure()
    fig_perf.add_trace(go.Scatter(x=df.index, y=(df["Eq_BH"]-1), name="買入持有", line=dict(color="silver", width=1.5)))
    fig_perf.add_trace(go.Scatter(x=df.index, y=(df["Eq_LRS"]-1), name="標準 LRS", line=dict(color="#C084FC", width=2, dash="dash")))
    fig_perf.add_trace(go.Scatter(x=df.index, y=(df["Eq_Bias"]-1), name="LRS + 乖離套利", line=dict(color="#7C3AED", width=3)))

    fig_perf.update_layout(
        height=500, template="plotly_white", yaxis=dict(tickformat=".1%", title="累積報酬率"),
        hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_perf, use_container_width=True)

    # --- 7. 績效彙整表 ---
    def get_mdd(eq): return (1 - eq / eq.cummax()).max()
    kpi = {
        "策略名稱": ["買進持有", "標準 LRS", "LRS + 乖離套利"],
        "期末資產": [f"{df['Eq_BH'].iloc[-1]*capital:,.0f}", f"{df['Eq_LRS'].iloc[-1]*capital:,.0f}", f"{df['Eq_Bias'].iloc[-1]*capital:,.0f}"],
        "總報酬率": [f"{(df['Eq_BH'].iloc[-1]-1):.2%}", f"{(df['Eq_LRS'].iloc[-1]-1):.2%}", f"{(df['Eq_Bias'].iloc[-1]-1):.2%}"],
        "最大回撤 (MDD)": [f"{get_mdd(df['Eq_BH']):.2%}", f"{get_mdd(df['Eq_LRS']):.2%}", f"{get_mdd(df['Eq_Bias']):.2%}"]
    }
    st.table(pd.DataFrame(kpi))
