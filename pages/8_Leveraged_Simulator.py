import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 1. 頁面標題
st.set_page_config(page_title="正2歷史模擬 - 倉鼠量化戰情室", layout="wide")
st.title("🐹 正2 歷史極端行情模擬器")
st.caption("模擬 2008 金融海嘯等極端情境下，正2 (00631L) 的每日平衡表現")

# 2. 側邊欄參數設定
with st.sidebar:
    st.header("⚙️ 模擬參數")
    # 預設使用台股加權指數 ^TWII
    target_symbol = st.text_input("輸入回測指數代碼", value="^TWII")
    
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("開始日期", value=datetime(2007, 1, 1))
    with col_date2:
        end_date = st.date_input("結束日期", value=datetime(2010, 12, 31))
    
    leverage = st.slider("槓桿倍數", 1.0, 2.0, 2.0, step=0.1)
    annual_fee = st.slider("預估年度損耗 (%)", 0.0, 5.0, 1.5) / 100
    
    st.markdown("---")
    use_sma = st.checkbox("啟用 200SMA 趨勢濾網", value=False)
    sma_period = st.number_input("SMA 週期", value=200)

# 3. 資料處理與計算
@st.cache_data
def get_backtest_data(symbol, start, end):
    df = yf.download(symbol, start=start, end=end)
    if df.empty: return None
    df = df[['Close']].copy()
    df.columns = ['Price']
    return df

df = get_backtest_data(target_symbol, start_date, end_date)

if df is not None:
    # 計算每日報酬
    df['Daily_Ret'] = df['Price'].pct_change()
    df['SMA'] = df['Price'].rolling(window=sma_period).mean()
    
    # 計算正2報酬 (考慮內扣費用)
    daily_fee = annual_fee / 252
    
    if use_sma:
        # 訊號：收盤 > SMA 隔日進場
        df['Signal'] = (df['Price'] > df['SMA']).shift(1).fillna(False)
        df['Strategy_Ret'] = np.where(df['Signal'], df['Daily_Ret'] * leverage - daily_fee, 0)
    else:
        df['Strategy_Ret'] = df['Daily_Ret'] * leverage - daily_fee

    # 計算累積淨值 (假設初始 100 萬)
    df['Index_Cum'] = (1 + df['Daily_Ret'].fillna(0)).cumprod() * 100
    df['Strategy_Cum'] = (1 + df['Strategy_Ret'].fillna(0)).cumprod() * 100

    # 4. 指標顯示
    m1, m2, m3 = st.columns(3)
    final_idx = df['Index_Cum'].iloc[-1]
    final_strat = df['Strategy_Cum'].iloc[-1]
    
    # 計算 MDD
    def get_mdd(series):
        return ((series - series.cummax()) / series.cummax()).min()

    m1.metric("指數最終淨值", f"{final_idx:.1f} 萬")
    m2.metric("策略最終淨值", f"{final_strat:.1f} 萬", delta=f"{final_strat - final_idx:.1f} 萬")
    m3.metric("策略最大回撤 (MDD)", f"{get_mdd(df['Strategy_Cum'])*100:.1f}%")

    # 5. 繪製圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Index_Cum'], name='原始指數 (1x)', line=dict(color='gray')))
    fig.add_trace(go.Scatter(x=df.index, y=df['Strategy_Cum'], name=f'策略模擬 ({leverage}x)', line=dict(color='#00D1B2', width=3)))
    
    fig.update_layout(
        title=f"{target_symbol} 模擬走勢圖",
        hovermode="x unified",
        template="plotly_dark",
        yaxis_title="資產價值 (萬元)"
    )
    st.plotly_chart(fig, use_container_width=True)

    # 6. 歷史崩盤區段觀察 (自動抓取最慘跌幅)
    st.subheader("📉 歷史回撤監控")
    df['Drawdown'] = (df['Strategy_Cum'] - df['Strategy_Cum'].cummax()) / df['Strategy_Cum'].cummax()
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Drawdown'], fill='tozeroy', name='回撤 %'))
    fig_dd.update_layout(template="plotly_dark", yaxis_tickformat=".1%")
    st.plotly_chart(fig_dd, use_container_width=True)

else:
    st.error("無法取得資料，請檢查代碼或日期設定。")
