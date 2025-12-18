###############################################################
# app.py — SMA 乖離率戰情室 (視覺辨識優化版)
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# 1. 頁面設定
st.set_page_config(
    page_title="Hamr Lab | 視覺優化戰情室",
    layout="wide",
)

with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("視覺優化：區域填充代表乖離程度，實線代表均線。")

st.title("📊 SMA 乖離率深度分析儀")

# ===============================================================
# 區塊 1: 參數設定
# ===============================================================
with st.container(border=True):
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        ticker_input = st.text_input("輸入標的代號", value="2330.TW").upper()
    with c2:
        start_date = st.date_input("開始日期", datetime(2018, 1, 1))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    c4, c5, c6 = st.columns(3)
    with c4:
        sma_window = st.number_input("SMA 均線週期", value=200)
    with c5:
        overbought_pct = st.number_input("高位警戒 (%)", value=40)
    with c6:
        oversold_pct = st.number_input("低位警戒 (%)", value=-20)

    submitted = st.button("🚀 執行量化分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 繪圖邏輯
# ===============================================================
if submitted or ticker_input:
    df_raw = yf.download(ticker_input, start=start_date, end=end_date, progress=False)
    
    if not df_raw.empty:
        df = df_raw.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs('Close', axis=1, level=0)
        else:
            df = df['Close']
        
        df = pd.DataFrame(df)
        df.columns = ['Price']
        df['SMA'] = df['Price'].rolling(window=sma_window).mean()
        df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
        df = df.dropna()

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # --- 1. 背景：收盤價 (淺灰色，不干擾視覺) ---
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Price'], 
            name="收盤價", 
            line=dict(color='lightgrey', width=1),
            opacity=0.6
        ), secondary_y=False)
        
        # --- 2. 主角一：SMA 均線 (深色實線) ---
        fig.add_trace(go.Scatter(
            x=df.index, y=df['SMA'], 
            name=f"{sma_window} SMA", 
            line=dict(color='#2c3e50', width=2.5)
        ), secondary_y=False)

        # --- 3. 主角二：乖離率 (藍色區域填充) ---
        # 使用 fill='tozeroy' 讓乖離率呈現「面積感」
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Gap'], 
            name="乖離率 (右軸)", 
            line=dict(color='royalblue', width=1.5),
            fill='tozeroy', 
            fillcolor='rgba(65, 105, 225, 0.15)' 
        ), secondary_y=True)

        # --- 4. 警戒線與區域 ---
        # 零軸
        fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.5, secondary_y=True)
        
        # 高位警戒 (紅)
        fig.add_hline(y=overbought_pct/100, line_dash="dash", line_color="#e74c3c", 
                      annotation_text="過熱區", secondary_y=True)
        
        # 低位警戒 (綠)
        fig.add_hline(y=oversold_pct/100, line_dash="dash", line_color="#27ae60", 
                      annotation_text="恐慌區", secondary_y=True)

        # 佈局設定
        fig.update_layout(
            height=700,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor='white' # 改為白底讓顏色更跳
        )
        
        # 座標軸美化
        fig.update_yaxes(title_text="<b>股價</b>", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
        fig.update_yaxes(title_text="<b>乖離率 %</b>", tickformat=".0%", secondary_y=True, showgrid=False)

        st.plotly_chart(fig, use_container_width=True)

        # --- 數據摘要 ---
        c_m1, c_m2, c_m3 = st.columns(3)
        curr_gap = df['Gap'].iloc[-1]
        c_m1.metric("目前股價", f"{df['Price'].iloc[-1]:.2f}")
        c_m2.metric("目前乖離率", f"{curr_gap:.2%}", delta=f"{(curr_gap*100):.1f}%")
        
        # 狀態標籤
        if curr_gap >= overbought_pct/100:
            st.error(f"🚨 高位警戒：當前乖離 ({curr_gap:.1%}) 已進入超漲過熱區！")
        elif curr_gap <= oversold_pct/100:
            st.success(f"💎 低位機會：當前乖離 ({curr_gap:.1%}) 已進入超跌恐慌區！")

    else:
        st.error("查無資料，請檢查代號。")
