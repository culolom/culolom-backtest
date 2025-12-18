###############################################################
# app.py — SMA 乖離率戰情室 (雙線對照加強版)
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
    page_title="Hamr Lab | 乖離率深度分析儀",
    layout="wide",
)

# ===============================================================
# Sidebar: 僅保留導覽功能
# ===============================================================
with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("💡 視覺說明：\n- 橘色粗線：收盤價\n- 灰色虛線：SMA 均線\n- 藍色區域：乖離率")

# ===============================================================
# 主頁面標題
# ===============================================================
st.title("📊 SMA 乖離率深度分析儀")
st.caption("同步觀測「股價」、「均線」與「乖離程度」的連動關係。")

# ===============================================================
# 區塊 1: 參數設定
# ===============================================================
with st.container(border=True):
    st.subheader("🛠️ 策略參數設定")
    
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        ticker_input = st.text_input("輸入標的代號 (例如: 2330.TW, NVDA)", value="2330.TW").upper()
    with c2:
        start_date = st.date_input("開始日期", datetime(2018, 1, 1))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    c4, c5, c6 = st.columns(3)
    with c4:
        sma_window = st.number_input("SMA 均線週期", value=200)
    with c5:
        overbought_pct = st.number_input("高位警戒 (%) (左軸)", value=40)
    with c6:
        oversold_pct = st.number_input("低位警戒 (%) (左軸)", value=-20)

    submitted = st.button("🚀 執行量化分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 繪圖邏輯
# ===============================================================
if submitted or ticker_input:
    with st.spinner(f"正在分析 {ticker_input}..."):
        df_raw = yf.download(ticker_input, start=start_date, end=end_date, progress=False)
        
        if df_raw.empty:
            st.error("❌ 找不到該標的資料，請確認代號。")
        else:
            # 數據處理
            df = df_raw.copy()
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs('Close', axis=1, level=0)
            else:
                df = df['Close']
            
            df = pd.DataFrame(df)
            df.columns = ['Price']
            
            # 計算指標
            df['SMA'] = df['Price'].rolling(window=sma_window).mean()
            df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
            df = df.dropna()

            # 建立雙 Y 軸圖表
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # --- 1. 乖離率 (左軸 secondary_y=False) ---
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Gap'], 
                name="乖離率 (左軸)", 
                line=dict(color='royalblue', width=1),
                fill='tozeroy', 
                fillcolor='rgba(65, 105, 225, 0.12)' 
            ), secondary_y=False)

            # --- 2. SMA 參考線 (右軸 secondary_y=True) ---
            # 使用灰色虛線，作為背景基準
            fig.add_trace(go.Scatter(
                x=df.index, y=df['SMA'], 
                name=f"{sma_window} SMA (右軸)", 
                line=dict(color='#7f8c8d', width=1.5, dash='dash'),
                opacity=0.7
            ), secondary_y=True)

            # --- 3. 收盤價 (右軸 secondary_y=True) ---
            # 橘色粗實線主視覺
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Price'], 
                name="收盤價 (右軸)", 
                line=dict(color='#ff7f0e', width=4) 
            ), secondary_y=True)
            
            # --- 4. 警戒線設定 (左軸) ---
            fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, secondary_y=False)
            fig.add_hline(y=overbought_pct/100, line_dash="dot", line_color="#e74c3c", 
                          annotation_text="過熱區", annotation_position="top left", secondary_y=False)
            fig.add_hline(y=oversold_pct/100, line_dash="dot", line_color="#27ae60", 
                          annotation_text="恐慌區", annotation_position="bottom left", secondary_y=False)

            # 佈局美化
            fig.update_layout(
                height=700,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor='white',
                margin=dict(t=100)
            )
            
            # 座標軸標題設定
            fig.update_yaxes(title_text="<b>乖離率 % (左)</b>", tickformat=".0%", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
            fig.update_yaxes(title_text="<b>價格 (右)</b>", secondary_y=True, showgrid=False)

            st.plotly_chart(fig, use_container_width=True)

            # --- 統計資訊區 ---
            st.subheader("📊 數據摘要")
            m1, m2, m3 = st.columns(3)
            curr_gap = df['Gap'].iloc[-1]
            m1.metric("目前股價", f"{df['Price'].iloc[-1]:.2f}")
            m2.metric("目前乖離率", f"{curr_gap:.2%}")
            m3.metric(f"{sma_window} SMA 數值", f"{df['SMA'].iloc[-1]:.2f}")

            if curr_gap >= overbought_pct/100:
                st.error(f"🚨 高位警戒：當前乖離 ({curr_gap:.1%}) 已進入過熱區！橘色線已顯著高於灰色均線。")
            elif curr_gap <= oversold_pct/100:
                st.success(f"💎 低位機會：當前乖離 ({curr_gap:.1%}) 已進入恐慌區！橘色線已顯著低於灰色均線。")

else:
    st.info("👆 請輸入標的代號並點擊「執行量化分析」。")
