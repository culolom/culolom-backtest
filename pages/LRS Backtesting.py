import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import os
import sys

# --- 1. 頁面配置 ---
st.set_page_config(
    page_title="多策略戰情室 - 倉鼠量化實驗室", 
    page_icon="🦅",
    layout="wide"
)

# 🔒 驗證守門員 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass

# --- 2. CSS 樣式設定 ---
st.markdown("""
    <style>
    div.stButton > button { width: 100%; height: 3em; font-size: 1.2em; font-weight: bold; border-radius: 10px; background-color: #FF6F00; color: white; border: none; }
    .mdd-card {
        border-radius: 10px; padding: 15px; margin-top: 10px; border: 1px solid #30363d;
        background-color: rgba(151, 166, 195, 0.05); text-align: center;
        min-height: 160px;
    }
    .mdd-value { font-size: 1.6em; font-weight: bold; margin: 2px 0; }
    .ret-value { font-size: 1.2em; font-weight: bold; margin: 2px 0; }
    .mdd-label { color: #8b949e; font-size: 0.75em; line-height: 1.2; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 側邊欄導航 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

# --- 4. 頂部快速切換按鈕 ---
st.title("🐹 歷史極端行情模擬器")
st.caption("本系統模擬歷史極端行情，體現在崩盤下的最大回撤 (MDD) 與策略抗壓性。")

col_btn1, col_btn2, col_btn3 = st.columns(3)

if 'start_date' not in st.session_state:
    st.session_state.start_date = datetime(2007, 7, 1)
    st.session_state.end_date = datetime(2009, 7, 1)
    st.session_state.scenario_name = "2008 金融海嘯"

with col_btn1:
    if st.button("📉 2000年 網路泡沫"):
        st.session_state.start_date = datetime(2000, 1, 1)
        st.session_state.end_date = datetime(2002, 12, 31)
        st.session_state.scenario_name = "2000 網路泡沫"
with col_btn2:
    if st.button("🌊 2008 金融海嘯"):
        st.session_state.start_date = datetime(2007, 7, 1)
        st.session_state.end_date = datetime(2009, 7, 1)
        st.session_state.scenario_name = "2008 金融海嘯"
with col_btn3:
    if st.button("🛡️ 2025 關稅股災"):
        st.session_state.start_date = datetime(2025, 1, 1)
        st.session_state.end_date = datetime(2025, 10, 31)
        st.session_state.scenario_name = "2025 對等關稅股災"

# --- 5. 資料抓取與計算 ---
st.divider()
enable_lrs = st.toggle("🚀 啟用 LRS 趨勢策略對比 (100% 正2 + 200SMA 擇時)", value=True)

target_symbol = "^TWII" 
annual_fee = 0.015      

@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    fetch_start = start - timedelta(days=400)
    df = yf.download(symbol, start=fetch_start, end=end, progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex): df = df['Close']
    else: df = df[['Close']]
    df.columns = ['Price']
    return df

raw_df = get_backtest_data(target_symbol, st.session_state.start_date, st.session_state.end_date)

if raw_df is not None:
    # 指標計算
    raw_df['SMA200'] = raw_df['Price'].rolling(window=200).mean()
    df = raw_df[raw_df.index >= pd.to_datetime(st.session_state.start_date)].copy()
    
    df['Ret_1x'] = df['Price'].pct_change().fillna(0)
    df['Ret_2x'] = df['Ret_1x'] * 2 - (annual_fee / 252)
    df['Signal'] = (df['Price'] > df['SMA200']).shift(1).fillna(False)

    # 策略淨值
    df['V_Bench'] = (1 + df['Ret_1x']).cumprod() * 100
    df['V_100'] = (1 + df['Ret_2x']).cumprod() * 100
    df['V_LRS'] = (1 + np.where(df['Signal'], df['Ret_2x'], 0.0)).cumprod() * 100
    
    # --- [核心修改：連漲連跌統計] ---
    def get_streak_stats(data):
        is_up = data['Ret_1x'] > 0
        is_down = data['Ret_1x'] < 0
        # 計算連漲天數
        up_streak = is_up * (is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1)
        # 計算連跌天數
        down_streak = is_down * (is_down.groupby((is_down != is_down.shift()).cumsum()).cumcount() + 1)
        
        total = len(data)
        stats = []
        for s in [2, 3, 4, 5]:
            stats.append({"Streak": f"{s}天+", "Prob": (up_streak >= s).sum() / total, "Type": "連漲機率"})
            stats.append({"Streak": f"{s}天+", "Prob": (down_streak >= s).sum() / total, "Type": "連跌機率"})
        return pd.DataFrame(stats)

    df_above = df[df['Price'] > df['SMA200']]
    df_below = df[df['Price'] <= df['SMA200']]

    # --- 走勢圖與回撤圖 (略過，維持原樣) ---
    st.subheader(f"📈 {st.session_state.scenario_name}：總資產走勢大對決")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['V_Bench'], name='原型指數 (1x)', line=dict(color='#8b949e', dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_100'], name='全倉正2', line=dict(color='#FF4B4B', width=1.5)))
    if enable_lrs:
        fig.add_trace(go.Scatter(x=df.index, y=df['V_LRS'], name='LRS 擇時 (2x+SMA)', line=dict(color='#FFA500', width=3)))
    st.plotly_chart(fig, use_container_width=True)

    # --- 💡 新增：Regime Momentum Matrix (環境動能矩陣) ---
    st.divider()
    st.subheader("🔥 Regime Momentum Matrix：均線如何改變漲跌慣性")
    st.caption("觀察重點：在均線之下，『連跌』的機率是否顯著飆升？這正是避開正二的科學原因。")
    
    m_col1, m_col2 = st.columns(2)
    
    with m_col1:
        st.markdown("#### 🟢 均線之上 (多頭環境)")
        if not df_above.empty:
            streak_above = get_streak_stats(df_above)
            fig_above = px.bar(streak_above, x="Streak", y="Prob", color="Type", barmode="group",
                               color_discrete_map={"連漲機率": "#6699CC", "連跌機率": "#EE7733"},
                               text_auto='.1%')
            fig_above.update_layout(yaxis_tickformat='.0%', height=350, margin=dict(t=30))
            st.plotly_chart(fig_above, use_container_width=True)
        else: st.info("此區間無均線之上數據")

    with m_col2:
        st.markdown("#### 🔴 均線之下 (空頭環境)")
        if not df_below.empty:
            streak_below = get_streak_stats(df_below)
            fig_below = px.bar(streak_below, x="Streak", y="Prob", color="Type", barmode="group",
                               color_discrete_map={"連漲機率": "#6699CC", "連跌機率": "#EE7733"},
                               text_auto='.1%')
            fig_below.update_layout(yaxis_tickformat='.0%', height=350, margin=dict(t=30))
            st.plotly_chart(fig_below, use_container_width=True)
        else: st.info("此區間無均線之下數據")

    # --- 10. 風控卡片 (維持原樣) ---
    # ... 原有代碼 ...
