###############################################################
# app.py — SMA 乖離率戰情室 (本地 CSV 正2限定版)
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
    page_title="Hamr Lab | 極端乖離回測戰情室 (本地版)",
    layout="wide",
)

with st.sidebar:
    st.title("🐹 倉鼠導覽")
    st.page_link("https://hamr-lab.com/", label="回到量化戰情室首頁", icon="🏠")
    st.divider()
    st.info("💡 資料來源模式：已切換為本地 `data/` 資料夾讀取模式。")
    st.caption("請確保 CSV 檔名包含代號 (如 00631L.TW.csv) 且內含 Date 與 Close 欄位。")

st.title("📊 SMA 乖離率深度量化戰情室 (正2 標準差版)")

# ===============================================================
# 區塊 1: 參數設定與檔案讀取
# ===============================================================
with st.container(border=True):
    # --- 自動掃描 data 資料夾 ---
    data_dir = "data"
    csv_files = []
    
    if os.path.exists(data_dir):
        # 讀取目錄下所有 csv 檔案
        csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        csv_files.sort() # 排序讓清單整齊
    else:
        st.error(f"❌ 找不到 '{data_dir}' 資料夾，請確認目錄結構。")

    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    
    with c1:
        if csv_files:
            # 使用下拉選單取代文字輸入
            selected_file = st.selectbox("選擇本地標的 (從 data 資料夾)", csv_files, index=0)
            ticker_name = selected_file.replace(".csv", "") # 顯示用名稱
        else:
            selected_file = None
            st.warning("⚠️ data 資料夾內沒有 CSV 檔案")
            
    with c2:
        start_date = st.date_input("開始日期", datetime.now() - timedelta(days=365*5))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    # 參數設定
    c4, c5 = st.columns([1, 2])
    with c4:
        sma_window = st.number_input("SMA 均線週期", value=200)
    with c5:
        st.write("") # 佔位用

    submitted = st.button("🚀 讀取檔案並分析", use_container_width=True, type="primary")

