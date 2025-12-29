###############################################################
# app.py — 50正2定投抄底雷達 (歷年趨勢圖版)
###############################################################

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# ===============================================================
# 1. 頁面設定 & 驗證守門員
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2定投抄底雷達",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證守門員 (若無 auth.py 則跳過)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth
    if not auth.check_password():
        st.stop()  
except ImportError:
    st.warning("⚠️ 找不到 auth 模組，暫以測試模式執行")

# 側邊欄導覽
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.info("💡 策略邏輯：\n- 🟢 定投區 (-1σ ~ -2σ)\n- 🔴 抄底區 (< -2σ)")
    st.caption("基準：收盤價與 200SMA 之乖離率")

st.title("🚀 50正2定投抄底雷達")

# ===============================================================
# 2. 參數設定 (自動觸發)
# ===============================================================
data_dir = "data"
TARGET_MAP = {
    "00631L 元大台灣50正2": "00631L.TW.csv",
    "00663L 國泰台灣加權正2": "00663L.TW.csv",
    "00675L 富邦台灣加權正2": "00675L.TW.csv",
    "00685L 群益台灣加權正2": "00685L.TW.csv"
}

# 檢查現有檔案
available_options = []
if os.path.exists(data_dir):
    for display_name, filename in TARGET_MAP.items():
        if os.path.exists(os.path.join(data_dir, filename)):
            available_options.append(display_name)
else:
    st.error(f"❌ 找不到 '{data_dir}' 資料夾")

