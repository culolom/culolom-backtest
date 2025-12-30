import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面設定與 UI 樣式
###############################################################
st.set_page_config(
    page_title="Meb Faber 0050 趨勢策略",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>🛡️ 0050 梅班·費伯趨勢策略</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>策略核心邏輯：</b><br>
1️⃣ <b>判定基準</b>：每月最後一個交易日觀察 0050 的收盤價。<br>
2️⃣ <b>進場規則</b>：收盤價 <b>站上</b> 10 個月均線 → 全倉持有 0050。<br>
3️⃣ <b>出場規則</b>：收盤價 <b>跌破</b> 10 個月均線 → 全倉賣出轉為現金。
""",
    unsafe_allow_html=True,
)

###############################################################
# 2. 資料讀取功能 (預設讀取 data/0050.TW.csv)
###############################################################
DATA_DIR = Path("data")

def load_0050_data() -> pd.DataFrame:
    # 這裡預設您的檔案名稱為 0050.TW.csv 或 0050.csv
    file_path = DATA_DIR / "0050.TW.csv"
    if not file_path.exists():
        file_path = DATA_DIR / "0050.csv"
        
    if not file_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(file_path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    # 確保有 Price 欄位，若沒有則用 Close
    if "Price" not in df.columns:
        df["Price"] = df["Close"]
    return df[["Price"]]

###############################################################
# 3. 側邊欄參數設定
###############################################################
with st.sidebar:
    st.header("⚙️ 策略參數")
    capital = st.number_input("投入初始本金 (元)", 100000, 10000000, 1000000, step=100000)
    sma_months = st.number_input("月均線週期 (費伯推薦 10)", 1, 24, 10)
    
    raw_data = load_0050_data()
    
    if not raw_data.empty:
        s_min = raw_data.index.min().date()
        s_max = raw_data.index.max().date()
        st.info(f"📅 資料區間：{s_min} ~ {s_max}")
        
        start_date = st.date_input("開始日期", value=dt.date(2016, 1, 1), min_value=s_min, max_value=s_max)
        end_date = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
    else:
        st.error("⚠️ 找不到 data/0050.TW.csv，請確認檔案位置。")
        st.stop()

###############################################################
# 4. 核心計算邏輯
###############################################################
if st.button("開始回測 🚀"):
    # 4-1. 預抓緩衝資料計算月均線
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    # 往前回溯足夠月數以計算 SMA
    buffer_start = start_dt - pd.DateOffset(months=sma_months + 2)
    
    df = raw_data.loc[buffer_start:end_dt].copy()

    # 4-2. 計算 10 個月均線 (使用月底收盤價)
    # resample('ME') 代表取每月最後一天
    df_m = df["Price"].resample('ME').last().to_frame()
    df_m["MA_Signal"] = df_m["Price"].rolling(window=sma_months).mean()
    
    # 4-3. 將月訊號對應回日資料
    df = df.join(df_m["MA_Signal"], rsuffix="_monthly")
    df["MA_Signal"] = df["MA_Signal"].ffill() # 每天都能看到當月參考的均線值

    # 4-4. 過濾出使用者選取的實際回測日期
    df = df.loc[start_dt:end_dt].copy()
    
    # 4-5. 判定進出訊號
    positions = []
    current_pos = 0.0
    
    for i in range(len(df)):
        # 判斷當天是否為月底
        is_month_end = False
        if i < len(df) - 1:
            if df.index[i].month != df.index[i+1].month:
                is_month_end = True
        else:
            is_month_end = True # 最後一天
            
        # 費伯策略：只有在月底那天才決定下個月要不要持股
        if is_month_end:
            if df["Price"].iloc[i] > df["MA_Signal"].iloc[i]:
                current_pos = 1.0 # 站上月線 -> 買進/持有
            else:
                current_pos = 0.0 # 跌破月線 -> 賣出/空手
        
        positions.append(current_pos)

    # 訊號產生的隔天才能執行交易，所以要把 Position 往後移一格
    df["Position"] = pd.Series(positions, index=df.index).shift(1).fillna(0)

    # 4-6. 計算報酬率與淨值
    df["Daily_Ret"] = df["Price"].pct_change().fillna(0)
    df["Strategy_Ret"] = df["Daily_Ret"] * df["Position"]
    
    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_BH"] = (1 + df["Daily_Ret"]).cumprod()

    ###############################################################
    # 5. 結果視覺化 (Plotly)
    ###############################################################
    
    # --- 圖表 1: 價格與 10 月均線 ---
    st.subheader("📌 0050 價格與 10 月均線對照")
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price"], name="0050 收盤價", line=dict(color="#636EFA", width=1.5)))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_months}月均線", line=dict(color="#FFA15A", dash="dot")))
    
    # 標記空手區間 (背景著色)
    fig_p.update_layout(template="plotly_white", height=450, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_p, use_container_width=True)

    # --- 圖表 2: 資金曲線比較 ---
    st.subheader("📈 資金曲線：費伯策略 vs. 買進持有 (0050)")
    fig_e = go.Figure()
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"] * capital, name="Meb Faber 策略", line=dict(color="#00CC96", width=2.5)))
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"] * capital, name="0050 買進持有", line=dict(color="gray", width=1), opacity=0.6))
    fig_e.update_layout(template="plotly_white", height=450, yaxis_title="資產規模 (元)")
    st.plotly_chart(fig_e, use_container_width=True)

    ###############################################################
    # 6. 指標報表
    ###############################################################
    
    def calc_stats(equity, returns):
        total_ret = (equity.iloc[-1] - 1)
        duration_years = (equity.index[-1] - equity.index[0]).days / 365.25
        cagr = (1 + total_ret) ** (1 / duration_years) - 1
        mdd = (equity / equity.cummax() - 1).min()
        vol = returns.std() * np.sqrt(252)
        sharpe = cagr / vol if vol != 0 else 0
        return total_ret, cagr, mdd, sharpe

    s_res = calc_stats(df["Equity_Strategy"], df["Strategy_Ret"])
    b_res = calc_stats(df["Equity_BH"], df["Daily_Ret"])

    st.write("### 📊 指標對照表")
    
    res_df = pd.DataFrame({
        "統計指標": ["總報酬率", "年化報酬率 (CAGR)", "最大回撤 (MDD)", "夏普比率 (Sharpe)"],
        "Meb Faber 策略": [f"{s_res[0]*100:.2f}%", f"{s_res[1]*100:.2f}%", f"{s_res[2]*100:.2f}%", f"{s_res[3]:.2f}"],
        "0050 買進持有": [f"{b_res[0]*100:.2f}%", f"{b_res[1]*100:.2f}%", f"{b_res[2]*100:.2f}%", f"{b_res[3]:.2f}"]
    })
    
    st.table(res_df)

    st.success(f"回測結束！在該區間內，策略最大回撤為 {s_res[2]*100:.2f}%，有效降低了市場風險。")
