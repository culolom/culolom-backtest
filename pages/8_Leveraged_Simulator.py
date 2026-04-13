import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 頁面配置 ---
st.set_page_config(page_title="配置比較戰情室 - 倉鼠量化實驗室", layout="wide")

st.markdown("""
    <style>
    div.stButton > button { width: 100%; height: 3em; font-size: 1.2em; font-weight: bold; border-radius: 10px; }
    .mdd-card {
        border-radius: 10px; padding: 15px; margin-top: 10px; border: 1px solid #30363d;
        background-color: rgba(151, 166, 195, 0.05); text-align: center;
    }
    .mdd-value { font-size: 1.8em; font-weight: bold; margin: 5px 0; }
    .mdd-label { color: #8b949e; font-size: 0.8em; }
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
st.title("🐹 極端行情：配置策略大洗牌")
st.subheader("📌 選擇歷史情境")
col_btn1, col_btn2 = st.columns(2)

if 'start_date' not in st.session_state:
    st.session_state.start_date = datetime(2007, 7, 1)
    st.session_state.end_date = datetime(2009, 7, 1)
    st.session_state.scenario_name = "2008 金融海嘯"

with col_btn1:
    if st.button("📉 2000年 網路泡沫"):
        st.session_state.start_date = datetime(2000, 1, 1)
        st.session_state.end_date = datetime(2002, 1, 1)
        st.session_state.scenario_name = "2000 網路泡沫"
with col_btn2:
    if st.button("🌊 2008 金融海嘯"):
        st.session_state.start_date = datetime(2007, 7, 1)
        st.session_state.end_date = datetime(2009, 7, 1)
        st.session_state.scenario_name = "2008 金融海嘯"

# --- 4. 防禦功能開關 ---
st.divider()
use_sma_defense = st.checkbox("🛡️ 啟動 200SMA 趨勢防禦 (破線時所有部位轉現金)", value=False)

# 寫死參數
target_symbol = "^TWII"
annual_fee = 0.015 

# --- 5. 資料抓取 ---
@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    fetch_start = start - timedelta(days=400)
    try:
        df = yf.download(symbol, start=fetch_start, end=end, progress=False)
        if df.empty: return None
        df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
        df = df[[symbol]] if symbol in df.columns else df.iloc[:, [0]]
        df.columns = ['Price']
        return df
    except: return None

raw_df = get_backtest_data(target_symbol, st.session_state.start_date, st.session_state.end_date)

if raw_df is not None and len(raw_df) > 0:
    # A. 計算指標與裁切
    raw_df['SMA200'] = raw_df['Price'].rolling(window=200).mean()
    df = raw_df[raw_df.index >= pd.to_datetime(st.session_state.start_date)].copy()
    
    # B. 計算基礎報酬
    df['Ret_1x'] = df['Price'].pct_change().fillna(0)
    df['Ret_2x'] = df['Ret_1x'] * 2 - (annual_fee / 252)
    
    # C. 防禦訊號
    df['Signal'] = (df['Price'] > df['SMA200']).shift(1).fillna(False) if use_sma_defense else True

    # D. 計算三種策略的每日報酬 (核心邏輯：含現金分配)
    # 1. 100% 正2
    df['Strat_100_Ret'] = np.where(df['Signal'], df['Ret_2x'], 0.0)
    # 2. 5050 策略 (50% 正2 + 50% 現金)
    df['Strat_5050_Ret'] = np.where(df['Signal'], df['Ret_2x'] * 0.5, 0.0)
    # 3. 433 策略 (40% 原型 + 30% 正2 + 30% 現金)
    df['Strat_433_Ret'] = np.where(df['Signal'], df['Ret_1x'] * 0.4 + df['Ret_2x'] * 0.3, 0.0)

    # E. 計算累積淨值
    df['V_100'] = (1 + df['Strat_100_Ret']).cumprod() * 100
    df['V_5050'] = (1 + df['Strat_5050_Ret']).cumprod() * 100
    df['V_433'] = (1 + df['Strat_433_Ret']).cumprod() * 100
    
    # F. 計算回撤 (Drawdown)
    df['DD_100'] = (df['V_100'] - df['V_100'].cummax()) / df['V_100'].cummax()
    df['DD_5050'] = (df['V_5050'] - df['V_5050'].cummax()) / df['V_5050'].cummax()
    df['DD_433'] = (df['V_433'] - df['V_433'].cummax()) / df['V_433'].cummax()

    # --- 6. 指標面板 ---
    st.subheader(f"📊 {st.session_state.scenario_name}：策略終點價值")
    m1, m2, m3 = st.columns(3)
    m1.metric("100% 正2 最終價值", f"{df['V_100'].iloc[-1]:.1f} 萬")
    m2.metric("5050 策略 最終價值", f"{df['V_5050'].iloc[-1]:.1f} 萬")
    m3.metric("433 策略 最終價值", f"{df['V_433'].iloc[-1]:.1f} 萬")

    # --- 7. 走勢比較圖 (核心需求) ---
    st.subheader("📈 總資產走勢比較 (含現金部位計算)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['V_100'], name='100% 正2', line=dict(color='#FF4B4B', width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_5050'], name='5050策略 (50%現金)', line=dict(color='#00D1B2', width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_433'], name='433策略 (30%現金)', line=dict(color='#1C83E1', width=2)))
    fig.update_layout(hovermode="x unified", height=450, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 8. 回撤比較圖 (體現風險分散) ---
    st.subheader("📉 總資產回撤比較 (MDD)")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_100'], name='100% 正2 回撤', fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.2)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_5050'], name='5050 回撤', fill='tozeroy', line=dict(color='rgba(0, 209, 178, 0.4)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_433'], name='433 回撤', fill='tozeroy', line=dict(color='rgba(28, 131, 225, 0.2)')))
    fig_dd.update_layout(hovermode="x unified", height=300, yaxis_tickformat=".1%")
    st.plotly_chart(fig_dd, use_container_width=True)

    # --- 9. MDD 比較卡片 ---
    st.subheader("🛡️ 風控數據對比")
    c1, c2, c3 = st.columns(3)
    def mdd_card(title, val, color):
        st.markdown(f"""<div class="mdd-card" style="border-color: {color};">
            <div class="mdd-label">{title}</div>
            <div class="mdd-value" style="color: {color};">{val*100:.2f}%</div>
        </div>""", unsafe_allow_html=True)
    
    with c1: mdd_card("100% 正2 最大回撤", df['DD_100'].min(), "#FF4B4B")
    with c2: mdd_card("5050 策略 最大回撤", df['DD_5050'].min(), "#00D1B2")
    with c3: mdd_card("433 策略 最大回撤", df['DD_433'].min(), "#1C83E1")

    # --- 10. 專業說明 ---
    st.divider()
    st.markdown(f"""
    ### 💡 為什麼資產配置能有效降低回撤？
    1. **現金的緩衝作用**：如圖所示，當 100% 正2 在 {st.session_state.scenario_name} 崩盤時，持有 50% 現金的 **5050 策略** 因為只有一半部位在市場曝險，總資產回撤會直接「減半」。
    2. **再平衡效應**：本模擬隱含了每日再平衡，這意味著當下跌時，系統會自動賣出部分現金補入部位；上漲時則賣出部位鎖定獲利到現金。這在極端波動中提供了極佳的穩定性。
    3. **防禦機制的加成**：若啟動 **200SMA 防禦**，你會發現曲線在破線後會變為「水平線」，這代表此時資產完全轉為現金，徹底躲過後續的毀滅性大跌。
    """)

else:
    st.warning("⚠️ 無法獲取該時段資料，請檢查代碼或網路。")