# ===============================================================
# 區塊 2: 繪圖與回測邏輯
# ===============================================================
if submitted and selected_file:
    file_path = os.path.join(data_dir, selected_file)
    
    try:
        # 讀取 CSV
        df_raw = pd.read_csv(file_path)
        
        # --- 資料清洗與格式化 ---
        # 1. 確保日期欄位存在並轉換格式
        if 'Date' in df_raw.columns:
            df_raw['Date'] = pd.to_datetime(df_raw['Date'])
            df_raw.set_index('Date', inplace=True)
        else:
            st.error("CSV 檔案中缺少 'Date' 欄位，無法解析。")
            st.stop()
            
        # 2. 篩選日期區間
        # 轉換 input date 為 datetime64 以進行比較
        tz_start = pd.to_datetime(start_date)
        tz_end = pd.to_datetime(end_date)
        df = df_raw.sort_index().loc[tz_start:tz_end].copy()

        # 3. 確保有 Close 欄位
        if 'Close' not in df.columns:
             # 有些下載的資料可能是 Adj Close，做個簡單的檢查
            if 'Adj Close' in df.columns:
                df['Price'] = df['Adj Close']
            else:
                st.error("CSV 檔案中找不到 'Close' 或 'Adj Close' 價格欄位。")
                st.stop()
        else:
            df['Price'] = df['Close']
        
        # 確保價格為數值型態
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
        df = df.dropna(subset=['Price'])

        if df.empty:
            st.warning("⚠️ 選定的日期區間內無數據。")
        else:
            # --- 指標與回測數據計算 (邏輯同前) ---
            df['SMA'] = df['Price'].rolling(window=sma_window).mean()
            df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
            df['Return_5D'] = (df['Price'].shift(-5) - df['Price']) / df['Price']
            df = df.dropna(subset=['SMA', 'Gap'])

            # --- 統計數據計算 (標準差) ---
            gap_mean_all = df['Gap'].mean()
            gap_std_all = df['Gap'].std()
            
            # 計算 1倍 與 2倍 標準差位置
            sigma_pos_1 = gap_mean_all + (1 * gap_std_all)
            sigma_neg_1 = gap_mean_all - (1 * gap_std_all)
            sigma_pos_2 = gap_mean_all + (2 * gap_std_all)
            sigma_neg_2 = gap_mean_all - (2 * gap_std_all)

            # --- 主圖表：雙軸疊圖 ---
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

            # --- 標準差警戒線 ---
            # ±2σ (紫色，較粗)
            fig_main.add_hline(y=sigma_pos_2, line_dash="dot", line_color="#9b59b6", line_width=1.5, annotation_text=f"+2σ", annotation_position="top left", secondary_y=False)
            fig_main.add_hline(y=sigma_neg_2, line_dash="dot", line_color="#9b59b6", line_width=1.5, annotation_text=f"-2σ", annotation_position="bottom left", secondary_y=False)
            # ±1σ (灰色，較細)
            fig_main.add_hline(y=sigma_pos_1, line_dash="dash", line_color="gray", line_width=1, opacity=0.5, annotation_text=f"+1σ", annotation_position="top left", secondary_y=False)
            fig_main.add_hline(y=sigma_neg_1, line_dash="dash", line_color="gray", line_width=1, opacity=0.5, annotation_text=f"-1σ", annotation_position="bottom left", secondary_y=False)

            # 佈局美化
            fig_main.update_layout(
                title=f"{ticker_name} - 乖離率分析",
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
                st.subheader("📊 乖離率常態分佈圖")
                fig_hist = go.Figure(go.Histogram(x=df['Gap'], nbinsx=100, marker_color='royalblue', opacity=0.6, name='分佈'))
                
                # 分佈圖上的標準差線
                fig_hist.add_vline(x=sigma_pos_2, line_dash="dot", line_width=2, line_color="#9b59b6", annotation_text="+2σ")
                fig_hist.add_vline(x=sigma_neg_2, line_dash="dot", line_width=2, line_color="#9b59b6", annotation_text="-2σ", annotation_position="bottom right")
                fig_hist.add_vline(x=sigma_pos_1, line_dash="dash", line_width=1, line_color="gray", annotation_text="+1σ")
                fig_hist.add_vline(x=sigma_neg_1, line_dash="dash", line_width=1, line_color="gray", annotation_text="-1σ")

                fig_hist.update_layout(xaxis_tickformat=".0%", height=350, plot_bgcolor='white', bargap=0.1)
                st.plotly_chart(fig_hist, use_container_width=True)

            with col_r:
                st.subheader("🎯 極端訊號 (±2σ) 5日回測")
                # 過熱統計 (> +2σ)
                ov_t = df[df['Gap'] >= sigma_pos_2].dropna(subset=['Return_5D'])
                wr_ov = len(ov_t[ov_t['Return_5D'] < 0]) / len(ov_t) if not ov_t.empty else 0
                
                # 恐慌統計 (< -2σ)
                un_t = df[df['Gap'] <= sigma_neg_2].dropna(subset=['Return_5D'])
                wr_un = len(un_t[un_t['Return_5D'] > 0]) / len(un_t) if not un_t.empty else 0

                c_rc1, c_rc2 = st.columns(2)
                c_rc1.metric("高於 +2σ 後下跌勝率", f"{wr_ov:.1%}")
                c_rc2.metric("低於 -2σ 後上漲勝率", f"{wr_un:.1%}")
                st.write(f"💡 樣本數：觸發 +2σ {len(ov_t)} 次 / 觸發 -2σ {len(un_t)} 次")
                st.caption("註：勝率計算基礎為該極端值出現後，持有5日是否反向回歸。")

            # --- 數據摘要 ---
            st.divider()
            st.subheader("📋 乖離率統計摘要")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("目前價格", f"{df['Price'].iloc[-1]:.2f}")
            m2.metric("目前乖離率", f"{df['Gap'].iloc[-1]:.2%}")
            m3.metric("歷史最大/小乖離", f"{df['Gap'].max():.1%} / {df['Gap'].min():.1%}")

            st.caption("🔍 波動率統計 (基於歷史常態分佈)：")
            sd1, sd2, sd3, sd4 = st.columns(4)
            with sd1:
                sd1.metric("標準差 (σ)", f"{gap_std_all:.2%}")
            with sd2:
                sd2.metric("平均乖離", f"{gap_mean_all:.2%}")
            with sd3:
                sd3.metric("+2σ 價格/乖離", f"{sigma_pos_2:.2%}")
            with sd4:
                sd4.metric("-2σ 價格/乖離", f"{sigma_neg_2:.2%}")

            st.caption("📊 正負乖離分群統計：")
            pos_gaps = df[df['Gap'] > 0]['Gap']
            neg_gaps = df[df['Gap'] < 0]['Gap']

            stat1, stat2, stat3, stat4 = st.columns(4)
            with stat1:
                val = pos_gaps.mean() if not pos_gaps.empty else 0
                st.metric("📈 正乖離平均", f"{val:.2%}")
            with stat2:
                val = pos_gaps.median() if not pos_gaps.empty else 0
                st.metric("📈 正乖離中位數", f"{val:.2%}")
            with stat3:
                val = neg_gaps.mean() if not neg_gaps.empty else 0
                st.metric("📉 負乖離平均", f"{val:.2%}")
            with stat4:
                val = neg_gaps.median() if not neg_gaps.empty else 0
                st.metric("📉 負乖離中位數", f"{val:.2%}")

    except Exception as e:
        st.error(f"讀取或處理檔案時發生錯誤：{e}")

elif not ticker_input and not selected_file:
     st.info("👆 請確認 data 資料夾內有 CSV 檔案。")
