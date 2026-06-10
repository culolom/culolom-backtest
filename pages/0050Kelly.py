import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="0050 凱利公式戰情室", layout="wide")
st.title("📊 0050 凱利公式動態戰情室")

# 1. 讓使用者設定參數
col_in1, col_in2 = st.columns(2)
with col_in1:
    sma_window = st.number_input("設定狀態均線天數 (判斷目前多空燈號)", min_value=5, max_value=240, value=200, step=5)
with col_in2:
    rf_rate = st.number_input("無風險利率 / 資金成本 (%)", min_value=0.0, max_value=15.0, value=2.0, step=0.1) / 100

# 2. 自動讀取 0050 資料
df = pd.DataFrame()
for path in ["data/0050.TW.csv", "data/0050.csv", "0050.TW.csv", "0050.csv"]:
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        break

if df.empty:
    st.error("⚠️ 找不到 0050 的 CSV 檔案")
else:
    df = df.dropna(subset=["Close"])
    df["Daily_Return"] = np.log(df["Close"] / df["Close"].shift(1))
    
    # 🎯 核心計算：全歷史常態數據
    mu = df["Daily_Return"].mean() * 252       # 長期年化報酬率
    sigma = df["Daily_Return"].std() * np.sqrt(252) # 長期年化波動率
    
    # 🎯 凱利公式計算: β* = (μ - rf) / σ²
    full_kelly = (mu - rf_rate) / (sigma ** 2) if sigma > 0 else 0.0
    half_kelly = full_kelly * 0.5
    
    # 3. 畫面呈現結果指標
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📌 無風險利率 (rf)", f"{rf_rate:.2%}")
    col2.metric("📈 長期年化報酬率 (μ)", f"{mu:.2%}")
    col3.metric("🔥 凱利槓桿 (Full Kelly)", f"{full_kelly:.2f} 倍")
    col4.metric("🛡️ 半凱利槓桿 (Half Kelly)", f"{half_kelly:.2f} 倍")

    st.write("---")

    # 4. 判斷多空狀態
    df["SMA"] = df["Close"].rolling(sma_window).mean()
    latest_price = df['Close'].iloc[-1]
    latest_sma = df['SMA'].iloc[-1]
    
    if latest_price > latest_sma:
        st.success(f"🟢 目前 0050 價格 ({latest_price:.2f}) 在均線 ({latest_sma:.2f}) 之上：環境健康，可執行槓桿策略。")
    else:
        st.warning(f"🔴 目前 0050 價格 ({latest_price:.2f}) 在均線 ({latest_sma:.2f}) 之下：處於空頭，請注意槓桿風險。")

    # 5. 繪製 CAGR 效能曲線 (拋物線)
    # X軸：槓桿倍數 (從 0 到 6)
    betas = np.linspace(0, 6, 300)
    # 連續時間 CAGR 公式: g(β) = rf + β(μ - rf) - 0.5 * β² * σ²
    cagr_values = rf_rate + betas * (mu - rf_rate) - 0.5 * (betas**2) * (sigma**2)
    
    fig = go.Figure()

    # 畫出拋物線
    fig.add_trace(go.Scatter(x=betas, y=cagr_values, mode='lines', name='預期長期 CAGR', line=dict(color='blue', width=3)))

    # 標註紅點 (無風險利率)
    fig.add_trace(go.Scatter(x=[0], y=[rf_rate], mode='markers+text', name='無風險利率', 
                             marker=dict(color='red', size=12), text=["rf"], textposition="bottom left"))

    # 標註綠點 (1倍原資產)
    cagr_1x = rf_rate + 1 * (mu - rf_rate) - 0.5 * (1**2) * (sigma**2)
    fig.add_trace(go.Scatter(x=[1], y=[cagr_1x], mode='markers+text', name='1X 原型資產', 
                             marker=dict(color='green', size=12), text=["1X"], textposition="top center"))

    # 標註藍點 (全凱利頂點)
    cagr_full = rf_rate + full_kelly * (mu - rf_rate) - 0.5 * (full_kelly**2) * (sigma**2)
    fig.add_trace(go.Scatter(x=[full_kelly], y=[cagr_full], mode='markers+text', name='全凱利 (頂點)', 
                             marker=dict(color='orange', size=15, symbol='star'), text=["Full Kelly"], textposition="top center"))

    # 標註半凱利點
    cagr_half = rf_rate + half_kelly * (mu - rf_rate) - 0.5 * (half_kelly**2) * (sigma**2)
    fig.add_trace(go.Scatter(x=[half_kelly], y=[cagr_half], mode='markers+text', name='半凱利', 
                             marker=dict(color='purple', size=12, symbol='diamond'), text=["Half Kelly"], textposition="top left"))

    # 區分顏色區域 (仿照您的第二張圖)
    # 積極區 (0 到 Full Kelly)
    fig.add_vrect(x0=0, x1=full_kelly, fillcolor="lightgreen", opacity=0.2, layer="below", line_width=0)
    # 低效區 (Full Kelly 以上)
    fig.add_vrect(x0=full_kelly, x1=6, fillcolor="salmon", opacity=0.2, layer="below", line_width=0)

    fig.update_layout(
        title=f"0050 槓桿效能拋物線 (基於長期波動率 {sigma:.2%})",
        xaxis_title="每日調整槓桿倍數 (Leverage Beta)",
        yaxis_title="年化複合增長率 (CAGR)",
        template="plotly_white",
        height=500,
        yaxis=dict(tickformat=".1%"),
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    st.info("""
    **💡 曲線解讀說明：**
    1. **頂點 (Full Kelly)：** 數學上能讓錢長最快的地方。
    2. **半凱利 (Half Kelly)：** 位於左側坡道，回報雖然比頂點少一點，但風險大幅降低，是實戰中最推薦的平衡點。
    3. **1X 點：** 如果你的 1X 點已經在頂點右邊，代表 0050 本身波動過大，連不開槓桿都嫌多（這在 0050 歷史上很少發生）。
    4. **紅色區域：** 槓桿開過頭，複利內耗開始殺死你的本金，請絕對避開。
    """)
