###############################################################
# app.py — 單一標的 SMA 極端乖離戰情室 (雙軸合一版)
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
    page_title="Hamr Lab | SMA 極端乖離戰情室",
    layout="wide",
)

# ===============================================================
# Sidebar: 僅保留導覽功能
# ===============================================================
with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("提示：此版本將價格與乖離率合併顯示，左軸為價格，右軸為乖離率。")

# ===============================================================
# 主頁面標題
# ===============================================================
st.title("📊 SMA 乖離率深度分析儀 (雙軸疊圖版)")
st.caption("透過雙 Y 軸疊圖，直觀對照股價走勢與其偏離均線的程度。")

# ===============================================================
# 區塊 1: 參數設定 (放在主頁面)
# ===============================================================
with st.container(border=True):
    st.subheader("🛠️ 策略參數設定")
    
    # 第一排：標的與日期
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        ticker_input = st.text_input("輸入標的代號 (例如: 2330.TW, NVDA, QQQ)", value="2330.TW").upper()
    with c2:
        # 預設拉長到 10 年，看極端值比較有感
        start_date = st.date_input("開始日期", datetime(2013, 1, 1))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    # 第二排：技術參數與警戒值
    c4, c5, c6 = st.columns(3)
    with c4:
        sma_window = st.number_input("SMA 均線週期", min_value=10, max_value=500, value=200, step=10)
    with c5:
        overbought_pct = st.number_input("高位警戒線 (%) (右軸)", value=40)
    with c6:
        oversold_pct = st.number_input("低位警戒線 (%) (右軸)", value=-20)

    submitted = st.button("🚀 執行量化分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 資料處理與繪圖
# ===============================================================
if submitted or ticker_input:
    with st.spinner(f"正在抓取 {ticker_input} 資料並製作疊圖..."):
        # 抓取資料
        df_raw = yf.download(ticker_input, start=start_date, end=end_date, progress=False)
        
        if df_raw.empty:
            st.error("❌ 找不到該標的資料，請確認代號是否正確。")
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

            # --- 繪圖區 (改用單一圖表雙Y軸) ---
            # specs 定義這是一個有副座標軸的圖
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # 1. 繪製主軸資料 (左軸: secondary_y=False)
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Price'], 
                name="收盤價 (左軸)", 
                line=dict(color='rgba(100, 100, 100, 0.5)', width=1.5)
            ), secondary_y=False)
            
            fig.add_trace(go.Scatter(
                x=df.index, y=df['SMA'], 
                name=f"{sma_window} SMA (左軸)", 
                line=dict(color='#ff7f0e', width=2)
            ), secondary_y=False)

            # 2. 繪製副軸資料 (右軸: secondary_y=True)
            # 乖離率改用虛線，避免遮擋太多價格線
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Gap'], 
                name="乖離率% (右軸)", 
                line=dict(color='#1f77b4', width=1.5, dash='dot'),
                opacity=0.8
            ), secondary_y=True)
            
            # 加入警戒線 (畫在右軸)
            fig.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, secondary_y=True)
            fig.add_hline(y=overbought_pct/100, line_dash="dot", line_color="#d62728", 
                          annotation_text=f"過熱 {overbought_pct}%", annotation_position="top left", secondary_y=True)
            fig.add_hline(y=oversold_pct/100, line_dash="dot", line_color="#2ca02c", 
                          annotation_text=f"恐慌 {oversold_pct}%", annotation_position="bottom left", secondary_y=True)

            # 佈局美化
            fig.update_layout(
                title_text=f"📈 {ticker_input} 價格走勢與 SMA 乖離率疊圖",
                height=650, # 合併後高度可以稍微降低
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(t=80)
            )
            
            # 設定座標軸
            # 左軸 (主軸)
            fig.update_yaxes(title_text="股價 (Price)", secondary_y=False, showgrid=True)
            # 右軸 (副軸) - 不顯示網格以免混亂
            fig.update_yaxes(title_text="乖離率 (Gap%)", tickformat=".1%", secondary_y=True, showgrid=False, zeroline=False)

            st.plotly_chart(fig, use_container_width=True)

            # --- 統計資訊區 ---
            st.subheader("📊 策略快照")
            m1, m2, m3, m4 = st.columns(4)
            
            current_gap = df['Gap'].iloc[-1]

            m1.metric("當前價格", f"{df['Price'].iloc[-1]:.2f}")
            m2.metric("當前乖離率", f"{current_gap:.2%}")
            m3.metric("歷史最大乖離", f"{df['Gap'].max():.2%}")
            m4.metric("歷史最小乖離", f"{df['Gap'].min():.2%}")

            # 提示區
            if current_gap >= overbought_pct/100:
                st.warning(f"⚠️ 警告：當前乖離率已進入 {overbought_pct}% 高位警戒區，請留意過熱回檔風險。")
            elif current_gap <= oversold_pct/100:
                st.success(f"✅ 提示：當前乖離率已跌破 {oversold_pct}% 恐慌區，可能存在超跌反彈機會。")

else:
    st.info("👆 請輸入標的代號並點擊「執行量化分析」開始繪製圖表。")
