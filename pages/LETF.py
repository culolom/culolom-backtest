import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="0050 長期總體槓桿計算器", layout="wide")
st.title("📊 0050 長期總體常態槓桿計算器")

# 1. 讓使用者設定參數 (此時均線天數僅用於判斷當前多空燈號，不影響槓桿計算公式)
col_in1, col_in2 = st.columns(2)
with col_in1:
    sma_window = st.number_input("設定狀態均線天數 (僅用於多空狀態判斷)", min_value=5, max_value=240, value=200, step=5)
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
    
    # 🎯 核心邏輯修正 2：年化波動率 (σ) 也直接計算歷史所有數據的總標準差 (不看均線篩選)
    sigma_all_history = df["Daily_Return"].std() * np.sqrt(252)
    
    # 3. 計算均線，僅用於判斷當前的最新多空狀態
    df["SMA"] = df["Close"].rolling(sma_window).mean()
    
    if len(df) > sma_window:
        # 套用論文公式計算長期常態最佳槓桿: β = (長期所有μ - rf) / 長期所有σ²
        optimal_leverage = (mu_all_history - rf_rate) / (sigma_all_history ** 2) if sigma_all_history > 0 else 0.0
        
        # 4. 畫面呈現結果
        st.write(f"**📅 最新有效數據日期：** {df.index[-1].strftime('%Y-%m-%d')}")
        st.write(f"**💰 當前 0050 收盤價：** {df['Close'].iloc[-1]:.2f} 元 (均線：{df['SMA'].iloc[-1]:.2f} 元)")
        
        # 狀態燈號判斷
        if df["Close"].iloc[-1] > df["SMA"].iloc[-1]:
            st.success("🟢 目前最新狀態：0050 價格在均線之上（長期常態槓桿可行，目前環境健康）")
        else:
            st.warning("🔴 目前最新狀態：0050 價格在均線之下（注意：目前大環境處於空頭波段，請謹慎防範黑天鵝）")
            
        st.write("---")
        # 輸出三個核心數字
        col1, col2, col3 = st.columns(3)
        col1.metric("📈 長期歷史年化報酬率 (μ)", f"{mu_all_history:.2%}", help="計算 data 內所有日期的總體報酬期望值")
        col2.metric("⚡ 長期歷史年化波動率 (σ)", f"{sigma_all_history:.2%}", help="計算 data 內所有日期的總體年化標準差")
        col3.metric("💡 長期常態適合槓桿比例", f"{optimal_leverage:.2f} 倍", help="排除短期干擾，依據歷史全數據算出的最穩健基準槓桿")
    else:
        st.error("計算失敗，數據量不足以計算均線天數。")
