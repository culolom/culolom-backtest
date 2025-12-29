###############################################################
# app.py — 50正2定投抄底雷達 (年度 K 線 + 波動範圍版)
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
    df['Daily_Return'] = df['Price'].pct_change()
    
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    # ===============================================================
    # 4. 統計區塊：年度乖離 K 線圖
    # ===============================================================
    col_stat1, col_stat2 = st.columns([7, 3])

    with col_stat1:
        st.subheader("📅 年度乖離波動 K 線 + 震盪範圍")
        
        yearly_df = df_clean.copy()
        yearly_df['Year'] = yearly_df.index.year
        
        # 聚合年度數據
        stats_k = yearly_df.groupby('Year').agg({
            'Gap': ['max', 'min', 'first', 'last', 'mean'],
            'Price': ['first', 'last']
        })
        stats_k.columns = ['max_gap', 'min_gap', 'open_gap', 'close_gap', 'avg_gap', 'open_price', 'close_price']
        stats_k['is_up'] = stats_k['close_price'] > stats_k['open_price']
        # 追加：年度乖離 Range (最大 - 最小)
        stats_k['range_gap'] = stats_k['max_gap'] - stats_k['min_gap']
        
        # 建立含雙 Y 軸的圖表
        fig_k = make_subplots(specs=[[{"secondary_y": True}]])

        # 1. 繪製年度範圍 Range 折線 (右軸)
        fig_k.add_trace(go.Scatter(
            x=stats_k.index, y=stats_k['range_gap'],
            mode='lines+markers',
            name='年度震盪總範圍 (Max-Min)',
            line=dict(color='rgba(150, 150, 150, 0.4)', width=2, dash='dot'),
            marker=dict(symbol='diamond', size=8, color='gray'),
            hovertemplate="年度震盪總幅度: %{y:.2%}<extra></extra>"
        ), secondary_y=True)

        for year, row in stats_k.iterrows():
            color = "#e74c3c" if row['is_up'] else "#2ecc71"
            
            # 2. 繪製影線 (High-Low) (左軸)
            fig_k.add_trace(go.Scatter(
                x=[year, year], y=[row['min_gap'], row['max_gap']],
                mode='lines',
                line=dict(color=color, width=1.5),
                showlegend=False,
                hoverinfo='skip'
            ), secondary_y=False)
            
            # 3. 繪製實體 (Open-Close) (左軸)
            fig_k.add_trace(go.Scatter(
                x=[year], y=[(row['open_gap'] + row['close_gap'])/2],
                mode='markers',
                marker=dict(
                    symbol='square',
                    size=22, 
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

            # 4. 標註年平均乖離點 (白色小點) (左軸)
            fig_k.add_trace(go.Scatter(
                x=[year], y=[row['avg_gap']],
                mode='markers',
                marker=dict(color='white', size=5, line=dict(color='black', width=1)),
                name='年平均乖離',
                showlegend=False,
                hoverinfo='skip'
            ), secondary_y=False)

        fig_k.update_layout(
            height=450,
            template="plotly_white",
            xaxis=dict(title="年份", dtick=1, gridcolor='whitesmoke'),
            yaxis=dict(title="乖離率 (K線/均值) %", tickformat=".0%", gridcolor='whitesmoke'),
            yaxis2=dict(title="年度總震盪幅度 (灰色點線) %", tickformat=".0%", showgrid=False, range=[0, stats_k['range_gap'].max() * 1.2]),
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_k, use_container_width=True)
        st.caption("💡 說明：K 線顏色代表該年價格漲跌(紅漲綠跌)；灰色點線為該年「最大-最小乖離」之總寬度，代表年度波動率。")

    with col_stat2:
        st.subheader("📊 波動率摘要")
        d_avg = df['Daily_Return'].mean()
        d_std = df['Daily_Return'].std()
        
        m1, m2 = st.columns(2)
        m1.metric("平均日漲幅", f"{d_avg:.2%}")
        m2.metric("日波動率", f"{d_std:.2%}")
        
        st.write("年度數據摘要：")
        # 整理一個乾淨的表格
        display_stats = stats_k[['max_gap', 'min_gap', 'range_gap', 'avg_gap']].copy()
        display_stats.columns = ['最高乖離', '最低乖離', '波動範圍', '平均乖離']
        st.dataframe(
            display_stats.iloc[::-1].style.format("{:.2%}"), 
            height=300, use_container_width=True
        )

    # ===============================================================
    # 5. 主圖表顯示
    # ===============================================================
    st.divider()
    
    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    sigma_neg_1 = gap_mean - gap_std
    sigma_neg_2 = gap_mean - 2 * gap_std
    min_gap_display = min(df_clean['Gap'].min(), sigma_neg_2) * 1.2

    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 乖離率 (左軸)
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", 
        line=dict(color='#2980b9', width=1.5)
    ), secondary_y=False)

    # 價格 (右軸)
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Price'], name="收盤價", 
        line=dict(color='#ff7f0e', width=2),
        opacity=0.4
    ), secondary_y=True)

    # 背景色塊
    fig_main.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.1, layer="below", secondary_y=False)
    fig_main.add_hrect(y0=sigma_neg_2, y1=min_gap_display, fillcolor="#e74c3c", opacity=0.1, layer="below", secondary_y=False)

    fig_main.update_layout(
        title=f"{selected_option} 全歷史走勢",
        height=550, hovermode="x unified", template="plotly_white",
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
    )
    fig_main.update_yaxes(title_text="指標強度 %", tickformat=".0%", secondary_y=False)
    fig_main.update_yaxes(title_text="價格", secondary_y=True)
    
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 6. 底部價格參考點
    # ===============================================================
    st.divider()
    current_sma = df_clean['SMA'].iloc[-1]
    p_dca = current_sma * (1 + sigma_neg_1)
    p_bot = current_sma * (1 + sigma_neg_2)
    
    k1, k2, k3 = st.columns(3)
    k1.metric("當前收盤價", f"{df_clean['Price'].iloc[-1]:.2f}")
    k2.metric("🟢 定投啟動價 (-1σ)", f"{p_dca:.2f}")
    k3.metric("🔴 破盤抄底價 (-2σ)", f"{p_bot:.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
