###############################################################
# app.py — 50正2定投抄底雷達 (全版 K 線版 - 移除波動率摘要)
###############################################################

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# ===============================================================
# 1. 頁面設定 & 驗證
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2年度統計雷達",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ------------------------------------------------------
# 側邊欄 Sidebar
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    st.divider()
    st.info("💡 設計理念：透過 200SMA 乖離率與歷史標準差，尋找台股正2的極度恐慌買點。")

st.title("🚀 50正2年度乖離 K 線雷達")

# ===============================================================
# 2. 參數設定
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
        selected_option = st.selectbox("🎯 選擇標的 (自動計算全歷史)", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("基準均線週期 (SMA)", value=200)

# ===============================================================
# 3. 核心數據運算
# ===============================================================
file_path = os.path.join(data_dir, selected_file)

try:
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    df['Price'] = pd.to_numeric(df[price_col], errors='coerce')
    df = df.dropna(subset=['Price']).sort_index()

    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()


    # ===============================================================
    # 5. 全歷史主圖表
    # ===============================================================
    st.divider()
    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    sigma_neg_1, sigma_neg_2 = gap_mean - gap_std, gap_mean - 2 * gap_std
    min_gap_display = min(df_clean['Gap'].min(), sigma_neg_2) * 1.2

    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", line=dict(color='#2980b9', width=1.5)), secondary_y=False)
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Price'], name="收盤價", line=dict(color='#ff7f0e', width=2), opacity=0.4), secondary_y=True)

    # 區域填充
    fig_main.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.1, layer="below", secondary_y=False)
    fig_main.add_hrect(y0=sigma_neg_2, y1=min_gap_display, fillcolor="#e74c3c", opacity=0.1, layer="below", secondary_y=False)

    fig_main.update_layout(title=f"{selected_option} 全歷史走勢", height=550, hovermode="x unified", template="plotly_white")
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 6. 價格參考點
    # ===============================================================
    st.divider()
    current_sma = df_clean['SMA'].iloc[-1]
    k1, k2, k3 = st.columns(3)
    k1.metric("當前收盤價", f"{df_clean['Price'].iloc[-1]:.2f}")
    k2.metric("🟢 定投啟動價 (-1σ)", f"{current_sma * (1 + sigma_neg_1):.2f}")
    k3.metric("🔴 破盤抄底價 (-2σ)", f"{current_sma * (1 + sigma_neg_2):.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
