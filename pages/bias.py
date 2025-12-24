###############################################################
# app.py — SMA 乖離率戰情室 (定投/抄底實戰版)
###############################################################

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# 1. 頁面設定
st.set_page_config(
    page_title="Hamr Lab | 乖離率戰情室 (實戰版)",
    layout="wide",
)

with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("💡 策略模式：專注於負向乖離。")
    st.markdown("""
    - **定投線 (-1σ)**: 綠色，價格回落至合理區間，維持紀律。
    - **抄底線 (-2σ)**: 紅色，極端恐慌時刻，考慮加大部位。
    """)

st.title("📊 SMA 乖離率戰情室 (定投/抄底實戰版)")

# ===============================================================
# 區塊 1: 參數設定與檔案讀取
# ===============================================================
with st.container(border=True):
    # --- 自動掃描 data 資料夾 ---
    data_dir = "data"
    csv_files = []
    selected_file = None 
    
    if os.path.exists(data_dir):
        # 讀取目錄下所有 csv 檔案
        csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        csv_files.sort()
    else:
        st.error(f"❌ 找不到 '{data_dir}' 資料夾，請確認目錄結構。")

    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    
    with c1:
        if csv_files:
            selected_file = st.selectbox("選擇本地標的 (從 data 資料夾)", csv_files, index=0)
            ticker_name = selected_file.replace(".csv", "")
        else:
            st.warning("⚠️ data 資料夾內沒有 CSV 檔案")
            ticker_name = "未知標的"
            
    with c2:
        start_date = st.date_input("開始日期", datetime.now() - timedelta(days=365*5))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    c4, c5 = st.columns([1, 2])
    with c4:
        sma_window = st.number_input("SMA 均線週期", value=200)
    with c5:
        st.write("") 

    submitted = st.button("🚀 讀取檔案並分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 繪圖與回測邏輯
# ===============================================================
if submitted and selected_file:
    file_path = os.path.join(data_dir, selected_file)
    
    try:
        # 讀取 CSV
        df_raw = pd.read_csv(file_path)
        
        # --- 資料清洗 ---
        if 'Date' in df_raw.columns:
            df_raw['Date'] = pd.to_datetime(df_raw['Date'])
            df_raw.set_index('Date', inplace=True)
        else:
            st.error("CSV 缺少 'Date' 欄位。")
            st.stop()
            
        # 篩選日期
        tz_start = pd.to_datetime(start_date)
        tz_end = pd.to_datetime(end_date)
        df = df_raw.sort_index().loc[tz_start:tz_end].copy()

        # 確保價格欄位
        if 'Close' not in df.columns:
            if 'Adj Close' in df.columns:
                df['Price'] = df['Adj Close']
            else:
                st.error("找不到 'Close' 欄位。")
                st.stop()
        else:
            df['Price'] = df['Close']
        
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
        df = df.dropna(subset=['Price'])

        if df.empty:
            st.warning("⚠️ 選定區間無數據。")
        else:
            # --- 指標計算 ---
            df['SMA'] = df['Price'].rolling(window=sma_window).mean()
            df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
            df['Return_5D'] = (df['Price'].shift(-5) - df['Price']) / df['Price']
            df = df.dropna(subset=['SMA', 'Gap'])

            # --- 統計數據 (只取需要的) ---
            gap_mean_all = df['Gap'].mean()
            gap_std_all = df['Gap'].std()
            
            # 定義：定投線 (-1σ), 抄底線 (-2σ)
            # 正乖離線均已移除
            sigma_neg_1 = gap_mean_all - (1 * gap_std_all) # 定投
            sigma_neg_2 = gap_mean_all - (2 * gap_std_all) # 抄底

            # --- 主圖表 ---
            fig_main = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 乖離率 (左軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Gap'], name="乖離率 (左軸)", 
                line=dict(color='royalblue', width=1),
                fill='tozeroy', fillcolor='rgba(65, 105, 225, 0.1)'
            ), secondary_y=False)

            # SMA (右軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['SMA'], name=f"{sma_window} SMA (右軸)", 
                line=dict(color='#7f8c8d', width=1.2, dash='dash'), opacity=0.5
            ), secondary_y=True)

            # 價格 (右軸)
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Price'], name="收盤價 (右軸)", 
                line=dict(color='#ff7f0e', width=2.5) 
            ), secondary_y=True)

            # --- [修改核心] 繪製定投線與抄底線 ---
            
            # 1. 定投線 (-1σ): 綠色 (#2ecc71)
            fig_main.add_hline(
                y=sigma_neg_1, 
                line_dash="dash", 
                line_color="#2ecc71", 
                line_width=1.5, 
                annotation_text=f"定投線 (-1σ)", 
                annotation_position="bottom left", 
                annotation_font_color="#2ecc71",
                secondary_y=False
            )
            
            # 2. 抄底線 (-2σ): 紅色 (#e74c3c), 加粗
            fig_main.add_hline(
                y=sigma_neg_2, 
                line_dash="dot", 
                line_color="#e74c3c", 
                line_width=2.5, 
                annotation_text=f"抄底線 (-2σ)", 
                annotation_position="bottom left", 
                annotation_font_color="#e74c3c",
                secondary_y=False
            )

            # 佈局美化
            fig_main.update_layout(
                title=f"{ticker_name} - 乖離率實戰分析",
                height=600, hovermode="x unified", plot_bgcolor='white',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_main.update_yaxes(title_text="乖離率 %", tickformat=".0%", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
            fig_main.update_yaxes(title_text="價格", secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_main, use_container_width=True)

            # --- 歷史分佈圖 (同步修改) ---
            st.divider()
            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("📊 乖離率分佈與落點")
                fig_hist = go.Figure(go.Histogram(x=df['Gap'], nbinsx=100, marker_color='royalblue', opacity=0.6, name='分佈'))
                
                # 分佈圖線條同步
                fig_hist.add_vline(x=sigma_neg_1, line_dash="dash", line_width=2, line_color="#2ecc71", annotation_text="定投區")
                fig_hist.add_vline(x=sigma_neg_2, line_dash="dot", line_width=3, line_color="#e74c3c", annotation_text="抄底區")

                fig_hist.update_layout(xaxis_tickformat=".0%", height=350, plot_bgcolor='white', bargap=0.1)
                st.plotly_chart(fig_hist, use_container_width=True)

            with col_r:
                st.subheader("🎯 實戰訊號 5日回測")
                
                # 計算：跌破定投線後的表現
                dca_t = df[df['Gap'] <= sigma_neg_1].dropna(subset=['Return_5D'])
                wr_dca = len(dca_t[dca_t['Return_5D'] > 0]) / len(dca_t) if not dca_t.empty else 0
                
                # 計算：跌破抄底線後的表現
                bot_t = df[df['Gap'] <= sigma_neg_2].dropna(subset=['Return_5D'])
                wr_bot = len(bot_t[bot_t['Return_5D'] > 0]) / len(bot_t) if not bot_t.empty else 0

                c_rc1, c_rc2 = st.columns(2)
                c_rc1.metric("觸及 定投線 後上漲機率", f"{wr_dca:.1%}")
                c_rc2.metric("觸及 抄底線 後上漲機率", f"{wr_bot:.1%}")
                
                st.write(f"💡 訊號次數：定投機會 {len(dca_t)} 次 / 抄底機會 {len(bot_t)} 次")
                st.caption("註：勝率為訊號出現後持有 5 日為正報酬的機率。")

            # --- 數據摘要 ---
            st.divider()
            st.subheader("📋 實戰數據摘要")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("目前價格", f"{df['Price'].iloc[-1]:.2f}")
            m2.metric("目前乖離率", f"{df['Gap'].iloc[-1]:.2%}")
            m3.metric("標準差 (σ)", f"{gap_std_all:.2%}")

            st.caption("👇 你的進場參考點 (基於乖離率推算)：")
            sd1, sd2, sd3 = st.columns(3)
            
            # 推算當前均線下的對應價格
            current_sma = df['SMA'].iloc[-1]
            price_at_dca = current_sma * (1 + sigma_neg_1)
            price_at_bot = current_sma * (1 + sigma_neg_2)

            with sd1:
                 sd1.metric("📉 負乖離平均", f"{df[df['Gap'] < 0]['Gap'].mean():.2%}")
            with sd2:
                sd2.metric("🟢 定投線位置 (-1σ)", f"{sigma_neg_1:.2%}", delta="適合分批", delta_color="off")
            with sd3:
                sd3.metric("🔴 抄底線位置 (-2σ)", f"{sigma_neg_2:.2%}", delta="極度恐慌", delta_color="inverse")

    except Exception as e:
        st.error(f"分析過程中發生錯誤：{e}")

else:
    if not selected_file:
         st.info("👆 請確認 data 資料夾內有 CSV 檔案。")
    elif not submitted:
         st.info("👆 請選擇標的並點擊「讀取檔案並分析」。")
