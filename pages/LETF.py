import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="0050 改進版槓桿計算器", layout="wide")
st.title("📊 0050 動態波動 × 長期報酬 槓桿計算器")

# 1. 讓使用者設定參數
col_in1, col_in2 = st.columns(2)
with col_in1:
    sma_window = st.number_input("設定動態均線天數 (決定波動率)", min_value=5, max_value=240, value=200, step=5)
with col_in2:
    rf_rate = st.number_input("信貸利率 (%)", min_value=0.0, max_value=15.0, value=3.0, step=0.1) / 100

# 2. 自動讀取 0050 資料
df = pd.DataFrame()
for path in ["data/0050.TW.csv", "data/0050.csv", "0050.TW.csv", "0050.csv"]:
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        break

if df.empty:
    st.error("⚠️ 找不到 0050 的 CSV 檔案")
else:
    # 剔除不完整資料
    df = df.dropna(subset=["Close"])
    
    # 計算基礎對數報酬率
    df["Daily_Return"] = np.log(df["Close"] / df["Close"].shift(1))
    
    # 🎯 核心邏輯修正 1：年化報酬率 (μ) 直接計算歷史所有數據的總平均
    mu_all_history = df["Daily_Return"].mean() * 252
    
    # 🎯 核心邏輯修正 2：只有波動率才跟隨均線設定篩選
    df["SMA"] = df["Close"].rolling(sma_window).mean()
    bull_df = df[df["Close"] > df["SMA"]].dropna()
    
    if not bull_df.empty:
        # 只計算大於均線（多頭狀態下）的年化波動率
        sigma_bull = bull_df["Daily_Return"].std() * np.sqrt(252)
        
        # 套用公式計算合理槓桿: β = (長期固定μ - rf) / 動態σ²
        optimal_leverage = (mu_all_history - rf_rate) / (sigma_bull ** 2) if sigma_bull > 0 else 0.0
        
        # 3. 畫面呈現結果
        st.write(f"**📅 最新有效數據日期：** {df.index[-1].strftime('%Y-%m-%d')}")
        st.write(f"**💰 當前 0050 收盤價：** {df['Close'].iloc[-1]:.2f} 元 (均線：{df['SMA'].iloc[-1]:.2f} 元)")
        
        if df["Close"].iloc[-1] > df["SMA"].iloc[-1]:
            st.success("🟢 目前最新狀態：0050 價格在均線之上（多頭環境）")
        else:
            st.warning("🔴 目前最新狀態：0050 價格在均線之下（空頭環境）")
            
        st.write("---")
        # 輸出核心數字
        col1, col2, col3 = st.columns(3)
        col1.metric("📈 長期歷史年化報酬率 (μ)", f"{mu_all_history:.2%}", help="計算 data 內所有日期的總體報酬期望值")
        col2.metric("⚡ 當前多頭環境年化波動率 (σ)", f"{sigma_bull:.2%}", help="僅計算符合大於均線天數時的最新波動度")
        col3.metric("💡 修正後的適合槓桿比例", f"{optimal_leverage:.2f} 倍", help="利用長期穩健報酬配上最新动态波動算出的黃金槓桿")
    else:
        st.error("計算失敗，滿足該均線天數的多頭數據不足。")
