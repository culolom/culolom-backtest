import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# ... (驗證與字型設定同前) ...

# ==========================================
# 核心計算邏輯：偵測動能衰竭 (Divergence Detection)
# ==========================================
def process_momentum_data(df, lookback_months, smooth_days):
    lookback_days = lookback_months * 21
    # 1. 計算原始動能 (12M ROC)
    df['Momentum'] = df['Price'].pct_change(lookback_days)
    # 2. 計算平滑動能 (你的紅線)
    df['Mom_Smooth'] = df['Momentum'].rolling(window=smooth_days).mean()
    # 3. 計算動能斜率 (Slope / 加速度)
    # 我們取 5 天的變化量來判斷方向，避免單日雜訊
    df['Mom_Slope'] = df['Mom_Smooth'].diff(5)
    
    # 4. 定義「動能衰竭」區間
    # 條件：動能 > 0 (還在漲) 且 動能斜率 < 0 (但速度變慢了)
    df['Is_Exhaustion'] = (df['Mom_Smooth'] > 0) & (df['Mom_Slope'] < 0)
    return df

# ... (UI 選單部分同前) ...

if not df_raw.empty:
    df = df_raw.loc[str(start_date):str(end_date)].copy()
    df = process_momentum_data(df, lookback_months, smooth_days)

    # ==========================================
    # 進階視覺化：自動標記衰竭區
    # ==========================================
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, 
                        subplot_titles=(f"{selected_label} 價格走勢 (淡橘色區塊為動能衰竭)", "12個月 動能強度 (ROC)"),
                        row_heights=[0.6, 0.4])

    # 1. 價格線
    fig.add_trace(go.Scatter(x=df.index, y=df['Price'], name="收盤價", line=dict(color="#1f77b4", width=2)), row=1, col=1)

    # 2. 動能與平滑線
    fig.add_trace(go.Scatter(x=df.index, y=df['Momentum'], name="原始動能", line=dict(color="rgba(150,150,150,0.3)", width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Mom_Smooth'], name="平滑動能 (紅線)", line=dict(color="#e41a1c", width=3)), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)

    # ✨ 自動標記：當動能衰竭時，加上背景色
    # 我們尋找 Is_Exhaustion 為 True 的區塊
    exhaustion_periods = df[df['Is_Exhaustion'] == True].index
    
    # 為了效能，我們用簡單的遮罩方式在 Plotly 標記區間
    for i in range(1, len(df)):
        if df['Is_Exhaustion'].iloc[i]:
            # 在上圖加底色
            fig.add_vrect(
                x0=df.index[i-1], x1=df.index[i],
                fillcolor="orange", opacity=0.1,
                layer="below", line_width=0,
                row=1, col=1
            )

    fig.update_layout(height=800, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # 數據診斷面板
    # ==========================================
    curr_status = "⚠️ 警示：動能衰竭中" if df['Is_Exhaustion'].iloc[-1] else "✅ 正常：動能續強或打底"
    st.info(f"**當前診斷：{curr_status}**")
