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

# 參數寫死
target_symbol = "^TWII"
leverage = 2.0
annual_fee = 0.015 

st.info(f"當前情境：**{st.session_state.scenario_name}** | 參數：**{leverage}x / 1.5% 損耗**" + 
        (" | **已開啟 200SMA 防禦**" if use_sma_defense else " | **無腦持有模式**"))

# --- 5. 資料抓取 ---
@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    fetch_start = start - timedelta(days=400)
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
    # A. 指標計算
    raw_df['SMA200'] = raw_df['Price'].rolling(window=200).mean()
    df = raw_df[raw_df.index >= pd.to_datetime(st.session_state.start_date)].copy()
    
    # B. 報酬計算
    df['Daily_Ret'] = df['Price'].pct_change()
    daily_fee = annual_fee / 252
    
    if use_sma_defense:
        df['Signal'] = (df['Price'] > df['SMA200']).shift(1).fillna(False)
        df['Strategy_Ret'] = np.where(df['Signal'], df['Daily_Ret'] * leverage - daily_fee, 0.0)
    else:
        df['Strategy_Ret'] = df['Daily_Ret'] * leverage - daily_fee

    # C. 淨值與回撤計算
    df['Index_Cum'] = (1 + df['Daily_Ret'].fillna(0)).cumprod() * 100
    df['Strategy_Cum'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() * 100
    df['Index_DD'] = (df['Index_Cum'] - df['Index_Cum'].cummax()) / df['Index_Cum'].cummax()
    df['Strategy_DD'] = (df['Strategy_Cum'] - df['Strategy_Cum'].cummax()) / df['Strategy_Cum'].cummax()
    
    # D. 視覺化縮放修正
    scale_factor = 100 / df['Price'].iloc[0]
    df['SMA200_Scaled'] = df['SMA200'] * scale_factor

    # --- 6. 指標面板 ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("基準指數最終價值", f"{df['Index_Cum'].iloc[-1]:.1f} 萬")
    m2.metric("正2策略最終價值", f"{df['Strategy_Cum'].iloc[-1]:.1f} 萬", delta=f"{((df['Strategy_Cum'].iloc[-1]/100)-1)*100:.1f}%")
    m3.metric("指數最大回撤", f"{df['Index_DD'].min()*100:.1f}%")
    m4.metric("策略最大回撤", f"{df['Strategy_DD'].min()*100:.1f}%", delta_color="inverse")

    # --- 7. 走勢圖表 ---
    st.subheader("📈 資產淨值走勢")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Index_Cum'], name='原始指數 (1x)', line=dict(color='rgba(150, 150, 150, 0.5)')))
    fig.add_trace(go.Scatter(x=df.index, y=df['Strategy_Cum'], name=f'模擬正2 (2x)', line=dict(color='#00D1B2', width=2.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA200_Scaled'], name='200SMA (同步縮放)', line=dict(dash='dot', color='rgba(255, 165, 0, 0.6)')))
    fig.update_layout(hovermode="x unified", height=400, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 8. 回撤圖表 (新增回來的區塊) ---
    st.subheader("📉 歷史回撤深度比較")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Index_DD'], name='指數回撤', fill='tozeroy', line=dict(width=1, color='rgba(150, 150, 150, 0.3)')))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Strategy_DD'], name='策略回撤', fill='tozeroy', line=dict(width=1, color='rgba(0, 209, 178, 0.3)')))
    
    fig_dd.update_layout(
        hovermode="x unified",
        height=300,
        margin=dict(l=20, r=20, t=30, b=20),
        yaxis_tickformat=".1%",
        yaxis_title="回撤百分比"
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    # --- 9. MDD 表格 ---
    st.subheader("📊 最大回撤 (MDD) 深度分析")
    def get_mdd_stats(cum_series, dd_series):
        mdd_val = dd_series.min()
        valley_date = dd_series.idxmin()
        peak_date = cum_series[:valley_date].idxmax()
        return f"{mdd_val*100:.2f}%", str(peak_date.date()), str(valley_date.date()), (valley_date - peak_date).days

    idx_stats = get_mdd_stats(df['Index_Cum'], df['Index_DD'])
    str_stats = get_mdd_stats(df['Strategy_Cum'], df['Strategy_DD'])

    mdd_compare_data = {
        "分析指標": ["最大回撤 (MDD)", "起點 (歷史高點)", "終點 (最慘低點)", "回撤歷時 (天)"],
        "基準指數 (1x)": idx_stats,
        f"模擬正2 ({leverage}x)": str_stats
    }
    st.dataframe(pd.DataFrame(mdd_compare_data), use_container_width=True, hide_index=True)

    # --- 10. 專業說明區塊 ---
    st.divider()
    st.subheader("💡 模擬參數與防禦機制說明")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown(f"""
        **為什麼需要 200SMA 防禦？**
        * **避開主跌段**：在 2000 年或 2008 年，股市一旦跌破 200SMA 往往代表長期空頭。透過防禦開關，你可以看到「避開空頭」對正2淨值的巨大貢獻。
        * **減少曝險**：槓桿工具在空頭市場的「每日平衡」會導致資產迅速縮水，防禦機制能讓你在市場極度危險時退場觀望。
        """)
    with col_info2:
        st.markdown(f"""
        **1.5% 年度損耗與波動損耗說明**
        * **1.5% 損耗**：包含經理費、保管費與期貨轉倉成本。這是一個保守的壓力測試值。
        * **波動損耗**：本程式採用「每日平衡」計算，自動還原了震盪盤整時的「路徑依賴損耗」。當你看到圖中正2的回升速度不對稱時，那就是波動損耗的體現。
        """)

else:
    st.warning("⚠️ 無法獲取該時段資料，請檢查代碼或網路。")
