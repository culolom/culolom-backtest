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
    st.info("💡 設計理念：結合 SMA 乖離 K 線與波動率分析，確認當前市場處於何種震盪位階。")

st.title("🚀 50正2年度乖離 K 線與波動雷達")

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
        selected_option = st.selectbox("🎯 選擇標的 (自動計算全歷史數據)", available_options)
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

    # 計算 SMA 與 乖離率 (Gap)
    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    
    # 計算波動率相關數據
    df['Returns'] = df['Price'].pct_change()
    if 'High' in df.columns and 'Low' in df.columns:
        df['Daily_Swing'] = (df['High'] - df['Low']) / df['Low']
    else:
        df['Daily_Swing'] = df['Returns'].abs() # 若無高低價，以絕對報酬率替代
        
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()
    df_clean['Year'] = df_clean.index.year

    # ===============================================================
    # 4. 圖表一：年度乖離 K 線 (開盤/收盤/最高/最低/平均)
    # ===============================================================
    st.subheader(f"📅 年度 {sma_window}SMA 乖離 K 線")
    
    stats_k = df_clean.groupby('Year').agg({
        'Gap': ['max', 'min', 'first', 'last', 'mean'],
        'Price': ['first', 'last']
    })
    stats_k.columns = ['max_gap', 'min_gap', 'open_gap', 'close_gap', 'avg_gap', 'open_price', 'close_price']
    stats_k['is_up'] = stats_k['close_price'] > stats_k['open_price']
    
    fig_k = go.Figure()

    for year, row in stats_k.iterrows():
        color = "#e74c3c" if row['is_up'] else "#2ecc71"
        
        # 影線 (年度乖離 Max/Min)
        fig_k.add_trace(go.Scatter(
            x=[year, year], y=[row['min_gap'], row['max_gap']],
            mode='lines', line=dict(color=color, width=1.5),
            showlegend=False, hoverinfo='skip'
        ))
        
        # 實體 (年初乖離 -> 年底乖離)
        fig_k.add_trace(go.Scatter(
            x=[year], y=[(row['open_gap'] + row['close_gap'])/2],
            mode='markers',
            marker=dict(symbol='square', size=22, color=color),
            customdata=[[row['open_gap'], row['close_gap'], row['max_gap'], row['min_gap'], row['avg_gap']]],
            hovertemplate=(
                "<b>年份: %{x}</b><br>" +
                "年初乖離: %{customdata[0]:.2%}<br>" +
                "年底乖離: %{customdata[1]:.2%}<br>" +
                "最高乖離: %{customdata[2]:.2%}<br>" +
                "最低乖離: %{customdata[3]:.2%}<br>" +
                "年度平均: %{customdata[4]:.2%}<br>" +
                "<extra></extra>"
            ),
            showlegend=False
        ))

        # 年度平均點 (白點)
        fig_k.add_trace(go.Scatter(
            x=[year], y=[row['avg_gap']],
            mode='markers',
            marker=dict(color='white', size=6, line=dict(color='black', width=1)),
            name='年度平均乖離', showlegend=False, hoverinfo='skip'
        ))

    fig_k.update_layout(
        height=450, template="plotly_white",
        xaxis=dict(title="年份", dtick=1, gridcolor='whitesmoke'),
        yaxis=dict(title="乖離率 %", tickformat=".0%", gridcolor='whitesmoke'),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_k, use_container_width=True)

    # ===============================================================
    # 5. 圖表二：年度波動分析 (確認波動大小)
    # ===============================================================
    st.divider()
    st.subheader("📊 年度波動深度分析 (確認波動大小)")
    
    # 計算年化波動率與日均震幅
    vol_stats = df_clean.groupby('Year').agg({
        'Returns': lambda x: x.std() * np.sqrt(252),
        'Daily_Swing': 'mean'
    })
    vol_stats.columns = ['annual_vol', 'avg_swing']
    
    fig_vol = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 年化波動率 (柱狀圖 - 專業穩定度指標)
    fig_vol.add_trace(go.Bar(
        x=vol_stats.index, y=vol_stats['annual_vol'],
        name='年化波動率 (頻率與幅度)',
        marker_color='rgba(41, 128, 185, 0.6)',
        hovertemplate="年度年化波動率: %{y:.2%}<extra></extra>"
    ), secondary_y=False)
    
    # 平均日震幅 (折線圖 - 盤中體感指標)
    fig_vol.add_trace(go.Scatter(
        x=vol_stats.index, y=vol_stats['avg_swing'],
        name='平均日均震幅 (體感)',
        line=dict(color='#e67e22', width=3),
        mode='lines+markers',
        hovertemplate="年度平均日震幅: %{y:.2%}<extra></extra>"
    ), secondary_y=True)
    
    fig_vol.update_layout(
        height=400, template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="年化波動率", tickformat=".0%"),
        yaxis2=dict(title="日均震幅", tickformat=".0%", showgrid=False)
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    # ===============================================================
    # 6. 全歷史指標走勢
    # ===============================================================
    st.divider()
    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    sigma_neg_1, sigma_neg_2 = gap_mean - gap_std, gap_mean - 2 * gap_std
    min_gap_display = min(df_clean['Gap'].min(), sigma_neg_2) * 1.2

    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", line=dict(color='#2980b9', width=1.5)), secondary_y=False)
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Price'], name="收盤價", line=dict(color='#ff7f0e', width=1.5), opacity=0.3), secondary_y=True)

    fig_main.add_hrect(y0=sigma_neg_1, y1=sigma_neg_2, fillcolor="#2ecc71", opacity=0.1, layer="below", secondary_y=False)
    fig_main.add_hrect(y0=sigma_neg_2, y1=min_gap_display, fillcolor="#e74c3c", opacity=0.1, layer="below", secondary_y=False)

    fig_main.update_layout(title=f"{selected_option} 歷史乖離區間", height=500, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 7. 價格參考點
    # ===============================================================
    st.divider()
    current_sma = df_clean['SMA'].iloc[-1]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("當前收盤價", f"{df_clean['Price'].iloc[-1]:.2f}")
    k2.metric(f"當前 {sma_window}SMA", f"{current_sma:.2f}")
    k3.metric("🟢 定投啟動價 (-1σ)", f"{current_sma * (1 + sigma_neg_1):.2f}")
    k4.metric("🔴 破盤抄底價 (-2σ)", f"{current_sma * (1 + sigma_neg_2):.2f}")

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
