###############################################################
# app.py — 0050 正2/反1 動態切換策略
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# 基本設定
st.set_page_config(page_title="正2/反1 動態切換策略", page_icon="⚖️", layout="wide")

ID_LONG = "00631L.TW"   # 正2
ID_SHORT = "00632R.TW"  # 反1
DATA_DIR = Path("data")

###############################################################
# 1. 核心計算與數據加載
###############################################################

def load_required_data():
    """載入正2與反1的數據並對齊日期"""
    p_long = DATA_DIR / f"{ID_LONG}.csv"
    p_short = DATA_DIR / f"{ID_SHORT}.csv"
    
    if not p_long.exists() or not p_short.exists():
        st.error(f"❌ 缺少必要檔案: 請確保 data 資料夾內有 {ID_LONG}.csv 與 {ID_SHORT}.csv")
        st.stop()
        
    df_l = pd.read_csv(p_long, parse_dates=["Date"], index_col="Date")[["Close"]].rename(columns={"Close": "Price_L"})
    df_s = pd.read_csv(p_short, parse_dates=["Date"], index_col="Date")[["Close"]].rename(columns={"Close": "Price_S"})
    
    # 合併數據並移除空值（對齊兩者都有交易的時間）
    df = pd.concat([df_l, df_s], axis=1).sort_index().dropna()
    return df

def get_stats(eq, rets, y):
    if y <= 0 or len(eq) == 0: return [0]*8
    f_eq = eq.iloc[-1]
    f_ret = f_eq - 1
    cagr = (1 + f_ret)**(1/y) - 1 if f_ret > -1 else -1
    mdd = 1 - (eq / eq.cummax()).min()
    
    # 波動率與 Sharpe
    avg = rets.mean()
    std = rets.std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else 0
    calmar = cagr / mdd if mdd > 0 else 0
    return f_eq, f_ret, cagr, mdd, vol, sharpe, 0, calmar

###############################################################
# 2. UI 介面
###############################################################

st.markdown("# ⚖️ 0050 正2/反1 動態切換策略")
st.markdown("##### 策略邏輯：以正2 (00631L) 之 SMA 作為多空濾網")
st.info("💡 **多頭 (正2 > SMA)**: 操作正2 | **空頭 (正2 < SMA)**: 操作反1")

with st.sidebar:
    st.header("⚙️ 參數設定")
    sma_window = st.number_input("SMA 趨勢線天數 (以正2為準)", 10, 300, 200)
    lookback_window = st.number_input("區間極值天數", 5, 120, 20)
    buy_pct = st.number_input("買進：自區間最低點回升 (%)", 0.5, 20.0, 5.0) / 100
    sell_pct = st.number_input("賣出：自區間最高點回落 (%)", 0.5, 20.0, 5.0) / 100
    capital = st.number_input("初始本金", 10000, 1000000, 100000)

# 載入數據
df = load_required_data()
s_min, s_max = df.index.min().date(), df.index.max().date()

col_d1, col_d2 = st.columns(2)
start_dt = col_d1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=365*5)))
end_dt = col_d2.date_input("結束日期", value=s_max)

