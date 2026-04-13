import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 頁面配置 ---
st.set_page_config(page_title="正2歷史模擬 - 倉鼠量化戰情室", layout="wide")

# 自定義樣式：優化按鈕與指標顯示
st.markdown("""
    <style>
    div.stButton > button { width: 100%; height: 3em; font-size: 1.2em; font-weight: bold; border-radius: 10px; }
    div[data-testid="stMetric"] { background-color: #161B22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 側邊欄配置 (Sidebar) ---
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

# 初始化 Session State 來儲存日期
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

# --- 4. 寫死參數設定 ---
target_symbol = "^TWII"
leverage = 2.0
annual_fee = 0.015  # 寫死 1.5%

st.info(f"當前模擬：**{st.session_state.scenario_name}** | 標的：**{target_symbol}** | 槓桿：**{leverage}x** | 年度損耗：**1.5%**")

# --- 5. 資料抓取與計算 ---
@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    try:
        df = yf.download(symbol, start=start, end=end, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df['Close']
        else:
            df = df[['Close']]
        df = df[[symbol]] if symbol in df.columns else df.iloc[:, [0]]
        df.columns = ['Price']
        return df
    except:
        return None

df = get_backtest_data(target_symbol, st.session_state.start_date, st.session_state.end_date)

if df is not None and len(df) > 0:
    # 核心邏輯
    df['Daily_Ret'] = df['Price'].pct_change()
    daily_fee = annual_fee / 252
    df['Strategy_Ret'] = df['Daily_Ret'] * leverage - daily_fee

    df['Index_Cum'] = (1 + df['Daily_Ret'].fillna(0)).cumprod() * 100
    df['Strategy_Cum'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() * 100
    
    # 回撤計算
    df['Index_DD'] = (df['Index_Cum'] - df['Index_Cum'].cummax()) / df['Index_Cum'].cummax()
    df['Strategy_DD'] = (df['Strategy_Cum'] - df['Strategy_Cum'].cummax()) / df['Strategy_Cum'].cummax()

    # --- 6. 指標面板 ---
    m1, m2, m3, m4 = st.columns(4)
    final_idx = df['Index_Cum'].iloc[-1]
    final_strat = df['Strategy_Cum'].iloc[-1]
    m1.metric("指數最終價值", f"{final_idx:.1f} 萬")
    m2.metric("策略最終價值", f"{final_strat:.1f} 萬", delta=f"{((final_strat/100)-1)*100:.1f}%")
    m3.metric("指數最大回撤", f"{df['Index_DD'].min()*100:.1f}%")
    m4.metric("策略最大回撤", f"{df['Strategy_DD'].min()*100:.1f}%", delta_color="inverse")

    # --- 7. MDD 比較表格 ---
    st.subheader("📊 最大回撤 (MDD) 深度分析")
    def get_mdd_stats(cum_series, dd_series):
        mdd_val = dd_series.min()
        valley_date = dd_series.idxmin()
        peak_date = cum_series[:valley_date].idxmax()
        duration = (valley_date - peak_date).days
        return mdd_val, peak_date.date(), valley_date.date(), duration

    idx_mdd, idx_peak, idx_valley, idx_dur = get_mdd_stats(df['Index_Cum'], df['Index_DD'])
    str_mdd, str_peak, str_valley, str_dur = get_mdd_stats(df['Strategy_Cum'], df['Strategy_DD'])

    mdd_compare_data = {
        "分析指標": ["最大回撤 (MDD)", "起點 (歷史高點)", "終點 (最慘低點)", "回撤歷時 (天)"],
        "基準指數 (1x)": [f"{idx_mdd*100:.2f}%", idx_peak, idx_valley, idx_dur],
        f"模擬正2 ({leverage}x)": [f"{str_mdd*100:.2f}%", str_peak, str_valley, str_dur]
    }
    st.table(pd.DataFrame(mdd_compare_data))

    # --- 8. 走勢圖表 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Index_Cum'], name='原始指數 (1x)', line=dict(color='rgba(200, 200, 200, 0.5)')))
    fig.add_trace(go.Scatter(x=df.index, y=df['Strategy_Cum'], name=f'模擬正2 (2x)', line=dict(color='#00D1B2', width=2.5)))
    fig.update_layout(template="plotly_dark", hovermode="x unified", height=400, margin=dict(l=20, r=20, t=30, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # --- 9. 專業說明區塊 ---
    st.divider()
    st.subheader("💡 模擬參數細節說明")
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.markdown("""
        **為何預估年度損耗設定為 1.5%？**
        這是一個貼近現實台股正2（如 00631L）的保守估計：
        * **基本內扣 (約 1.04%)**：包含經理費 (1.0%) 與保管費 (0.04%)。
        * **交易與轉倉成本 (約 0.46%)**：包含期貨換月價差損耗、指數授權費及相關雜支。
        * *註：台股長期處於逆價差，有時轉倉甚至是正貢獻，在此抓 1.5% 係為了壓力測試極端環境。*
        """)
    
    with col_info2:
        st.markdown("""
        **關於「波動損耗 (Volatility Decay)」**
        本模擬已自動包含波動損耗，原因如下：
        * 本程式採用 **「每日平衡 (Daily Rebalancing)」** 邏輯計算。
        * 複利公式為：$Value_{t} = Value_{t-1} \times (1 + R_{daily} \times 2)$。
        * 當市場大幅震盪（先跌 10% 再漲 10%）時，槓桿淨值的回升速度會天生慢於原指數，這就是數學上的**路徑依賴損耗**，已完美還原在曲線中。
        """)

else:
    st.warning("⚠️ 無法獲取該時段資料，請檢查代碼設定。")
