import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 頁面配置 ---
st.set_page_config(page_title="正2歷史模擬 - 倉鼠量化戰情室", layout="wide")

st.markdown("""
    <style>
    div.stButton > button { width: 100%; height: 3em; font-size: 1.2em; font-weight: bold; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄導航 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

# --- 3. 頂部快速切換按鈕 ---
st.title("🐹 正2 歷史極端行情模擬器")
st.subheader("📌 選擇模擬情境")
col_btn1, col_btn2 = st.columns(2)

if 'start_date' not in st.session_state:
    st.session_state.start_date = datetime(2007, 7, 1)
    st.session_state.end_date = datetime(2009, 7, 1)
    st.session_state.scenario_name = "2008 金融海嘯"

with col_btn1:
    if st.button("📉 2000年 網路泡沫 (2000-2002)"):
        st.session_state.start_date = datetime(2000, 1, 1)
        st.session_state.end_date = datetime(2002, 1, 1)
        st.session_state.scenario_name = "2000 網路泡沫"

with col_btn2:
    if st.button("🌊 2008 金融海嘯 (2007-2009)"):
        st.session_state.start_date = datetime(2007, 7, 1)
        st.session_state.end_date = datetime(2009, 7, 1)
        st.session_state.scenario_name = "2008 金融海嘯"

# --- 4. 防禦功能開關 ---
st.divider()
col_ctrl1, col_ctrl2 = st.columns([1, 2])
with col_ctrl1:
    use_sma_defense = st.checkbox("🛡️ 啟動 200SMA 趨勢防禦", value=False)

# 寫死參數
target_symbol = "^TWII"
leverage = 2.0
annual_fee = 0.015 

st.info(f"當前情境：**{st.session_state.scenario_name}** | 參數：**{leverage}x / 1.5% 損耗**" + 
        (" | **已開啟 200SMA 防禦**" if use_sma_defense else " | **無腦持有模式**"))

# --- 5. 資料抓取 ---
@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    fetch_start = start - timedelta(days=400) # 多抓一點確保 SMA200 準確
    try:
        df = yf.download(symbol, start=fetch_start, end=end, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df['Close']
        else:
            df = df[['Close']]
        df = df[[symbol]] if symbol in df.columns else df.iloc[:, [0]]
        df.columns = ['Price']
        return df
    except: return None

raw_df = get_backtest_data(target_symbol, st.session_state.start_date, st.session_state.end_date)

if raw_df is not None and len(raw_df) > 0:
    # A. 計算 SMA
    raw_df['SMA200'] = raw_df['Price'].rolling(window=200).mean()
    
    # B. 裁切時段
    df = raw_df[raw_df.index >= pd.to_datetime(st.session_state.start_date)].copy()
    
    # C. 計算報酬 (這部分是程式邏輯)
    df['Daily_Ret'] = df['Price'].pct_change()
    daily_fee = annual_fee / 252
    
    if use_sma_defense:
        # 訊號：股價 > SMA 則參與槓桿
        df['Signal'] = (df['Price'] > df['SMA200']).shift(1).fillna(False)
        df['Strategy_Ret'] = np.where(df['Signal'], df['Daily_Ret'] * leverage - daily_fee, 0.0)
    else:
        df['Strategy_Ret'] = df['Daily_Ret'] * leverage - daily_fee

    # D. 計算累積淨值 (100 為基準)
    df['Index_Cum'] = (1 + df['Daily_Ret'].fillna(0)).cumprod() * 100
    df['Strategy_Cum'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() * 100
    
    # --- 重要：視覺化縮放修正 ---
    # 讓 SMA200 的畫線比例與 Index_Cum 一致
    scale_factor = 100 / df['Price'].iloc[0]
    df['SMA200_Scaled'] = df['SMA200'] * scale_factor

    # --- 6. 指標面板 ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("基準指數最終價值", f"{df['Index_Cum'].iloc[-1]:.1f} 萬")
    m2.metric("正2策略最終價值", f"{df['Strategy_Cum'].iloc[-1]:.1f} 萬")
    m3.metric("指數最大回撤", f"{((df['Index_Cum'] / df['Index_Cum'].cummax()) - 1).min()*100:.1f}%")
    m4.metric("策略最大回撤", f"{((df['Strategy_Cum'] / df['Strategy_Cum'].cummax()) - 1).min()*100:.1f}%", delta_color="inverse")

    # --- 7. 走勢圖表 ---
    st.subheader("📈 資產淨值走勢")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Index_Cum'], name='原始指數 (1x)', line=dict(color='rgba(150, 150, 150, 0.5)')))
    fig.add_trace(go.Scatter(x=df.index, y=df['Strategy_Cum'], name=f'模擬正2 (2x)', line=dict(color='#00D1B2', width=2.5)))
    
    # 畫出修正後的 SMA200
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA200_Scaled'], 
                             name='200SMA (同步縮放)', line=dict(dash='dot', color='rgba(255, 165, 0, 0.6)')))
    
    fig.update_layout(hovermode="x unified", height=450, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 8. MDD 表格 ---
    st.subheader("📊 最大回撤 (MDD) 深度分析")
    def get_mdd_stats(cum_series):
        dd = (cum_series - cum_series.cummax()) / cum_series.cummax()
        mdd_val = dd.min()
        valley_date = dd.idxmin()
        peak_date = cum_series[:valley_date].idxmax()
        return f"{mdd_val*100:.2f}%", str(peak_date.date()), str(valley_date.date()), (valley_date - peak_date).days

    idx_mdd = get_mdd_stats(df['Index_Cum'])
    str_mdd = get_mdd_stats(df['Strategy_Cum'])

    mdd_compare_data = {
        "分析指標": ["最大回撤 (MDD)", "起點 (歷史高點)", "終點 (最慘低點)", "回撤歷時 (天)"],
        "基準指數 (1x)": idx_mdd,
        f"模擬正2 ({leverage}x)": str_mdd
    }
    st.dataframe(pd.DataFrame(mdd_compare_data), use_container_width=True, hide_index=True)

    # --- 9. 說明說明 ---
    st.divider()
    st.info("💡 **小筆記：** 如果你發現 2000 年 4 月沒賣，是因為當時原始股價還在均線之上（1999 年漲太兇，均線追不上）。改用此版本後，圖表上的交叉點將與程式賣出時機完全同步。")

else:
    st.warning("⚠️ 無法獲取該時段資料。")
