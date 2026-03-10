###############################################################
# app.py — 50/50 策略：總曝險回撤視角 (倉鼠量化戰情室版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 基礎設定 ---
st.set_page_config(page_title="50/50 總曝險回撤分析", page_icon="🛡️", layout="wide")

st.markdown("<h1 style='margin-bottom:0.5em;'>🛡️ 50/50 策略：總曝險回撤分析</h1>", unsafe_allow_html=True)
st.markdown("""
<b>核心邏輯：</b> 即使你只拿 50 萬買正2，我們仍以 100 萬作為基準計算回撤。<br>
這能真實反映「現金作為緩衝」如何保護你的總體資產，避免被正2 的劇烈波動嚇出場。
""", unsafe_allow_html=True)

# --- 核心回測引擎 (修正 MDD 邏輯) ---
def run_backtest(df, initial_capital, freq_code):
    """
    計算邏輯：嚴格區分現金與股票市值，最終合併為 Equity 曲線
    """
    cash = initial_capital * 0.5
    shares = (initial_capital * 0.5) / df["Price_lev"].iloc[0]
    
    portfolio_values = []
    cash_values = []
    stock_values = []
    reb_dates = df.resample(freq_code).last().index if freq_code else []
    
    for i in range(len(df)):
        current_date = df.index[i]
        p_lev = df["Price_lev"].iloc[i]
        
        # 1. 計算當下總市值 (這是 MDD 的分母)
        current_stock_val = shares * p_lev
        total_val = cash + current_stock_val
        
        portfolio_values.append(total_val)
        cash_values.append(cash)
        stock_values.append(current_stock_val)
        
        # 2. 判斷再平衡 (只在有設定頻率時觸發)
        if freq_code and current_date in reb_dates and i < len(df)-1:
            cash = total_val * 0.5
            shares = (total_val * 0.5) / p_lev
            
    return pd.DataFrame({
        "Equity": portfolio_values,
        "Cash_Component": cash_values,
        "Stock_Component": stock_values
    }, index=df.index)

# --- UI 邏輯與圖表 (略過重複的 load_csv, 專注於顯示) ---

# ... (此處保留 load_csv 與基本 UI 設定) ...

if st.button("開始計算策略 🚀"):
    # (假設已讀取 df 與設定好參數)
    
    # 執行回測
    res = run_backtest(df, capital, freq_map[reb_freq])
    df = pd.concat([df, res], axis=1)
    
    # 計算 0050 基準 (全倉 100 萬)
    df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]

    # --- 1. 策略訊號與執行價格 (雙軸對照) ---
    # (同前次代碼，此處略)

    # --- 2. 資金曲線與風險解析 (視覺化現金與股票的關係) ---
    
    st.markdown("<h3>📊 總資產組成與回撤分析</h3>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["資產組成堆疊圖", "總曝險回撤深度"])
    
    with tab1:
        fig_stack = go.Figure()
        fig_stack.add_trace(go.Scatter(x=df.index, y=df["Cash_Component"], name="現金部位 (緩衝)", stackgroup='one', line=dict(width=0.5, color='gray')))
        fig_stack.add_trace(go.Scatter(x=df.index, y=df["Stock_Component"], name="正2 部位 (曝險)", stackgroup='one', line=dict(width=0.5, color='orange')))
        fig_stack.update_layout(template="plotly_white", yaxis_title="總資產價值", hovermode="x unified")
        st.plotly_chart(fig_stack, use_container_width=True)

    with tab2:
        # 這裡的 MDD 已經是基於 (現金 + 股票) 的總價值計算
        dd_strat = (df["Equity"] / df["Equity"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="50/50 總資產回撤", fill='tozeroy', line=dict(color='red')))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="0050 全倉回撤", line=dict(color='blue')))
        fig_dd.update_layout(template="plotly_white", yaxis_title="回撤百分比 (%)")
        st.plotly_chart(fig_dd, use_container_width=True)

    # --- 3. 比較表格 (強化 MDD 的解釋) ---
    # ... (計算 stats_strat 與 stats_base) ...
    # 渲染 HTML 表格 ...
