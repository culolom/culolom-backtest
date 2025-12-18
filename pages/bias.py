###############################################################
# app.py — SMA 乖離率戰情室 (線條寬度優化版)
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 頁面設定
st.set_page_config(
    page_title="Hamr Lab | 極端乖離回測戰情室",
    layout="wide",
)

with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("💡 視覺調整：已將收盤價橘線調細，並優化層次感。")

st.title("📊 SMA 乖離率深度量化戰情室")

# ===============================================================
# 區塊 1: 參數設定
# ===============================================================
with st.container(border=True):
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        ticker_input = st.text_input("輸入標的代號 (例如: 2330.TW, NVDA)", value="2330.TW").upper()
    with c2:
        start_date = st.date_input("開始日期", datetime.now() - timedelta(days=365*10))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    c4, c5, c6 = st.columns(3)
    with c4:
        sma_window = st.number_input("SMA 均線週期", value=200)
    with c5:
        overbought_pct = st.number_input("高位警戒 (%)", value=40)
    with c6:
        oversold_pct = st.number_input("低位警戒 (%)", value=-20)

    submitted = st.button("🚀 開始量化回測與分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 繪圖與回測邏輯
# ===============================================================
if submitted or ticker_input:
    df_raw = yf.download(ticker_input, start=start_date, end=end_date, progress=False)
    
    if not df_raw.empty:
        df = df_raw.copy()
        df = df.xs('Close', axis=1, level=0) if isinstance(df.columns, pd.MultiIndex) else df['Close']
        df = pd.DataFrame(df); df.columns = ['Price']
        
        # 指標與回測數據計算
        df['SMA'] = df['Price'].rolling(window=sma_window).mean()
        df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
        df['Return_5D'] = (df['Price'].shift(-5) - df['Price']) / df['Price']
        df = df.dropna(subset=['SMA', 'Gap'])

        # --- 主圖表：雙軸疊圖 ---
        fig_main = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 乖離率 (左軸)
        fig_main.add_trace(go.Scatter(
            x=df.index, y=df['Gap'], name="乖離率 (左軸)", 
            line=dict(color='royalblue', width=1),
            fill='tozeroy', fillcolor='rgba(65, 105, 225, 0.1)' # 降低填充透明度
        ), secondary_y=False)

        # SMA (右軸)
        fig_main.add_trace(go.Scatter(
            x=df.index, y=df['SMA'], name=f"{sma_window} SMA (右軸)", 
            line=dict(color='#7f8c8d', width=1.2, dash='dash'), opacity=0.5
        ), secondary_y=True)

        # 價格 (右軸) - [關鍵修改：調細線條 width=2.5]
        fig_main.add_trace(go.Scatter(
            x=df.index, y=df['Price'], name="收盤價 (右軸)", 
            line=dict(color='#ff7f0e', width=2.5) 
        ), secondary_y=True)

        # 佈局美化
        fig_main.update_layout(
            height=600, hovermode="x unified", plot_bgcolor='white',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig_main.update_yaxes(title_text="乖離率 %", tickformat=".0%", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
        fig_main.update_yaxes(title_text="價格", secondary_y=True, showgrid=False)
        
        st.plotly_chart(fig_main, use_container_width=True)

        # --- 歷史分佈圖與回測統計 ---
        st.divider()
        col_l, col_r = st.columns(2)

        with col_l:
            st.subheader("📊 乖離率歷史分佈圖")
            fig_hist = go.Figure(go.Histogram(x=df['Gap'], nbinsx=100, marker_color='royalblue', opacity=0.6))
            fig_hist.add_vline(x=overbought_pct/100, line_dash="dash", line_color="#e74c3c")
            fig_hist.add_vline(x=oversold_pct/100, line_dash="dash", line_color="#27ae60")
            fig_hist.update_layout(xaxis_tickformat=".0%", height=350, plot_bgcolor='white', bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_r:
            st.subheader("🎯 極端訊號 5 日回測勝率")
            # 過熱統計
            ov_t = df[df['Gap'] >= overbought_pct/100].dropna(subset=['Return_5D'])
            wr_ov = len(ov_t[ov_t['Return_5D'] < 0]) / len(ov_t) if not ov_t.empty else 0
            # 恐慌統計
            un_t = df[df['Gap'] <= oversold_pct/100].dropna(subset=['Return_5D'])
            wr_un = len(un_t[un_t['Return_5D'] > 0]) / len(un_t) if not un_t.empty else 0

            c_rc1, c_rc2 = st.columns(2)
            c_rc1.metric("過熱期待下跌勝率", f"{wr_ov:.1%}")
            c_rc2.metric("恐慌期待上漲勝率", f"{wr_un:.1%}")
            st.write(f"💡 樣本數：過熱觸發 {len(ov_t)} 次 / 恐慌觸發 {len(un_t)} 次")

        # --- 數據摘要 ---
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("目前價格", f"{df['Price'].iloc[-1]:.2f}")
        m2.metric("目前乖離率", f"{df['Gap'].iloc[-1]:.2%}")
        m3.metric("歷史最大/小乖離", f"{df['Gap'].max():.1%} / {df['Gap'].min():.1%}")

else:
    st.info("👆 請輸入代號並點擊「開始量化回測與分析」。")
