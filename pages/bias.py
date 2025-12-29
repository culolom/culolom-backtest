###############################################################
# app.py — 50正2定投抄底雷達 (年度乖離 K 線版)
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
        st.subheader("📅 年度乖離波動 K 線 (乖離極限 + 年度漲跌)")
        
        # 準備年度資料
        yearly_df = df_clean.copy()
        yearly_df['Year'] = yearly_df.index.year
        
        # 聚合年度數據
        # High: 最大乖離, Low: 最低乖離, Open: 年初乖離, Close: 年底乖離
        # 並加入價格來判斷顏色
        stats_k = yearly_df.groupby('Year').agg({
            'Gap': ['max', 'min', 'first', 'last', 'mean'],
            'Price': ['first', 'last']
        })
        stats_k.columns = ['max_gap', 'min_gap', 'open_gap', 'close_gap', 'avg_gap', 'open_price', 'close_price']
        
        # 定義顏色：年度收盤價 > 開盤價 = 紅K (漲), 否則 綠K (跌)
        # 注意：台灣習慣 紅漲綠跌
        stats_k['is_up'] = stats_k['close_price'] > stats_k['open_price']
        
        fig_k = go.Figure()

        # 繪製年度乖離 K 棒
        # 使用 Candlestick，但 Y 軸放的是乖離率數據
        for year, row in stats_k.iterrows():
            color = "#e74c3c" if row['is_up'] else "#2ecc71"
            
            # 1. 繪製影線 (最大/最小乖離垂直線)
            fig_k.add_trace(go.Scatter(
                x=[year, year], y=[row['min_gap'], row['max_gap']],
                mode='lines',
                line=dict(color=color, width=2),
                showlegend=False,
                hoverinfo='skip'
            ))
            
            # 2. 繪製實體 (開盤乖離 vs 收盤乖離)
            # 為了讓 K 棒有寬度，使用 Bar 或自定義形狀，這裡用簡化的寬線表示實體
            fig_k.add_trace(go.Scatter(
                x=[year], y=[(row['open_gap'] + row['close_gap'])/2],
                mode='markers',
                marker=dict(
                    symbol='rect',
                    size=20, # 控制 K 棒寬度
                    color=color,
                    line=dict(width=0)
                ),
                name=f"{year} 趨勢",
                customdata=[[row['open_gap'], row['close_gap'], row['max_gap'], row['min_gap'], row['avg_gap']]],
                hovertemplate=(
                    "<b>年度: %{x}</b><br>" +
                    "年初乖離: %{customdata[0]:.2%}<br>" +
                    "年底乖離: %{customdata[1]:.2%}<br>" +
                    "最大乖離: %{customdata[2]:.2%}<br>" +
                    "最低乖離: %{customdata[3]:.2%}<br>" +
                    "平均乖離: %{customdata[4]:.2%}<br>" +
                    "<extra></extra>"
                ),
                showlegend=False
            ))

            # 3. 標註平均乖離點 (小點)
            fig_k.add_trace(go.Scatter(
                x=[year], y=[row['avg_gap']],
                mode='markers',
                marker=dict(color='white', size=4, line=dict(color='black', width=1)),
                name='年平均乖離',
                showlegend=False
            ))

        fig_k.update_layout(
            height=400,
            template="plotly_white",
            xaxis=dict(title="年份", dtick=1),
            yaxis=dict(title="乖離率趨勢 %", tickformat=".0%"),
            showlegend=False,
            margin=dict(l=10, r=10, t=30, b=10)
        )
        
        # 加入說明文字
        st.plotly_chart(fig_k, use_container_width=True)
        st.caption("💡 圖表說明：影線範圍為年度最大/最小乖離；K棒顏色由年度實體價格漲跌決定（紅漲綠跌）；白色小點為年平均乖離。")

    with col_stat2:
        st.subheader("📊 波動率統計")
        d_avg = df['Daily_Return'].mean()
        d_std = df['Daily_Return'].std()
        
        st.metric("平均日漲幅", f"{d_avg:.2%}")
        st.metric("日波動率 (Std)", f"{d_std:.2%}")
        
        # 顯示簡易表格輔助看精確數值
        st.write("年度極值摘要：")
        st.dataframe(stats_k[['max_gap', 'min_gap', 'avg_gap']].iloc[::-1].style.format("{:.2%}"), height=200)

    # ===============================================================
    # 5. 主圖表與參考價格 (保持原本邏輯)
    # ===============================================================
    st.divider()
    
    # 信心區間與主圖繪製... (此處省略部分重複代碼以節省空間，請沿用上一版本的繪圖邏輯)
    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    sigma_neg_1, sigma_neg_2 = gap_mean - gap_std, gap_mean - 2 * gap_std
    
    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Gap'], name="乖離率", line=dict(color='#2980b9', width=1.5)), secondary_y=False)
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Price'], name="股價", line=dict(color='#ff7f0e', width=2), opacity=0.4), secondary_y=True)
    
    # 背景色塊
    fig_main.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.1, layer="below", secondary_y=False)
    fig_main.add_hrect(y0=sigma_neg_2, y1=df_clean['Gap'].min()*1.2, fillcolor="#e74c3c", opacity=0.1, layer="below", secondary_y=False)

    fig_main.update_layout(height=500, hovermode="x unified", template="plotly_white")
    st.plotly_chart(fig_main, use_container_width=True)

    # 今日價格參考
    current_sma = df_clean['SMA'].iloc[-1]
    k1, k2, k3 = st.columns(3)
    k1.metric("當前價格", f"{df_clean['Price'].iloc[-1]:.2f}")
    k2.metric("🟢 定投啟動價", f"{current_sma * (1 + sigma_neg_1):.2f}")
    k3.metric("🔴 破盤抄底價", f"{current_sma * (1 + sigma_neg_2):.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
