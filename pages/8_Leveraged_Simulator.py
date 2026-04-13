import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 頁面配置 ---
st.set_page_config(page_title="多策略戰情室 - 倉鼠量化實驗室", layout="wide")

st.markdown("""
    <style>
    div.stButton > button { width: 100%; height: 3em; font-size: 1.2em; font-weight: bold; border-radius: 10px; }
    .mdd-card {
        border-radius: 10px; padding: 15px; margin-top: 10px; border: 1px solid #30363d;
        background-color: rgba(151, 166, 195, 0.05); text-align: center;
        min-height: 160px; /* 增加高度以容納總報酬 */
    }
    .mdd-value { font-size: 1.6em; font-weight: bold; margin: 2px 0; }
    .ret-value { font-size: 1.2em; font-weight: bold; margin: 2px 0; }
    .mdd-label { color: #8b949e; font-size: 0.75em; line-height: 1.2; font-weight: bold; }
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
st.title("🐹 歷史極端行情模擬器")
st.caption("本模擬歷史極端行情，體現在崩盤下的最大回撤。")

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

# --- 4. 功能開關 ---
st.divider()
enable_lrs = st.toggle("🚀 啟用 LRS 趨勢策略對比 (100% 正2 + 200SMA 擇時)", value=False)

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
    # A. 指標計算
    raw_df['SMA200'] = raw_df['Price'].rolling(window=200).mean()
    df = raw_df[raw_df.index >= pd.to_datetime(st.session_state.start_date)].copy()
    
    # B. 基礎報酬
    df['Ret_1x'] = df['Price'].pct_change().fillna(0)
    df['Ret_2x'] = df['Ret_1x'] * 2 - (annual_fee / 252)
    
    # C. 擇時訊號 (LRS 專用)
    df['Signal'] = (df['Price'] > df['SMA200']).shift(1).fillna(False)

    # D. 計算累積倍數
    comp_1x = (1 + df['Ret_1x']).cumprod()
    comp_2x = (1 + df['Ret_2x']).cumprod()
    comp_lrs = (1 + np.where(df['Signal'], df['Ret_2x'], 0.0)).cumprod()
    comp_cash = 1.0

    # E. 總資產計算 (初始 100 萬)
    df['V_Bench'] = comp_1x * 100
    df['V_100'] = comp_2x * 100
    df['V_5050'] = (comp_2x * 0.5 + comp_cash * 0.5) * 100
    df['V_433'] = (comp_1x * 0.4 + comp_2x * 0.3 + comp_cash * 0.3) * 100
    df['V_LRS'] = comp_lrs * 100
    
    # F. 回撤與總報酬計算
    results = {}
    for key, col in [('Bench', 'V_Bench'), ('100', 'V_100'), ('5050', 'V_5050'), ('433', 'V_433'), ('LRS', 'V_LRS')]:
        # MDD
        df[f'DD_{key}'] = (df[col] - df[col].cummax()) / df[col].cummax()
        # 總報酬 = (最終價值 / 初始價值) - 1
        results[f'Ret_{key}'] = (df[col].iloc[-1] / 100) - 1
        results[f'MDD_{key}'] = df[f'DD_{key}'].min()

    # G. 視覺化縮放
    scale_factor = 100 / df['Price'].iloc[0]
    df['SMA200_Scaled'] = df['SMA200'] * scale_factor

    # --- 6. 指標面板 ---
    st.subheader(f"📊 {st.session_state.scenario_name}：初始投入100萬最終價值比較")
    cols = st.columns(5 if enable_lrs else 4)
    cols[0].metric("原型 (1x)", f"{df['V_Bench'].iloc[-1]:.1f} 萬")
    cols[1].metric("全倉正2", f"{df['V_100'].iloc[-1]:.1f} 萬")
    if enable_lrs:
        cols[2].metric("LRS 擇時", f"{df['V_LRS'].iloc[-1]:.1f} 萬")
        cols[3].metric("5050 配置", f"{df['V_5050'].iloc[-1]:.1f} 萬")
        cols[4].metric("433 配置", f"{df['V_433'].iloc[-1]:.1f} 萬")
    else:
        cols[2].metric("5050 配置", f"{df['V_5050'].iloc[-1]:.1f} 萬")
        cols[3].metric("433 配置", f"{df['V_433'].iloc[-1]:.1f} 萬")

    # --- 7. 走勢比較圖 ---
    st.subheader("📈 總資產走勢大對決")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['V_Bench'], name='原型指數 (1x)', line=dict(color='#8b949e', dash='dash')))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_100'], name='全倉正2', line=dict(color='#FF4B4B', width=1.5)))
    
    if enable_lrs:
        fig.add_trace(go.Scatter(x=df.index, y=df['V_LRS'], name='LRS 擇時 (2x+SMA)', line=dict(color='#FFA500', width=3)))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA200_Scaled'], name='200SMA (防禦線)', line=dict(dash='dot', color='rgba(255, 165, 0, 0.4)')))
        
    fig.add_trace(go.Scatter(x=df.index, y=df['V_5050'], name='5050 配置', line=dict(color='#00D1B2', width=2.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df['V_433'], name='433 配置', line=dict(color='#1C83E1', width=2)))
    
    fig.update_layout(hovermode="x unified", height=500, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 8. 回撤比較圖 ---
    st.subheader("📉 總資產回撤比較 (MDD)")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_Bench'], name='原型回撤', fill='tozeroy', line=dict(color='rgba(139, 148, 158, 0.2)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_100'], name='全倉正2回撤', fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.2)')))
    if enable_lrs:
        fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_LRS'], name='LRS 擇時回撤', fill='tozeroy', line=dict(color='rgba(255, 165, 0, 0.4)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['DD_5050'], name='5050 回撤', fill='tozeroy', line=dict(color='rgba(0, 209, 178, 0.4)')))
    fig_dd.update_layout(hovermode="x unified", height=300, yaxis_tickformat=".1%")
    st.plotly_chart(fig_dd, use_container_width=True)

    # --- 9. 風控卡片 (含總報酬) ---
    st.subheader("🛡️ 策略風險與收益數據對比")
    card_cols = st.columns(5 if enable_lrs else 4)
    
    def mdd_card(col_obj, title, mdd, ret, color):
        # 報酬顏色判斷
        ret_color = "#FF4B4B" if ret < 0 else "#00D1B2"
        col_obj.markdown(f"""<div class="mdd-card" style="border-color: {color};">
            <div class="mdd-label" style="color: {color}; text-transform: uppercase;">{title}</div>
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.1);">
            <div class="mdd-label">最大回撤 (MDD)</div>
            <div class="mdd-value" style="color: {color};">{mdd*100:.2f}%</div>
            <div class="mdd-label" style="margin-top:10px;">總報酬率</div>
            <div class="ret-value" style="color: {ret_color};">{ret*100:.2f}%</div>
        </div>""", unsafe_allow_html=True)
    
    mdd_card(card_cols[0], "原型 (1x)", results['MDD_Bench'], results['Ret_Bench'], "#8b949e")
    mdd_card(card_cols[1], "全倉正2", results['MDD_100'], results['Ret_100'], "#FF4B4B")
    if enable_lrs:
        mdd_card(card_cols[2], "LRS 擇時", results['MDD_LRS'], results['Ret_LRS'], "#FFA500")
        mdd_card(card_cols[3], "5050 配置", results['MDD_5050'], results['Ret_5050'], "#00D1B2")
        mdd_card(card_cols[4], "433 配置", results['MDD_433'], results['Ret_433'], "#1C83E1")
    else:
        mdd_card(card_cols[2], "5050 配置", results['MDD_5050'], results['Ret_5050'], "#00D1B2")
        mdd_card(card_cols[3], "433 配置", results['MDD_433'], results['Ret_433'], "#1C83E1")

    # --- 10. 專業說明 ---
    st.divider()
    st.subheader("💡 策略定義與 1.5% 損耗說明")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown(f"""
        **各項策略定義 (100萬初始配置)：**
        * **100% 正2**：100萬全數投入 2x 槓桿標的。
        * **5050 策略**：50萬 2x 槓桿標的 + 50萬 現金。
        * **433 策略**：40萬 原型標的(1x) + 30萬 2x 槓桿標的 + 30萬 現金。
        
        **關於 1.5% 年度費用計算：**
        * **精確扣費**：1.5% 的損耗(經理費、轉倉損耗)僅作用於「槓桿部位」。
        * **實質影響**：例如 5050 策略，每年的實質費用損耗僅為 **0.75%**。
        """)
    with col_info2:
        st.markdown(f"""
        **數據觀察重點：**
        * **風控效率**：注意 **5050 策略** 在崩盤時的 MDD 通常僅為 **全倉正2** 的一半，這就是「現金防火牆」的效果。
        * **LRS 的優勢**：在極端多頭轉空頭的年份，LRS 能透過避開主跌段，在維持高報酬的同時大幅降低 MDD。
        * **心理安全感**：配置策略的核心不在於「賺最多」，而在於讓你在 MDD 發生時還能睡得著覺，從而拿得住部位。
        """)

else:
    st.warning("⚠️ 無法獲取該時段資料，請檢查網路連接。")
