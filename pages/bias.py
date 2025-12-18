###############################################################
# app.py — SMA 乖離率戰情室 (含直方圖與勝率回測)
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

# ===============================================================
# Sidebar: 僅保留導覽功能
# ===============================================================
with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.markdown("### 💡 視覺與邏輯說明")
    st.info("""
    - **橘色粗線**：收盤價 (主視覺)
    - **灰色虛線**：SMA 均線 (基準)
    - **藍色區域**：乖離率 %
    - **回測邏輯**：計算觸發極端值後，5 個交易日後的漲跌機率。
    """)

st.title("📊 SMA 乖離率深度量化戰情室")
st.caption("結合歷史分佈與勝率回測，用科學數據定義買賣點。")

# ===============================================================
# 區塊 1: 參數設定
# ===============================================================
with st.container(border=True):
    st.subheader("🛠️ 策略參數與回測設定")
    
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        ticker_input = st.text_input("輸入標的代號 (例如: 2330.TW, NVDA, TQQQ)", value="2330.TW").upper()
    with c2:
        # 預設看 10 年，樣本數才夠
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
# 區塊 2: 資料處理
# ===============================================================
if submitted or ticker_input:
    with st.spinner(f"正在抓取 {ticker_input} 歷史數據並執行回測..."):
        df_raw = yf.download(ticker_input, start=start_date, end=end_date, progress=False)
        
        if df_raw.empty:
            st.error("❌ 找不到該標的資料。")
        else:
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
            
            # --- 回測計算 (5日後表現) ---
            df['Price_Next_5D'] = df['Price'].shift(-5)
            df['Return_5D'] = (df['Price_Next_5D'] - df['Price']) / df['Price']
            
            df = df.dropna(subset=['SMA', 'Gap']) # 排除掉均線還沒算出來的天數

            # 1. 主圖表：雙軸疊圖
            fig_main = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 乖離率 (左軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Gap'], name="乖離率 (左軸)", 
                line=dict(color='royalblue', width=1),
                fill='tozeroy', fillcolor='rgba(65, 105, 225, 0.12)'
            ), secondary_y=False)

            # SMA (右軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['SMA'], name=f"{sma_window} SMA (右軸)", 
                line=dict(color='#7f8c8d', width=1.5, dash='dash'), opacity=0.6
            ), secondary_y=True)

            # 價格 (右軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Price'], name="收盤價 (右軸)", 
                line=dict(color='#ff7f0e', width=4) 
            ), secondary_y=True)

            # 警戒線
            fig_main.add_hline(y=0, line_dash="solid", line_color="gray", opacity=0.3, secondary_y=False)
            fig_main.add_hline(y=overbought_pct/100, line_dash="dot", line_color="#e74c3c", annotation_text="過熱區", secondary_y=False)
            fig_main.add_hline(y=oversold_pct/100, line_dash="dot", line_color="#27ae60", annotation_text="恐慌區", secondary_y=False)

            fig_main.update_layout(height=600, hovermode="x unified", plot_bgcolor='white', margin=dict(t=50))
            fig_main.update_yaxes(title_text="乖離率 %", tickformat=".0%", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
            fig_main.update_yaxes(title_text="價格", secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_main, use_container_width=True)

            # ===============================================================
            # 區塊 3: 歷史分佈圖 (Histogram) 與 回測統計
            # ===============================================================
            st.divider()
            col_left, col_right = st.columns([1, 1])

            with col_left:
                st.subheader("📊 乖離率歷史分佈圖")
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=df['Gap'], nbinsx=100, name="乖離率分佈",
                    marker_color='royalblue', opacity=0.7
                ))
                # 加入警戒垂直線
                fig_hist.add_vline(x=overbought_pct/100, line_dash="dash", line_color="#e74c3c")
                fig_hist.add_vline(x=oversold_pct/100, line_dash="dash", line_color="#27ae60")
                
                fig_hist.update_layout(
                    xaxis_title="乖離率 %", yaxis_title="出現天數",
                    xaxis_tickformat=".0%", bargap=0.05, height=400, plot_bgcolor='white'
                )
                st.plotly_chart(fig_hist, use_container_width=True)
                
                # 計算機率
                total_days = len(df)
                over_days = len(df[df['Gap'] >= overbought_pct/100])
                under_days = len(df[df['Gap'] <= oversold_pct/100])
                st.write(f"💡 歷史統計：在過去 {total_days} 個交易日中，乖離率高於 {overbought_pct}% 的天數僅佔 **{over_days/total_days:.2%}**；低於 {oversold_pct}% 的天數佔 **{under_days/total_days:.2%}**。")

            with col_right:
                st.subheader("🎯 極端訊號策略回測 (5日表現)")
                
                # 過熱訊號回測: Gap > Threshold -> 期待下跌 (Return < 0)
                over_trigger = df[df['Gap'] >= overbought_pct/100].copy()
                if not over_trigger.empty:
                    win_rate_over = len(over_trigger[over_trigger['Return_5D'] < 0]) / len(over_trigger.dropna(subset=['Return_5D']))
                    avg_ret_over = over_trigger['Return_5D'].mean()
                else:
                    win_rate_over, avg_ret_over = 0, 0

                # 恐慌訊號回測: Gap < Threshold -> 期待上漲 (Return > 0)
                under_trigger = df[df['Gap'] <= oversold_pct/100].copy()
                if not under_trigger.empty:
                    win_rate_under = len(under_trigger[under_trigger['Return_5D'] > 0]) / len(under_trigger.dropna(subset=['Return_5D']))
                    avg_ret_under = under_trigger['Return_5D'].mean()
                else:
                    win_rate_under, avg_ret_under = 0, 0

                # 顯示回測卡片
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.metric("過熱訊號 (期待下跌) 勝率", f"{win_rate_over:.1%}", help="乖離率超過高位警戒後，5天後股價確實下跌的機率")
                    st.caption(f"平均 5 日報酬率: {avg_ret_over:.2%}")
                with rc2:
                    st.metric("恐慌訊號 (期待上漲) 勝率", f"{win_rate_under:.1%}", help="乖離率低於低位警戒後，5天後股價確實上漲的機率")
                    st.caption(f"平均 5 日報酬率: {avg_ret_under:.2%}")

                st.info("💡 **解讀提示**：若勝率高於 60%，代表該極端值是具備高度參考價值的反轉訊號。")

            # --- 數據摘要卡片 ---
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            curr_gap = df['Gap'].iloc[-1]
            m1.metric("目前價格", f"{df['Price'].iloc[-1]:.2f}")
            m2.metric("目前乖離率", f"{curr_gap:.2%}")
            m3.metric("歷史最大乖離", f"{df['Gap'].max():.2%}")
            m4.metric("歷史最小乖離", f"{df['Gap'].min():.2%}")

else:
    st.info("👆 請輸入代號並點擊「開始量化回測與分析」。")
