import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 頁面配置 ---
st.set_page_config(page_title="正2歷史模擬 - 倉鼠量化戰情室", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetric"] { background-color: #161B22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

st.title("🐹 正2 歷史極端行情模擬器")
st.caption("透過「每日平衡」邏輯，還原 2008 金融海嘯等時期的模擬表現")

# --- 2. 側邊欄參數 ---
with st.sidebar:
    st.header("⚙️ 模擬參數")
    target_symbol = st.text_input("輸入回測指數代碼", value="^TWII")
    
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("開始日期", value=datetime(2007, 1, 1))
    with col_date2:
        end_date = st.date_input("結束日期", value=datetime(2010, 12, 31))
    
    leverage = st.slider("槓桿倍數", 1.0, 2.0, 2.0, step=0.1)
    annual_fee = st.slider("預估年度損耗 (%)", 0.0, 5.0, 1.5, step=0.1) / 100
    
    st.markdown("---")
    st.subheader("策略濾網")
    use_sma = st.checkbox("啟用 200SMA 趨勢濾網", value=False)
    sma_period = st.number_input("SMA 週期", value=200, min_value=5)

# --- 3. 資料抓取函數 ---
@st.cache_data(ttl=3600)
def get_backtest_data(symbol, start, end):
    try:
        df = yf.download(symbol, start=start, end=end, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df['Adj Close'] if 'Adj Close' in df.columns.levels[0] else df['Close']
        else:
            df = df[['Adj Close']] if 'Adj Close' in df.columns else df[['Close']]
        df = df[[symbol]] if symbol in df.columns else df.iloc[:, [0]]
        df.columns = ['Price']
        return df
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return None

# --- 4. 核心回測邏輯 ---
df = get_backtest_data(target_symbol, start_date, end_date)

if df is not None and len(df) > 0:
    df['Daily_Ret'] = df['Price'].pct_change()
    df['SMA'] = df['Price'].rolling(window=sma_period).mean()
    daily_fee = annual_fee / 252
    
    if use_sma:
        df['Signal'] = (df['Price'] > df['SMA']).shift(1).fillna(False)
        df['Strategy_Ret'] = np.where(df['Signal'], df['Daily_Ret'] * leverage - daily_fee, 0.0)
    else:
        df['Strategy_Ret'] = df['Daily_Ret'] * leverage - daily_fee

    df['Index_Cum'] = (1 + df['Daily_Ret'].fillna(0)).cumprod() * 100
    df['Strategy_Cum'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() * 100
    
    # 計算回撤 (Drawdown)
    df['Index_DD'] = (df['Index_Cum'] - df['Index_Cum'].cummax()) / df['Index_Cum'].cummax()
    df['Strategy_DD'] = (df['Strategy_Cum'] - df['Strategy_Cum'].cummax()) / df['Strategy_Cum'].cummax()

    # --- 5. 數據面板 ---
    m1, m2, m3, m4 = st.columns(4)
    final_idx = df['Index_Cum'].iloc[-1]
    final_strat = df['Strategy_Cum'].iloc[-1]
    m1.metric("指數最終價值", f"{final_idx:.1f} 萬")
    m2.metric("策略最終價值", f"{final_strat:.1f} 萬", delta=f"{((final_strat/100)-1)*100:.1f}%")
    m3.metric("指數最大回撤", f"{df['Index_DD'].min()*100:.1f}%")
    m4.metric("策略最大回撤", f"{df['Strategy_DD'].min()*100:.1f}%", delta_color="inverse")

    # --- 6. 最大回撤比較表格 (新增功能) ---
    st.subheader("📊 最大回撤 (MDD) 深度分析")

    def get_mdd_stats(cum_series, dd_series):
        mdd_val = dd_series.min()
        valley_date = dd_series.idxmin()
        # 找到在最低點之前的最高點日期
        peak_date = cum_series[:valley_date].idxmax()
        # 計算回撤持續天數 (從最高點到最低點)
        duration = (valley_date - peak_date).days
        return mdd_val, peak_date.date(), valley_date.date(), duration

    idx_mdd, idx_peak, idx_valley, idx_dur = get_mdd_stats(df['Index_Cum'], df['Index_DD'])
    str_mdd, str_peak, str_valley, str_dur = get_mdd_stats(df['Strategy_Cum'], df['Strategy_DD'])

    mdd_compare_data = {
        "分析指標": ["最大回撤 (MDD)", "起點 (歷史高點)", "終點 (最慘低點)", "回撤歷時 (天)"],
        "基準指數 (1x)": [f"{idx_mdd*100:.2f}%", idx_peak, idx_valley, idx_dur],
        f"模擬策略 ({leverage}x)": [f"{str_mdd*100:.2f}%", str_peak, str_valley, str_dur]
    }
    
    mdd_df = pd.DataFrame(mdd_compare_data)
    st.table(mdd_df) # 使用 st.table 顯示靜態漂亮表格

    # --- 7. 視覺化圖表 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Index_Cum'], name='原始指數 (1x)', line=dict(color='rgba(200, 200, 200, 0.5)')))
    fig.add_trace(go.Scatter(x=df.index, y=df['Strategy_Cum'], name=f'模擬策略 ({leverage}x)', line=dict(color='#00D1B2', width=2.5)))
    fig.update_layout(title="資產淨值累積曲線", template="plotly_dark", hovermode="x unified", yaxis_title="萬元")
    st.plotly_chart(fig, use_container_width=True)

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Index_DD'], name='指數回撤', fill='tozeroy', line=dict(width=0)))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Strategy_DD'], name='策略回撤', fill='tozeroy', line=dict(width=0)))
    fig_dd.update_layout(title="歷史回撤深度比較", template="plotly_dark", yaxis_tickformat=".1%")
    st.plotly_chart(fig_dd, use_container_width=True)

else:
    st.warning("⚠️ 無法獲取資料，請檢查代碼或日期。")
