import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="0050 雙維度凱利戰情室", layout="wide")
st.title("📊 0050 雙維度凱利公式動態戰情室")

# 1. 參數設定區
col_in1, col_in2 = st.columns(2)
with col_in1:
    sma_window = st.number_input("設定動態均線天數 (SMA Filter)", min_value=5, max_value=240, value=200, step=5)
with col_in2:
    rf_rate = st.number_input("無風險利率 / 資金成本 (%)", min_value=0.0, max_value=15.0, value=2.0, step=0.1) / 100

# 2. 讀取資料
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
    
    # 🎯 維度一：長期歷史總體數據 (All History)
    mu_all = df["Daily_Return"].mean() * 252
    sigma_all = df["Daily_Return"].std() * np.sqrt(252)
    
    full_kelly_all = (mu_all - rf_rate) / (sigma_all ** 2) if sigma_all > 0 else 0.0
    half_kelly_all = full_kelly_all * 0.5
    
    # 🎯 維度二：特定均線多頭區間數據 (> SMA)
    df["SMA"] = df["Close"].rolling(sma_window).mean()
    bull_df = df[df["Close"] > df["SMA"]].dropna()
    
    if not bull_df.empty:
        mu_bull = bull_df["Daily_Return"].mean() * 252
        sigma_bull = bull_df["Daily_Return"].std() * np.sqrt(252)
        
        full_kelly_bull = (mu_bull - rf_rate) / (sigma_bull ** 2) if sigma_bull > 0 else 0.0
        half_kelly_bull = full_kelly_bull * 0.5
    else:
        mu_bull, sigma_bull, full_kelly_bull, half_kelly_bull = np.nan, np.nan, 0.0, 0.0

    # 3. 呈現看板結果 (大字級指標卡區分兩列)
    st.subheader("🌐 維度一：長期歷史總體常態指標 ( Strategic Baseline )")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("長期總報酬率 (μ_all)", f"{mu_all:.2%}")
    t2.metric("長期總波動率 (σ_all)", f"{sigma_all:.2%}")
    t3.metric("總體 凱利槓桿", f"{full_kelly_all:.2f} 倍")
    t4.metric("總體 半凱利槓桿", f"{half_kelly_all:.2f} 倍")
    
    st.write("---")
    st.subheader(f"⚡ 維度二：價格在 {sma_window}MA 以上之多頭波段指標 ( Tactical Filter )")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric(f"{sma_window}MA多頭報酬率 (μ_bull)", f"{mu_bull:.2%}" if not np.isnan(mu_bull) else "—")
    b2.metric(f"{sma_window}MA多頭波動率 (σ_bull)", f"{sigma_bull:.2%}" if not np.isnan(sigma_bull) else "—")
    b3.metric(f"{sma_window}MA 凱利槓桿", f"{full_kelly_bull:.2f} 倍")
    b4.metric(f"{sma_window}MA 半凱利槓桿", f"{half_kelly_bull:.2f} 倍")

    st.write("---")

    # 4. 當前多空狀態判斷
    latest_price = df['Close'].iloc[-1]
    latest_sma = df['SMA'].iloc[-1]
    if latest_price > latest_sma:
        st.success(f"🟢 今日最新狀態 ({df.index[-1].strftime('%Y-%m-%d')})：0050 價格 ({latest_price:.2f}) 在 {sma_window}MA ({latest_sma:.2f}) 之上。目前處於多頭波段，可參考【維度二】進行積極配置。")
    else:
        st.warning(f"🔴 今日最新狀態 ({df.index[-1].strftime('%Y-%m-%d')})：0050 價格 ({latest_price:.2f}) 在 {sma_window}MA ({latest_sma:.2f}) 之下。目前處於逆風空頭波段，請降低槓桿或改採【維度一】的保守半凱利。")

    # 5. 繪製雙曲線圖進行視覺化比對
    betas = np.linspace(0, 6, 300)
    cagr_all = rf_rate + betas * (mu_all - rf_rate) - 0.5 * (betas**2) * (sigma_all**2)
    
    fig = go.Figure()
    # 畫出長期總體常態曲線 (實線)
    fig.add_trace(go.Scatter(x=betas, y=cagr_all, mode='lines', name='維度一：長期歷史常態曲線', line=dict(color='#636EFA', width=3)))
    fig.add_trace(go.Scatter(x=[full_kelly_all], y=[rf_rate + full_kelly_all * (mu_all - rf_rate) - 0.5 * (full_kelly_all**2) * (sigma_all**2)], 
                             mode='markers', name='總體 凱利頂點', marker=dict(color='#636EFA', size=14, symbol='star')))
    fig.add_trace(go.Scatter(x=[half_kelly_all], y=[rf_rate + half_kelly_all * (mu_all - rf_rate) - 0.5 * (half_kelly_all**2) * (sigma_all**2)], 
                             mode='markers', name='總體 半凱利點', marker=dict(color='#636EFA', size=11, symbol='diamond')))

    # 畫出均線多頭波段曲線 (虛線)
    if not np.isnan(sigma_bull):
        cagr_bull = rf_rate + betas * (mu_bull - rf_rate) - 0.5 * (betas**2) * (sigma_bull**2)
        fig.add_trace(go.Scatter(x=betas, y=cagr_bull, mode='lines', name=f'維度二：{sma_window}MA 多頭區間曲線', line=dict(color='#EF553B', width=3, dash='dash')))
        fig.add_trace(go.Scatter(x=[full_kelly_bull], y=[rf_rate + full_kelly_bull * (mu_bull - rf_rate) - 0.5 * (full_kelly_bull**2) * (sigma_bull**2)], 
                                 mode='markers', name=f'{sma_window}MA 凱利頂點', marker=dict(color='#EF553B', size=14, symbol='star')))
        fig.add_trace(go.Scatter(x=[half_kelly_bull], y=[rf_rate + half_kelly_bull * (mu_bull - rf_rate) - 0.5 * (half_kelly_bull**2) * (sigma_bull**2)], 
                                 mode='markers', name=f'{sma_window}MA 半凱利點', marker=dict(color='#EF553B', size=11, symbol='diamond')))

    # 標註1X位置與基準線
    fig.add_trace(go.Scatter(x=[1], y=[rf_rate + 1 * (mu_all - rf_rate) - 0.5 * (1**2) * (sigma_all**2)], mode='markers', name='1X 基準原資產', marker=dict(color='black', size=10)))

    fig.update_layout(
        title="0050 雙維度槓桿效能曲線對照圖",
        xaxis_title="每日重置名義槓桿倍數 (Leverage Beta)",
        yaxis_title="幾何預期複合增長率 (CAGR)",
        template="plotly_white",
        height=520,
        yaxis=dict(tickformat=".1%"),
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    st.info(f"""
    **💡 雙維度戰術實戰搭配指引：**
    * **當綠燈亮起時（價格在均線上）：** 市場正處於強勢期，【維度二】的橘紅色虛線往往會因為多頭時波動率被壓縮（$\sigma$ 變小）、回報率被拉高（$\mu$ 變大）而向上大幅擴張，算出較高的槓桿倍數。此時，如果您要採用最保險的策略，可以直接將槓桿拉到**「維度二的半凱利槓桿」**（通常會剛好落在 1.5 ~ 2.5 倍左右，極度適合搭配信貸持有 00631L）。
    * **當紅燈亮起時（價格在均線下）：** 市場已經轉弱，請立刻無視維度二的數字，並將槓桿無條件撤回**【維度一】的半凱利以下（大約 1.0 倍以下）**，甚至換回現金或定存，藉此避開死亡交叉後的系統性暴跌與內耗損耗。
    """)
