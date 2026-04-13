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
st.title("🐹 極端行情：四種配置大對決")
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
use_sma_defense = st.checkbox("🛡️ 啟動 200SMA 趨勢防禦 (開啟後原型與正2均受防禦保護)", value=False)

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

    # D. 計算四種策略的每日報酬
    # 1. 原型指數 (100% 1x) - 如果開啟防禦，原型也會退場
    df['Strat_Bench_Ret'] = np.where(df['Signal'], df['Ret_1x'], 0.0)
    # 2. 100% 正2
    df['Strat_100_Ret'] = np.where(df['Signal'], df['Ret_2x'], 0.0)
    # 3. 5050 策略 (50% 正2 + 50% 現金)
    df['Strat_5050_Ret'] = np.where(df['Signal'], df['Ret_2x'] * 0.5, 0.0)
    # 4. 433 策略 (40% 原型 + 30% 正2 + 30% 現金)
    df['Strat_433_Ret'] = np.where(df['Signal'], df['Ret_1x'] * 0.4 + df['Ret_2x'] * 0.3, 0.0)

    # E. 計算累積淨值
    df['V_Bench'] = (1 + df['Strat_Bench_Ret']).cumprod() * 100
    df['V_100'] = (1 + df['Strat_100_Ret']).cumprod() * 100
    df['V_5050'] = (1 + df['Strat_5050_Ret']).cumprod() * 100
    df['V_433'] = (1 + df['Strat_433_Ret']).cumprod() * 100
    
    # F. 計算回撤
    df['DD_Bench'] = (df['V_Bench'] - df['V_Bench'].cummax()) / df['V_Bench'].cummax()
    df['DD_100'] = (df['V_100'] - df['V_100'].cummax()) / df['V_100'].cummax()
    df['DD_5050'] = (df['V_5050'] - df['V_5050'].cummax()) / df['V_5050'].cummax()
    df['DD_433'] = (df['V_433'] - df['V_433'].cummax()) / df['V_433'].cummax()

    # --- 6. 指標面板 ---
    st.subheader(f"📊 {st.session_state.scenario_name}：終點價值比較")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("原型指數 (1x)", f"{df['V_Bench'].iloc[-1]:.1f} 萬")
    m2.metric("100% 正2", f"{df['V_100'].iloc[-1]:.1f} 萬")
    m3.metric("5050 策略", f"{df['V_5050'].iloc[-1]:.1f} 萬")
    m4.metric("433 策略", f"{df['V_433'].iloc[-1]:.1f} 萬")

    # --- 7. 走勢比較圖 ---
    st.subheader("📈 總資產走勢比較")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['V_Bench'], name='原型指數 (1x)', line=dict(color='#8b949e', dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_100'], name='100% 正2', line=dict(color='#FF4B4B', width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_5050'], name='5050 策略', line=dict(color='#00D1B2', width=3)))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_433'], name='433 策略', line=dict(color='#1C83E1', width=2)))
    fig.update_layout(hovermode="x unified", height=450, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 8. 回撤比較圖 ---
    st.subheader("📉 總資產回撤比較 (MDD)")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_Bench'], name='原型 (1x) 回撤', fill='tozeroy', line=dict(color='rgba(139, 148, 158, 0.2)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_100'], name='100% 正2 回撤', fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.2)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_5050'], name='5050 回撤', fill='tozeroy', line=dict(color='rgba(0, 209, 178, 0.4)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_433'], name='433 回撤', fill='tozeroy', line=dict(color='rgba(28, 131, 225, 0.2)')))
    fig_dd.update_layout(hovermode="x unified", height=300, yaxis_tickformat=".1%")
    st.plotly_chart(fig_dd, use_container_width=True)

    # --- 9. MDD 比較卡片 ---
    st.subheader("🛡️ 風控數據對比")
    c1, c2, c3, c4 = st.columns(4)
    def mdd_card(title, val, color):
        st.markdown(f"""<div class="mdd-card" style="border-color: {color};">
            <div class="mdd-label">{title}</div>
            <div class="mdd-value" style="color: {color};">{val*100:.2f}%</div>
        </div>""", unsafe_allow_html=True)
    
    with c1: mdd_card("原型 (1x) 回撤", df['DD_Bench'].min(), "#8b949e")
    with c2: mdd_card("100% 正2 回撤", df['DD_100'].min(), "#FF4B4B")
    with c3: mdd_card("5050 策略 回撤", df['DD_5050'].min(), "#00D1B2")
    with c4: mdd_card("433 策略 回撤", df['DD_433'].min(), "#1C83E1")

    # --- 10. 專業說明 ---
    st.divider()
    st.markdown(f"""
    ### 💡 配置心得：原型 vs 策略
    1. **原型與策略的差異**：透過 **原型 (1x)** 的加入，你可以明顯看到 2008 年大盤跌 50% 時，**5050 策略** 憑藉 50% 現金，竟然能把回撤控制得比「全倉原型指數」還要好。
    2. **5050 的優勢**：在極端行情中，50% 正2 + 50% 現金的組合，其波動度與原型相似，但因為槓桿複利的特性，在反彈時的爆發力通常優於原型。
    3. **防禦機制的加成**：若開啟防禦，四種路徑都會在破線時轉為平線（現金），這能保護你在海嘯最深處不被洗出場。
    """)

else:
    st.warning("⚠️ 無法獲取該時段資料，請檢查代碼或網路。")
