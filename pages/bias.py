###############################################################
# app.py — 50正2定投抄底指標 (色塊區域版 + Auth)
###############################################################

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import sys

# ===============================================================
# 1. 頁面設定 & 驗證守門員
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2定投抄底指標",
    page_icon="📈",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import auth
    if not auth.check_password():
        st.stop()  # 驗證沒過就停止執行
except ImportError:
    st.warning("⚠️ 找不到 auth 模組，跳過驗證 (僅限測試模式)")

# ------------------------------------------------------
# 側邊欄導覽
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    
    st.divider()
    st.info("💡 設計理念：致敬比特幣 ahr999 囤幣指標。")
    st.markdown("""
    **策略邏輯：**
    - **🟢 定投區 (-1σ ~ -2σ)**: 綠色區塊。價格回落至合理區間，適合執行定期定額。
    - **🔴 抄底區 (< -2σ)**: 紅色區塊。極度恐慌時刻，價格遭錯殺，考慮加大部位抄底。
    """)

# 主標題
st.title("🚀 50正2定投抄底指標 (Accumulation Index)")

# ===============================================================
# 區塊 1: 參數設定與檔案讀取
# ===============================================================
with st.container(border=True):
    TARGET_MAP = {
        "00631L 元大台灣50正2": "00631L.TW.csv",
        "00663L 國泰台灣加權正2": "00663L.TW.csv",
        "00675L 富邦台灣加權正2": "00675L.TW.csv",
        "00685L 群益台灣加權正2": "00685L.TW.csv"
    }
    
    data_dir = "data"
    available_options = []
    
    if os.path.exists(data_dir):
        for display_name, filename in TARGET_MAP.items():
            if os.path.exists(os.path.join(data_dir, filename)):
                available_options.append(display_name)
    else:
        st.error(f"❌ 找不到 '{data_dir}' 資料夾，請確認目錄結構。")

    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    
    selected_file = None
    ticker_name = "未知標的"

    with c1:
        if available_options:
            selected_option = st.selectbox("選擇囤幣標的 (台股正2)", available_options, index=0)
            selected_file = TARGET_MAP[selected_option]
            ticker_name = selected_option 
        else:
            st.warning("⚠️ data 資料夾內找不到指定的正2 CSV 檔案")
            
    with c2:
        start_date = st.date_input("開始日期", datetime.now() - timedelta(days=365*5))
    with c3:
        end_date = st.date_input("結束日期", datetime.now())

    c4, c5 = st.columns([1, 2])
    with c4:
        sma_window = st.number_input("基準均線週期 (預設 200)", value=200)
    with c5:
        st.write("") 

    submitted = st.button("🚀 開始分析囤幣區間", use_container_width=True, type="primary")

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

        if 'Close' not in df_raw.columns:
            if 'Adj Close' in df_raw.columns:
                df_raw['Price'] = df_raw['Adj Close']
            else:
                st.error("找不到 'Close' 欄位。")
                st.stop()
        else:
            df_raw['Price'] = df_raw['Close']
        
        df_raw['Price'] = pd.to_numeric(df_raw['Price'], errors='coerce')
        df_raw = df_raw.dropna(subset=['Price'])

        # --- 先計算全歷史指標 ---
        df_raw['SMA'] = df_raw['Price'].rolling(window=sma_window).mean()
        df_raw['Gap'] = (df_raw['Price'] - df_raw['SMA']) / df_raw['SMA']
        df_raw['Return_5D'] = (df_raw['Price'].shift(-5) - df_raw['Price']) / df_raw['Price']

        # --- 再進行時間切分 ---
        tz_start = pd.to_datetime(start_date)
        tz_end = pd.to_datetime(end_date)
        df = df_raw.sort_index().loc[tz_start:tz_end].copy()

        df = df.dropna(subset=['SMA', 'Gap'])

        if df.empty:
            st.warning(f"⚠️ 選定區間 ({start_date} ~ {end_date}) 內無有效數據。")
        else:
            # --- 統計數據 ---
            gap_mean_all = df['Gap'].mean()
            gap_std_all = df['Gap'].std()
            
            # 定義：定投線 (-1σ), 抄底線 (-2σ)
            sigma_neg_1 = gap_mean_all - (1 * gap_std_all)
            sigma_neg_2 = gap_mean_all - (2 * gap_std_all)
            
            # 定義區域下限 (為了畫紅色區塊，取一個比歷史最低還低一點的值)
            min_gap_display = min(df['Gap'].min(), sigma_neg_2) * 1.2

            # --- 主圖表 ---
            fig_main = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 1. 乖離率 (左軸) - 藍色線
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Gap'], name="指標數值 (左軸)", 
                line=dict(color='#2980b9', width=1.5),
                # 移除原本的藍色填充，避免與背景色塊混淆，或者保留淡淡的
                # fill='tozeroy', fillcolor='rgba(41, 128, 185, 0.05)' 
            ), secondary_y=False)

            # 2. 價格 (右軸) - 橘色線
            fig_main.add_trace(go.Scatter(
                x=df.index, y=df['Price'], name="收盤價 (右軸)", 
                line=dict(color='#ff7f0e', width=2.5) 
            ), secondary_y=True)

            # 3. [已移除] SMA 線 
            # 依據需求，這裡不再繪製 SMA 線，但保留在變數中供計算使用

            # --- 繪製背景色塊 (Zones) ---
            
            # 🟢 定投區 (Green Zone): -1σ 到 -2σ 之間
            fig_main.add_hrect(
                y0=sigma_neg_1, y1=sigma_neg_2,
                fillcolor="#2ecc71", opacity=0.15,
                layer="below", line_width=0,
                secondary_y=False,
                annotation_text="定投區", annotation_position="top left", annotation_font_color="#27ae60"
            )

            # 🔴 抄底區 (Red Zone): -2σ 以下
            fig_main.add_hrect(
                y0=sigma_neg_2, y1=min_gap_display, # 延伸到圖表底部
                fillcolor="#e74c3c", opacity=0.15,
                layer="below", line_width=0,
                secondary_y=False,
                annotation_text="抄底區", annotation_position="bottom left", annotation_font_color="#c0392b"
            )

            # 輔助線 (邊界線) - 讓區間邊界更清楚
            fig_main.add_hline(y=sigma_neg_1, line_dash="dash", line_color="#2ecc71", line_width=1, secondary_y=False)
            fig_main.add_hline(y=sigma_neg_2, line_dash="dash", line_color="#e74c3c", line_width=1, secondary_y=False)

            fig_main.update_layout(
                title=f"{ticker_name} - 囤幣指標走勢圖",
                height=600, hovermode="x unified", plot_bgcolor='white',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_main.update_yaxes(title_text="指標強度 %", tickformat=".0%", secondary_y=False, showgrid=True, gridcolor='whitesmoke')
            fig_main.update_yaxes(title_text="價格", secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_main, use_container_width=True)

            # --- 歷史分佈圖 ---
            st.divider()
            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("📊 指標落點分佈")
                fig_hist = go.Figure(go.Histogram(x=df['Gap'], nbinsx=100, marker_color='#2980b9', opacity=0.6, name='分佈'))
                # 分佈圖也加上色塊或線條對照
                fig_hist.add_vline(x=sigma_neg_1, line_dash="dash", line_width=2, line_color="#2ecc71", annotation_text="定投線")
                fig_hist.add_vline(x=sigma_neg_2, line_dash="dot", line_width=3, line_color="#e74c3c", annotation_text="抄底線")
                fig_hist.update_layout(xaxis_tickformat=".0%", height=350, plot_bgcolor='white', bargap=0.1)
                st.plotly_chart(fig_hist, use_container_width=True)

            with col_r:
                st.subheader("🎯 策略回測 (5日後表現)")
                
                dca_t = df[df['Gap'] <= sigma_neg_1].dropna(subset=['Return_5D'])
                wr_dca = len(dca_t[dca_t['Return_5D'] > 0]) / len(dca_t) if not dca_t.empty else 0
                
                bot_t = df[df['Gap'] <= sigma_neg_2].dropna(subset=['Return_5D'])
                wr_bot = len(bot_t[bot_t['Return_5D'] > 0]) / len(bot_t) if not bot_t.empty else 0

                c_rc1, c_rc2 = st.columns(2)
                c_rc1.metric("定投區 (綠區) 勝率", f"{wr_dca:.1%}")
                c_rc2.metric("抄底區 (紅區) 勝率", f"{wr_bot:.1%}")
                
                st.write(f"💡 機會次數：落入綠區 {len(dca_t)} 天 / 落入紅區 {len(bot_t)} 天")
                st.caption("註：勝率為訊號出現後持有 5 日為正報酬的機率。")

            # --- 數據摘要 (精簡版) ---
            st.divider()
            st.subheader("📋 囤幣價格參考表")

            # 重新計算建議價格
            current_sma = df['SMA'].iloc[-1]
            price_at_dca = current_sma * (1 + sigma_neg_1)
            price_at_bot = current_sma * (1 + sigma_neg_2)
            
            k1, k2, k3 = st.columns(3)
            
            with k1:
                st.metric("目前價格", f"{df['Price'].iloc[-1]:.2f}")
                
            with k2:
                st.metric("🟢 定投買入價 (進入綠區)", f"{price_at_dca:.2f}", delta="開始分批", delta_color="off")
                
            with k3:
                st.metric("🔴 抄底買入價 (進入紅區)", f"{price_at_bot:.2f}", delta="重倉機會", delta_color="inverse")

    except Exception as e:
        st.error(f"分析過程中發生錯誤：{e}")

else:
    if not available_options:
         st.info("👆 請確認 data 資料夾內有 00631L, 00663L, 00675L 或 00685L 的 CSV 檔案。")
    elif not submitted:
         st.info("👆 請選擇囤幣標的並點擊「開始分析囤幣區間」。")
