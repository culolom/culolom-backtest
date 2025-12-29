import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# ===============================================================
# 1. 頁面設定
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2乖離雷達",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證 (略過，保留你原本的邏輯)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ------------------------------------------------------
# 側邊欄
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.info("💡 指標說明：\n- 1σ 約涵蓋 68% 走勢\n- 2σ 約涵蓋 95% 走勢")

st.title("🚀 50正2 乖離率四階段雷達")

# ===============================================================
# 2. 數據讀取與運算
# ===============================================================
data_dir = "data"
TARGET_MAP = {
    "00631L 元大台灣50正2": "00631L.TW.csv",
    "00663L 國泰台灣加權正2": "00663L.TW.csv",
    "00675L 富邦台灣加權正2": "00675L.TW.csv",
    "00685L 群益台灣加權正2": "00685L.TW.csv"
}

available_options = [name for name, f in TARGET_MAP.items() if os.path.exists(os.path.join(data_dir, f))]

if not available_options:
    st.error("❌ 找不到數據檔案")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_option = st.selectbox("🎯 選擇標的", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("基準均線週期 (SMA)", value=200)

file_path = os.path.join(data_dir, selected_file)

try:
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    df['Price'] = pd.to_numeric(df[price_col], errors='coerce')
    df = df.dropna(subset=['Price']).sort_index()

    # 計算乖離率
    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    # 計算四個標準差位階
    gap_mean = df_clean['Gap'].mean()
    gap_std = df_clean['Gap'].std()
    
    s_pos2 = gap_mean + 2 * gap_std  # 套利線
    s_pos1 = gap_mean + gap_std      # 警戒線
    s_neg1 = gap_mean - gap_std      # 定投線
    s_neg2 = gap_mean - 2 * gap_std  # 抄底線

    # ===============================================================
    # 3. 四大指標卡片 (顯示百分比)
    # ===============================================================
    st.subheader("📊 歷史乖離率參考 (基於 200SMA)")
    m1, m2, m3, m4 = st.columns(4)
    
    # 這裡顯示百分比，並加上顏色標籤
    m1.metric("🔴 套利線 (+2σ)", f"{s_pos2*100:.1f}%")
    m2.metric("🟡 警戒線 (+1σ)", f"{s_pos1*100:.1f}%")
    m3.metric("🟢 定投線 (-1σ)", f"{s_neg1*100:.1f}%")
    m4.metric("🔵 抄底線 (-2σ)", f"{s_neg2*100:.1f}%")

    # ===============================================================
    # 4. 全歷史主圖表 (加四條線)
    # ===============================================================
    st.divider()
    
    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 1. 乖離率曲線
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Gap'], 
        name="指標乖離率", 
        line=dict(color='#2980b9', width=1.5)
    ), secondary_y=False)
    
    # 2. 收盤價曲線 (淡化處理)
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Price'], 
        name="收盤價", 
        line=dict(color='#ff7f0e', width=1.5), 
        opacity=0.2
    ), secondary_y=True)

    # 3. 加入四條水平參考線
    def add_ref_line(fig, y_val, label, color):
        fig.add_hline(
            y=y_val, 
            line=dict(color=color, width=1, dash="dash"),
            annotation_text=label,
            annotation_position="top right",
            secondary_y=False
        )

    add_ref_line(fig_main, s_pos2, "套利 +2σ", "#e74c3c")
    add_ref_line(fig_main, s_pos1, "警戒 +1σ", "#f1c40f")
    add_ref_line(fig_main, s_neg1, "定投 -1σ", "#2ecc71")
    add_ref_line(fig_main, s_neg2, "抄底 -2σ", "#3498db")

    fig_main.update_layout(
        title=f"{selected_option} 歷史乖離率與操作位階",
        height=600,
        hovermode="x unified",
        template="plotly_white",
        yaxis=dict(tickformat=".1%"), # 讓 Y 軸顯示百分比
    )
    
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 5. 當前價格參考 (收納)
    # ===============================================================
    with st.expander("📌 查看今日對應價格參考"):
        curr_p = df_clean['Price'].iloc[-1]
        curr_sma = df_clean['SMA'].iloc[-1]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.write(f"今日收盤：**{curr_p:.2f}**")
        c2.write(f"200SMA：**{curr_sma:.2f}**")
        c3.write(f"定投價 (-1σ)：**{curr_sma * (1 + s_neg1):.2f}**")
        c4.write(f"抄底價 (-2σ)：**{curr_sma * (1 + s_neg2):.2f}**")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
