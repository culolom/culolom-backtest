###############################################################
# app.py — 0050 多空切換 + 反一停利提前轉向版
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# ... (字型與環境設定保持原樣) ...

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 多空切換：反一提前轉向機制</h1>", unsafe_allow_html=True)

# --- UI 輸入 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    capital = st.number_input("投入本金", 1000, 5000000, 100000, step=10000)
with col2:
    sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)
with col3:
    start_date = st.date_input("開始日期", dt.date(2020, 1, 1))
with col4:
    end_date = st.date_input("結束日期", dt.date.today())

# 新增：反一提前停利規則設定
st.write("---")
col_rule1, col_rule2 = st.columns([1, 3])
with col_rule1:
    enable_early_exit = st.toggle("啟用反一提前轉向", value=True)
with col_rule2:
    bear_profit_target = st.number_input("反一漲幅超過此比例即轉向正 2 (%)", 1.0, 50.0, 10.0, step=0.5, disabled=not enable_early_exit) / 100

###############################################################
# 4. 回測執行
###############################################################
if st.button("開始回測 🚀"):
    # (資料載入與基礎計算部分與之前相同，省略載入過程...)
    df_base = load_csv("0050.TW")
    df_bull = load_csv("00631L.TW")
    df_bear = load_csv("00632R.TW")
    
    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_bull["Price"].rename("Price_bull"), how="inner")
    df = df.join(df_bear["Price"].rename("Price_bear"), how="inner")
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start_date:end_date].dropna(subset=["SMA"])

    # 5. 核心邏輯修改：加入成本追蹤
    signals = [1] * len(df)       # 最終決定的訊號 (1=正2, -1=反1)
    is_early_exited = [False] * len(df) # 記錄是否為提前轉向點
    
    current_signal = 1
    bear_entry_price = 0.0
    
    for i in range(1, len(df)):
        price_base = df["Price_base"].iloc[i]
        sma = df["SMA"].iloc[i]
        price_bear = df["Price_bear"].iloc[i]
        
        # 基本趨勢判斷
        trend_signal = 1 if price_base > sma else -1
        
        # 邏輯 A：如果趨勢翻正，重置所有狀態
        if trend_signal == 1:
            current_signal = 1
            bear_entry_price = 0.0
        
        # 邏輯 B：如果趨勢在空頭 (trend_signal == -1)
        else:
            # 如果原本剛從多頭轉空頭，或是之前已經重置
            if current_signal == 1 and bear_entry_price == 0:
                current_signal = -1
                bear_entry_price = price_bear # 記錄反一成本
            
            # 如果目前持有反一，檢查是否觸發「提前轉向」
            elif current_signal == -1 and enable_early_exit:
                profit_pct = (price_bear / bear_entry_price) - 1
                if profit_pct >= bear_profit_target:
                    current_signal = 1 # 提前轉向正 2
                    is_early_exited[i] = True # 標記這一天觸發了規則
        
        signals[i] = current_signal

    df["Signal"] = signals
    df["Early_Exit"] = is_early_exited
    
    # 績效計算 (與原代碼邏輯相同)
    df["Ret_bull"] = df["Price_bull"].pct_change().fillna(0)
    df["Ret_bear"] = df["Price_bear"].pct_change().fillna(0)
    df["Strategy_Ret"] = 0.0
    for i in range(1, len(df)):
        prev_sig = df["Signal"].iloc[i-1]
        df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bull"].iloc[i] if prev_sig == 1 else df["Ret_bear"].iloc[i]
    
    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["CumRet_bull_pct"] = (df["Price_bull"] / df["Price_bull"].iloc[0] - 1)
    df["CumRet_bear_pct"] = (df["Price_bear"] / df["Price_bear"].iloc[0] - 1)

    ###############################################################
    # 6. 繪製圖表
    ###############################################################
    st.markdown("<h3>📌 策略訊號與執行價格 (分開對照)</h3>", unsafe_allow_html=True)
    
    # 圖表 1：0050 與 正2 (加上提前轉向標記)
    fig_bull = go.Figure()
    fig_bull.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 (左軸)", line=dict(color="#636EFA")))
    fig_bull.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A")))
    fig_bull.add_trace(go.Scatter(x=df.index, y=df["CumRet_bull_pct"], name="正2 報酬 (右軸)", yaxis="y2", line=dict(dash='dot', color="#00CC96")))
    
    # 標註：普通轉向 vs 提前轉向
    normal_bull = df[(df["Signal"].diff() == 2) & (~df["Early_Exit"])]
    early_bull = df[df["Early_Exit"]]
    
    fig_bull.add_trace(go.Scatter(x=normal_bull.index, y=normal_bull["Price_base"], mode="markers", name="趨勢轉正2", marker=dict(symbol="triangle-up", size=10, color="green")))
    fig_bull.add_trace(go.Scatter(x=early_bull.index, y=early_bull["Price_base"], mode="markers", name="⭐ 提前轉向正2", marker=dict(symbol="star", size=12, color="gold", line=dict(width=1, color="black"))))

    fig_bull.update_layout(template="plotly_white", yaxis2=dict(overlaying="y", side="right", tickformat=".0%"))
    st.plotly_chart(fig_bull, use_container_width=True)

    # 圖表 2：0050 與 反一
    fig_bear = go.Figure()
    fig_bear.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 (左軸)", line=dict(color="#636EFA")))
    fig_bear.add_trace(go.Scatter(x=df.index, y=df["CumRet_bear_pct"], name="反一 報酬 (右軸)", yaxis="y2", line=dict(dash='dashdot', color="#EF553B")))
    
    # 標註轉向反一
    to_bear = df[df["Signal"].diff() == -2]
    fig_bear.add_trace(go.Scatter(x=to_bear.index, y=to_bear["Price_base"], mode="markers", name="轉向反一", marker=dict(symbol="triangle-down", size=10, color="red")))
    
    fig_bear.update_layout(template="plotly_white", yaxis2=dict(overlaying="y", side="right", tickformat=".0%"))
    st.plotly_chart(fig_bear, use_container_width=True)

    # ... (後續績效表格部分不變) ...