if st.button("執行回測執行引擎 🚀"):
    # 預處理
    df["SMA_Ref"] = df["Price_L"].rolling(sma_window).mean()
    
    # 分別計算兩者的區間極值 (避免未來函數，需 shift)
    df["L_Min"] = df["Price_L"].rolling(lookback_window).min().shift(1)
    df["L_Max"] = df["Price_L"].rolling(lookback_window).max().shift(1)
    df["S_Min"] = df["Price_S"].rolling(lookback_window).min().shift(1)
    df["S_Max"] = df["Price_S"].rolling(lookback_window).max().shift(1)
    
    # 裁切日期
    df = df.loc[start_dt:end_dt].dropna(subset=["SMA_Ref", "L_Min", "S_Min"])
    
    # 策略執行
    status = [] # 記錄當前持有的標的 0:空手, 1:正2, 2:反1
    pos_history = [0] * len(df)
    target_history = ["None"] * len(df)
    
    current_pos = 0 # 0: Cash, 1: Holding
    
    for i in range(len(df)):
        p_l = df["Price_L"].iloc[i]
        p_s = df["Price_S"].iloc[i]
        sma = df["SMA_Ref"].iloc[i]
        
        # 判斷當前大趨勢
        is_bull = p_l > sma
        
        if is_bull:
            # --- 多頭市場：操作正2 ---
            l_buy_trigger = df["L_Min"].iloc[i] * (1 + buy_pct)
            l_sell_trigger = df["L_Max"].iloc[i] * (1 - sell_pct)
            
            if current_pos == 0:
                if p_l > l_buy_trigger:
                    current_pos = 1 # 買入正2
            elif current_pos == 1: # 原本持有的就是正2
                if p_l < l_sell_trigger:
                    current_pos = 0 # 賣出
            else: # 原本持有反1，但現在變多頭了，強制平倉或轉換
                current_pos = 0 
                
            active_target = "00631L" if current_pos == 1 else "Cash"
            
        else:
            # --- 空頭市場：操作反1 ---
            s_buy_trigger = df["S_Min"].iloc[i] * (1 + buy_pct)
            s_sell_trigger = df["S_Max"].iloc[i] * (1 - sell_pct)
            
            if current_pos == 0:
                if p_s > s_buy_trigger:
                    current_pos = 2 # 買入反1
            elif current_pos == 2: # 原本持有的就是反1
                if p_s < s_sell_trigger:
                    current_pos = 0 # 賣出
            else: # 原本持有正2，但現在變空頭了
                current_pos = 0
            
            active_target = "00632R" if current_pos == 2 else "Cash"

        pos_history[i] = current_pos
        target_history[i] = active_target

    df["Position"] = pos_history
    df["Target"] = target_history
    
    # --- 計算報酬率 ---
    # 策略每日報酬 = (標的每日報酬 * 1) if 持有 else 0
    df["Ret_L"] = df["Price_L"].pct_change().fillna(0)
    df["Ret_S"] = df["Price_S"].pct_change().fillna(0)
    
    strat_rets = []
    for i in range(len(df)):
        if i == 0:
            strat_rets.append(0)
            continue
        
        # 獲取前一天的持有狀態來決定今天的報酬
        prev_pos = df["Position"].iloc[i-1]
        if prev_pos == 1:
            strat_rets.append(df["Ret_L"].iloc[i])
        elif prev_pos == 2:
            strat_rets.append(df["Ret_S"].iloc[i])
        else:
            strat_rets.append(0)
            
    df["Strategy_Ret"] = strat_rets
    df["Equity"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Benchmark"] = (1 + df["Ret_L"]).cumprod() # 以正2 B&H 為基準
    
    # 統計指標
    y_len = (df.index[-1] - df.index[0]).days / 365
    sl = get_stats(df["Equity"], df["Strategy_Ret"], y_len)
    sb = get_stats(df["Benchmark"], df["Ret_L"], y_len)

    # --- 顯示結果 ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("期末資產", f"{sl[0]*capital:,.0f}", f"{sl[1]:.2%}")
    c2.metric("年化報酬 (CAGR)", f"{sl[2]:.2%}")
    c3.metric("最大回撤 (MDD)", f"{sl[3]:.2%}")
    c4.metric("Sharpe Ratio", f"{sl[5]:.2f}")

    # --- 圖表 ---
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("資金曲線比較 (對比正2 B&H)", "趨勢濾網與持倉狀態"),
                        row_heights=[0.6, 0.4])
    
    # 資金曲線
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity"], name="切換策略", line=dict(color="#00D494", width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Benchmark"], name="正2 Buy & Hold", line=dict(color="#94A3B8", dash="dot")), row=1, col=1)
    
    # 趨勢與標的
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_L"], name="正2 價格", line=dict(color="#1E293B", width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Ref"], name=f"{sma_window}SMA 濾網", line=dict(color="#FB923C")), row=2, col=1)
    
    # 用顏色區分持倉狀態
    # 為了視覺化簡潔，我們只標註買入點
    buy_l = df[ (df["Position"]==1) & (df["Position"].shift(1)!=1) ]
    buy_s = df[ (df["Position"]==2) & (df["Position"].shift(1)!=2) ]
    
    fig.add_trace(go.Scatter(x=buy_l.index, y=buy_l["Price_L"], mode="markers", name="買入正2", 
                             marker=dict(symbol="triangle-up", size=10, color="#22C55E")), row=2, col=1)
    fig.add_trace(go.Scatter(x=buy_s.index, y=buy_s["Price_L"], mode="markers", name="買入反1", 
                             marker=dict(symbol="triangle-up", size=10, color="#EF4444")), row=2, col=1)

    fig.update_layout(height=800, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    
    # 交易明細
    with st.expander("查看最後 10 筆回測數據"):
        st.dataframe(df[["Price_L", "SMA_Ref", "Target", "Equity"]].tail(10))
