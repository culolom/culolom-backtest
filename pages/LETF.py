import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="0050 極簡槓桿計算器", layout="wide")
st.title("📊 0050 極簡動態槓桿計算器")

# 1. 讓使用者設定參數
col_in1, col_in2 = st.columns(2)
with col_in1:
    sma_window = st.number_input("設定均線天數 (如 200 或 20)", min_value=5, max_value=240, value=200, step=5)
with col_in2:
    rf_rate = st.number_input("信貸利率 (%)", min_value=0.0, max_value=15.0, value=3.0, step=0.1) / 100

# 2. 自動讀取 0050 資料
df = pd.DataFrame()
for path in ["data/0050.TW.csv", "data/0050.csv", "0050.TW.csv", "0050.csv"]:
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        break

if df.empty:
    st.error("⚠️ 找不到 0050 的 CSV 檔案，請確認 data/ 目錄下是否有 0050.TW.csv 或 0050.csv")
else:
    # 3. 核心指標計算 (計算收盤價大於均線時的特徵)
    df["SMA"] = df["Close"].rolling(sma_window).mean()
    df["Daily_Return"] = np.log(df["Close"] / df["Close"].shift(1)) # 對數報酬率
    
    # 篩選出 > SMA 的多頭波段
    bull_df = df[df["Close"] > df["SMA"]].dropna()
    
    if not bull_df.empty:
        mu = bull_df["Daily_Return"].mean() * 252       # 年化報酬率
        sigma = bull_df["Daily_Return"].std() * np.sqrt(252) # 年化波動率
        
        # 套用論文默頓最佳槓桿公式: β = (μ - rf) / σ²
        optimal_leverage = (mu - rf_rate) / (sigma ** 2) if sigma > 0 else 0.0
        
        # 4. 畫面呈現結果
        st.write(f"**📅 最新數據日期：** {df.index[-1].strftime('%Y-%m-%d')}")
        
        # 判斷今天是否在均線上
        if df["Close"].iloc[-1] > df["SMA"].iloc[-1]:
            st.success("🟢 目前最新狀態：0050 價格在均線之上（多頭環境）")
        else:
            st.warning("🔴 目前最新狀態：0050 價格在均線之下（空頭環境，建議保守或換回原型資產）")
            
        st.write("---")
        # 輸出您要的三個核心數字
        col1, col2, col3 = st.columns(3)
        col1.metric("📈 多頭年化報酬率 (μ)", f"{mu:.2%}")
        col2.metric("⚡ 多頭年化波動率 (σ)", f"{sigma:.2%}")
        col3.metric("💡 適合的名義槓桿比例", f"{optimal_leverage:.2f} 倍")
    else:
        st.error("計算失敗，滿足該均線天數的多頭數據不足。")
