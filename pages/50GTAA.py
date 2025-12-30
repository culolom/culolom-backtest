import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面與字型設定
###############################################################
st.set_page_config(page_title="Meb Faber 0050 回測", page_icon="📈", layout="wide")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 Meb Faber 策略資產分配 (0050 專用)</h1>", unsafe_allow_html=True)

st.markdown("""
<b>策略邏輯：</b><br>
1️⃣ <b>週期</b>：以「月」為單位。每月最後一個交易日觀察 0050 收盤價。<br>
2️⃣ <b>均線</b>：計算 10 個月的移動平均線 (10-Month SMA)。<br>
3️⃣ <b>進場</b>：月底收盤 > 10月線 → 下個月持有 0050。<br>
4️⃣ <b>避險</b>：月底收盤 < 10月線 → 下個月空手（換成現金）。
""", unsafe_allow_html=True)

###############################################################
# 2. 資料讀取功能
###############################################################
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# 固定標的為 0050
target_symbol = "0050.TW"
target_label = "0050 元大台灣50"

###############################################################
# 3. UI 參數輸入
###############################################################
with st.sidebar:
    st.header("⚙️ 參數設定")
    capital = st.number_input("投入本金 (元)", 100000, 10000000, 1000000, step=100000)
    sma_month = st.number_input("月均線週期 (建議 10)", 1, 24, 10)
    
    # 讀取資料以獲取日期範圍
    raw_data = load_csv("0050.TW")
    if not raw_data.empty:
        s_min = raw_data.index.min().date()
        s_max = raw_data.index.max().date()
        start_date = st.date_input("開始日期", value=dt.date(2016, 1, 1), min_value=s_min, max_value=s_max)
        end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
    else:
        st.error("找不到 0050.TW.csv 資料")
        st.stop()

###############################################################
# 4. 核心回測邏輯
###############################################################
if st.button("開始執行回測 🚀"):
    # 預抓足夠的資料來計算月線 (緩衝一年)
    start_buffer = pd.to_datetime(start_date) - pd.DateOffset(months=sma_month + 2)
    df = raw_data.loc[start_buffer:pd.to_datetime(end_date)].copy()

    # --- 月線信號計算 ---
    # 抓取每個月最後一天的價格
    df_m = df["Price"].resample('ME').last().to_frame()
    df_m["MA_Signal"] = df_m["Price"].rolling(sma_month).mean()
    
    # 將月訊號同步回日資料 (ffill 確保每天都知道當月的 10MA 是多少)
    df = df.join(df_m["MA_Signal"], rsuffix="_monthly")
    df["MA_Signal"] = df["MA_Signal"].ffill()

    # 切回使用者選取的範圍
    df = df.loc[pd.to_datetime(start_date):pd.to_datetime(end_date)].copy()
    
    # 計算日報酬
    df["Daily_Return"] = df["Price"].pct_change().fillna(0)

    # --- 模擬交易邏輯 ---
    positions = [0.0] * len(df)
    current_pos = 0.0
    
    for i in range(len(df)):
        # 取得今天日期
        today = df.index[i]
        # 判定今天是否為月底交易日
        is_month_end = False
        if i < len(df) - 1:
            if df.index[i].month != df.index[i+1].month:
                is_month_end = True
        else:
            is_month_end = True # 最後一天也算月底
            
        # 費伯規則：月底才調整
        if is_month_end:
            if df["Price"].iloc[i] > df["MA_Signal"].iloc[i]:
                current_pos = 1.0 # 持有
            else:
                current_pos = 0.0 # 空手
        
        positions[i] = current_pos

    # 寫入持倉 (注意：訊號是今天月底觸發，明天才開始有部位收益，所以要 shift)
    df["Position"] = pd.Series(positions, index=df.index).shift(1).fillna(0)
    
    # --- 計算淨值 ---
    # 策略淨值 (LRS 版即 Meb Faber 版)
    df["Strategy_Return"] = df["Daily_Return"] * df["Position"]
    df["Equity_Strategy"] = (1 + df["Strategy_Return"]).cumprod()
    # 基準淨值 (Buy & Hold 0050)
    df["Equity_BH"] = (1 + df["Daily_Return"]).cumprod()

    ###############################################################
    # 5. 線圖渲染 (Plotly)
    ###############################################################
    st.subheader("📌 價格與均線對照圖")
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price"], name="0050 收盤價", line=dict(color="#636EFA")))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_month}月均線", line=dict(color="#FFA15A", dash="dot")))
    fig_price.update_layout(template="plotly_white", height=400, hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_price, use_container_width=True)

    st.subheader("📈 資金曲線比較 (淨值)")
    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="Meb Faber 策略", line=dict(width=3, color="#00CC96")))
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"], name="0050 買進持有", line=dict(width=1, color="gray")))
    fig_equity.update_layout(template="plotly_white", height=450, yaxis=dict(title="淨值 (從 1.0 開始)"))
    st.plotly_chart(fig_equity, use_container_width=True)

    ###############################################################
    # 6. KPI 報表計算
    ###############################################################
    def get_metrics(equity_series, return_series):
        total_ret = (equity_series.iloc[-1] - 1)
        ann_ret = (1 + total_ret) ** (252 / len(equity_series)) - 1
        mdd = (equity_series / equity_series.cummax() - 1).min()
        vol = return_series.std() * np.sqrt(252)
        sharpe = ann_ret / vol if vol != 0 else 0
        return total_ret, ann_ret, mdd, sharpe

    m_strat = get_metrics(df["Equity_Strategy"], df["Strategy_Return"])
    m_bh = get_metrics(df["Equity_BH"], df["Daily_Return"])

    # 顯示 KPI 卡片
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("策略總報酬", f"{m_strat[0]*100:.2f}%", f"{(m_strat[0]-m_bh[0])*100:.1f}% vs BH")
    c2.metric("年化報酬率", f"{m_strat[1]*100:.2f}%")
    c3.metric("最大回撤 (MDD)", f"{m_strat[2]*100:.2f}%")
    c4.metric("夏普比率 (Sharpe)", f"{m_strat[3]:.2f}")

    # 報表表格
    st.write("### 📊 詳細指標對照")
    metrics_df = pd.DataFrame({
        "指標": ["總報酬率", "年化報酬率", "最大回撤 (MDD)", "年化波動率", "夏普比率"],
        "Meb Faber 策略": [
            f"{m_strat[0]*100:.2f}%", f"{m_strat[1]*100:.2f}%", 
            f"{m_strat[2]*100:.2f}%", f"{df['Strategy_Return'].std()*np.sqrt(252)*100:.2f}%", f"{m_strat[3]:.2f}"
        ],
        "0050 買進持有": [
            f"{m_bh[0]*100:.2f}%", f"{m_bh[1]*100:.2f}%", 
            f"{m_bh[2]*100:.2f}%", f"{df['Daily_Return'].std()*np.sqrt(252)*100:.2f}%", f"{m_bh[3]:.2f}"
        ]
    })
    st.table(metrics_df)

    st.success("回測完成！您可以觀察到，Meb Faber 策略在 2022 年或空頭排列時，是否成功透過月線避開大幅回檔。")
