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

# 🔒 驗證守門員 (保留原有的驗證邏輯)
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
    st.info("💡 設計理念：透過 SMA 乖離率與歷史標準差，尋找台股正2的極度恐慌買點。")

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
    st.error("❌ 找不到數據檔案，請確認 data 資料夾內是否有對應的 CSV 文件。")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_option = st.selectbox("🎯 選擇標的 (自動計算全歷史)", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("基準均線週期 (SMA)", value=200, min_value=10)

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

    # 計算 SMA 與 乖離率
    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    # ===============================================================
    # 4. 年度乖離統計 (K 線化)
    # ===============================================================
    st.subheader(f"📅 年度 {sma_window}SMA 乖離 K 線 + 震盪範圍")
    
    yearly_df = df_clean.copy()
    yearly_df['Year'] = yearly_df.index.year
    
    # 依照你的需求：最大、最小、平均、第一天、最後一天
    stats_k = yearly_df.groupby('Year').agg({
        'Gap': ['max', 'min', 'first', 'last', 'mean'],
        'Price': ['first', 'last']
    })
    stats_k.columns = ['max_gap', 'min_gap', 'open_gap', 'close_gap', 'avg_gap', 'open_price', 'close_price']
    
    # 顏色邏輯：若年度價格上漲則為紅，下跌為綠
    stats_k['is_up'] = stats_k['close_price'] > stats_k['open_price']
    stats_k['range_gap'] = stats_k['max_gap'] - stats_k['min_gap']
    
    fig_k = make_subplots(specs=[[{"secondary_y": True}]])

    # 背景：年度震盪總幅度 (右軸)
    fig_k.add_trace(go.Scatter(
        x=stats_k.index, y=stats_k['range_gap'],
        mode='lines+markers',
        name='年度乖離震盪寬度',
        line=dict(color='rgba(150, 150, 150, 0.4)', width=2, dash='dot'),
        marker=dict(symbol='diamond', size=8, color='gray'),
        hovertemplate="年度最大震盪幅度: %{y:.2%}<extra></extra>"
    ), secondary_y=True)

    # 繪製年度乖離 K 線
    for year, row in stats_k.iterrows():
        color = "#e74c3c" if row['is_up'] else "#2ecc71"
        
        # 1. 影線 (Max - Min)
        fig_k.add_trace(go.Scatter(
            x=[year, year], y=[row['min_gap'], row['max_gap']],
            mode='lines',
            line=dict(color=color, width=1.5),
            showlegend=False,
            hoverinfo='skip'
        ), secondary_y=False)
        
        # 2. 實體 (First - Last)
        # 使用方形標記模擬 K 線實體，或直接連線
        fig_k.add_trace(go.Scatter(
            x=[year], y=[(row['open_gap'] + row['close_gap'])/2],
            mode='markers',
            marker=dict(
                symbol='square', 
                size=24, 
                color=color,
                line=dict(width=0)
            ),
            customdata=[[row['open_gap'], row['close_gap'], row['max_gap'], row['min_gap'], row['avg_gap']]],
            hovertemplate=(
                "<b>年份: %{x}</b><br>" +
                "年初乖離: %{customdata[0]:.2%}<br>" +
                "年底乖離: %{customdata[1]:.2%}<br>" +
                "最高乖離: %{customdata[2]:.2%}<br>" +
                "最低乖離: %{customdata[3]:.2%}<br>" +
                "平均乖離: %{customdata[4]:.2%}<br>" +
                "<extra></extra>"
            ),
            showlegend=False
        ), secondary_y=False)

        # 3. 年度平均值點 (白點)
        fig_k.add_trace(go.Scatter(
            x=[year], y=[row['avg_gap']],
            mode='markers',
            marker=dict(color='white', size=6, line=dict(color='black', width=1)),
            name='年平均乖離',
            showlegend=False,
            hoverinfo='skip'
        ), secondary_y=False)

    fig_k.update_layout(
        height=550,
        template="plotly_white",
        xaxis=dict(title="年份", dtick=1, gridcolor='whitesmoke'),
        yaxis=dict(title=f"{sma_window}SMA 乖離率 (K線) %", tickformat=".0%", gridcolor='whitesmoke'),
        yaxis2=dict(title="年度總震盪幅度 %", tickformat=".0%", showgrid=False, range=[0, stats_k['range_gap'].max() * 1.5]),
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_k, use_container_width=True)

    # 數據表摺疊顯示
    with st.expander("📊 查看年度數據摘要表"):
        display_stats = stats_k[['open_gap', 'close_gap', 'max_gap', 'min_gap', 'avg_gap', 'range_gap']].copy()
        display_stats.columns = ['年初乖離', '年底乖離', '最高乖離', '最低乖離', '平均乖離', '震盪幅度']
        st.dataframe(display_stats.iloc[::-1].style.format("{:.2%}"), use_container_width=True)

    # ===============================================================
    # 5. 全歷史主圖表
    # ===============================================================
    st.divider()
    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    sigma_neg_1, sigma_neg_2 = gap_mean - gap_std, gap_mean - 2 * gap_std
    min_gap_display = min(df_clean['Gap'].min(), sigma_neg_2) * 1.2

    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    # 乖離率線
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", line=dict(color='#2980b9', width=1.5)), secondary_y=False)
    # 收盤價線 (淡化處理)
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Price'], name="收盤價", line=dict(color='#ff7f0e', width=1.5), opacity=0.3), secondary_y=True)

    # 恐慌區間填充
    fig_main.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.1, layer="below", secondary_y=False, annotation_text="-1σ 定投區")
    fig_main.add_hrect(y0=sigma_neg_2, y1=min_gap_display, fillcolor="#e74c3c", opacity=0.1, layer="below", secondary_y=False, annotation_text="-2σ 抄底區")

    fig_main.update_layout(title=f"{selected_option} 全歷史走勢", height=500, hovermode="x unified", template="plotly_white")
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 6. 價格參考點 (Dashboard 下方資訊欄)
    # ===============================================================
    st.divider()
    current_sma = df_clean['SMA'].iloc[-1]
    current_price = df_clean['Price'].iloc[-1]
    current_gap = df_clean['Gap'].iloc[-1]
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("當前收盤價", f"{current_price:.2f}", f"{current_gap:.2%}")
    k2.metric(f"當前 {sma_window}SMA", f"{current_sma:.2f}")
    k3.metric("🟢 定投價 (-1σ)", f"{current_sma * (1 + sigma_neg_1):.2f}")
    k4.metric("🔴 抄底價 (-2σ)", f"{current_sma * (1 + sigma_neg_2):.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
    st.info("請檢查 CSV 數據格式是否包含 Date, Close (或 Adj Close) 等欄位。")