if not available_options:
    st.warning("⚠️ 請確認 data 資料夾內有對應的 CSV 檔案。")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_option = st.selectbox("🎯 選擇標的 (自動計算 2015 至今全歷史)", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("基準均線週期 (SMA)", value=200)

# ===============================================================
# 3. 核心數據運算
# ===============================================================
file_path = os.path.join(data_dir, selected_file)

try:
    # 讀取資料
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # 處理價格欄位
    price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    df['Price'] = pd.to_numeric(df[price_col], errors='coerce')
    df = df.dropna(subset=['Price']).sort_index()

    # 指標計算
    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    df['Daily_Return'] = df['Price'].pct_change()
    df['Return_5D'] = (df['Price'].shift(-5) - df['Price']) / df['Price']
    
    # 移除 SMA 初期空值
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    # ===============================================================
    # 4. 統計區塊：歷年趨勢圖 & 每日統計
    # ===============================================================
    col_stat1, col_stat2 = st.columns([7, 3]) # 調整比例讓圖表寬一點

    with col_stat1:
        st.subheader("📅 歷年乖離率趨勢圖")
        
        # 1. 準備資料 (改為升序排列，以便繪製折線圖)
        yearly_df = df_clean.copy()
        yearly_df['Year'] = yearly_df.index.year
        stats_table = yearly_df.groupby('Year')['Gap'].agg([
            ('最大乖離', 'max'),
            ('最低乖離', 'min'),
            ('平均乖離', 'mean'),
            ('乖離標準差', 'std')
        ]).sort_index(ascending=True) # 重要：改為升序

        # 2. 建立 Plotly Figure
        fig_yearly = go.Figure()

        # 3. 添加四條線
        # 最大乖離 (紅色系)
        fig_yearly.add_trace(go.Scatter(
            x=stats_table.index, y=stats_table['最大乖離'],
            mode='lines+markers', name='最大乖離',
            line=dict(color='#e74c3c', width=2),
            marker=dict(size=6)
        ))
        # 平均乖離 (藍色系)
        fig_yearly.add_trace(go.Scatter(
            x=stats_table.index, y=stats_table['平均乖離'],
            mode='lines+markers', name='平均乖離',
            line=dict(color='#3498db', width=3),
            marker=dict(size=8)
        ))
        # 乖離標準差 (橘/黃色系)
        fig_yearly.add_trace(go.Scatter(
            x=stats_table.index, y=stats_table['乖離標準差'],
            mode='lines+markers', name='乖離標準差',
            line=dict(color='#f39c12', width=2),
            marker=dict(size=6)
        ))
        # 最低乖離 (深紅色，虛線)
        fig_yearly.add_trace(go.Scatter(
            x=stats_table.index, y=stats_table['最低乖離'],
            mode='lines+markers', name='最低乖離',
            line=dict(color='#c0392b', width=2, dash='dot'),
            marker=dict(size=6)
        ))

        # 4. 設定 Layout
        fig_yearly.update_layout(
            height=350,
            hovermode="x unified", # 游標懸停時顯示所有數據
            template="plotly_white",
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            xaxis=dict(
                title="年份",
                dtick=1 # 強制X軸每年都顯示標籤
            ),
            yaxis=dict(
                title="乖離率 %",
                tickformat=".1%" # 設定Y軸為百分比格式
            ),
            margin=dict(l=20, r=20, t=60, b=20)
        )
        
        # 5. 顯示圖表 (取代原本的 st.dataframe)
        st.plotly_chart(fig_yearly, use_container_width=True)

    with col_stat2:
        st.subheader("📊 每日漲跌幅概況")
        # 這裡保持原本的每日統計
        d_avg = df['Daily_Return'].mean()
        d_std = df['Daily_Return'].std()
        d_max = df['Daily_Return'].max()
        d_min = df['Daily_Return'].min()

        st.metric("平均日漲幅", f"{d_avg:.2%}")
        st.metric("漲跌標準差 (波動)", f"{d_std:.2%}")
        st.metric("歷史最大漲幅", f"{d_max:.2%}")
        st.metric("歷史最大跌幅", f"{d_min:.2%}")

    # ===============================================================
    # 5. 主圖表顯示 (保持不變)
    # ===============================================================
    st.divider()
    
    # 計算信心區間邊界
    gap_mean = df_clean['Gap'].mean()
    gap_std = df_clean['Gap'].std()
    sigma_neg_1 = gap_mean - (1 * gap_std)
    sigma_neg_2 = gap_mean - (2 * gap_std)
    min_gap_display = min(df_clean['Gap'].min(), sigma_neg_2) * 1.1

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 乖離率 (左軸)
    fig.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", 
        line=dict(color='#2980b9', width=1.5)
    ), secondary_y=False)

    # 價格 (右軸)
    fig.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Price'], name="收盤價", 
        line=dict(color='#ff7f0e', width=2),
        opacity=0.5
    ), secondary_y=True)

    # 背景色塊
    fig.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.15, layer="below", secondary_y=False, annotation_text="定投區")
    fig.add_hrect(y0=sigma_neg_2, y1=min_gap_display, fillcolor="#e74c3c", opacity=0.15, layer="below", secondary_y=False, annotation_text="抄底區")

    fig.update_layout(
        title=f"{selected_option} 歷史走勢圖 ({df_clean.index.min().date()} ~ {df_clean.index.max().date()})",
        height=600, hovermode="x unified", template="plotly_white",
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
    )
    fig.update_yaxes(title_text="指標強度 %", tickformat=".0%", secondary_y=False)
    fig.update_yaxes(title_text="價格", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)

    # ===============================================================
    # 6. 策略回測與底部價格參考 (保持不變)
    # ===============================================================
    st.divider()
    c_back1, c_back2 = st.columns([1, 1])

    with c_back1:
        st.subheader("🎯 抄底勝率 (持有5日)")
        dca_t = df_clean[df_clean['Gap'] <= sigma_neg_1].dropna(subset=['Return_5D'])
        wr_dca = len(dca_t[dca_t['Return_5D'] > 0]) / len(dca_t) if not dca_t.empty else 0
        bot_t = df_clean[df_clean['Gap'] <= sigma_neg_2].dropna(subset=['Return_5D'])
        wr_bot = len(bot_t[bot_t['Return_5D'] > 0]) / len(bot_t) if not bot_t.empty else 0

        st.write(f"🟢 定投區正報酬機率：**{wr_dca:.1%**}")
        st.write(f"🔴 抄底區正報酬機率：**{wr_bot:.1%**}")
        st.caption(f"全歷史統計：落入綠區 {len(dca_t)} 天 / 紅區 {len(bot_t)} 天")

    with c_back2:
        st.subheader("📋 今日價格參考點")
        current_sma = df_clean['SMA'].iloc[-1]
        p_dca = current_sma * (1 + sigma_neg_1)
        p_bot = current_sma * (1 + sigma_neg_2)
        
        st.metric("當前收盤價", f"{df_clean['Price'].iloc[-1]:.2f}")
        cc1, cc2 = st.columns(2)
        cc1.metric("🟢 定投啟動價", f"{p_dca:.2f}")
        cc2.metric("🔴 破盤抄底價", f"{p_bot:.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
