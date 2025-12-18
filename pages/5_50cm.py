import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 趨勢慣性分析", layout="wide")

# ===============================================================
# ETF 對照表與資料抓取
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {"symbol": "0050.TW", "lev": "00631L.TW"},
    "🇺🇸 美股 - QQQ (納斯達克100)": {"symbol": "QQQ", "lev": "TQQQ"},
    "🇺🇸 美股 - SPY (標普500)": {"symbol": "SPY", "lev": "UPRO"}
    "比特幣": {"symbol": "btc-usd", "lev": "btc-usd"}
}

@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    # 多抓一年資料計算均線與斜率
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=1)
    try:
        df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs("Close", axis=1, level=0) if "Close" in df.columns.levels[0] else df.xs("Adj Close", axis=1, level=0)
        return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return None

# ===============================================================
# 側邊欄設定
# ===============================================================
with st.sidebar:
    st.markdown("### 🐹 趨勢過濾參數")
    selected_proto = st.selectbox("分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    # 你的核心發現：斜率門檻
    slope_days = st.slider("斜率計算天數", 5, 60, 20)
    buy_slope_limit = -2.0  # 突破時斜率門檻
    sell_slope_limit = 2.0  # 跌破時斜率門檻
    
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表高度", 600, 1500, 850)

# ===============================================================
# 核心邏輯：慣性過濾訊號
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 1. 基礎指標
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    # 斜率計算 (過去 N 天的變動百分比)
    df_raw["SMA_Slope"] = (df_raw["SMA"] - df_raw["SMA"].shift(slope_days)) / df_raw["SMA"].shift(slope_days) * 100
    
    # 2. 你的核心邏輯：慣性過濾
    df_raw["Filtered_Signal"] = np.nan
    
    # [真突破]：價格 > SMA 且 斜率 > -2% (代表空頭力道已竭)
    buy_cond = (df_raw["Base"] > df_raw["SMA"]) & (df_raw["SMA_Slope"] > buy_slope_limit)
    # [真跌破]：價格 < SMA 且 斜率 < 2% (代表多頭慣性已盡)
    sell_cond = (df_raw["Base"] < df_raw["SMA"]) & (df_raw["SMA_Slope"] < sell_slope_limit)
    
    df_raw.loc[buy_cond, "Filtered_Signal"] = 1
    df_raw.loc[sell_cond, "Filtered_Signal"] = 0
    
    # 狀態保持 (直到下一個觸發訊號)
    df_raw["Filtered_Signal"] = df_raw["Filtered_Signal"].ffill().fillna(0)
    df_raw["Action"] = df_raw["Filtered_Signal"].diff()

    # 裁切回顯示區間
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    b_name = selected_proto.split(" ")[2]
    
    # --- 趨勢品質判斷邏輯 ---
    curr_slope = df["SMA_Slope"].iloc[-1]
    if curr_slope > 2: quality = "🟢 強勢多頭 (噴發期)"
    elif 0 < curr_slope <= 2: quality = "🟡 弱勢多頭 (趨勢轉折區)"
    elif -2 <= curr_slope <= 0: quality = "🟠 弱勢空頭 (築底期)"
    else: quality = "🔴 強勢空頭 (恐慌下行)"

    # ===============================================================
    # 儀表板摘要卡
    # ===============================================================
    st.subheader(f"戰情摘要：{b_name}")
    m1, m2, m3 = st.columns(3)
    m1.metric("當前均線斜率", f"{curr_slope:.2f}%")
    m2.metric("趨勢品質", quality)
    m3.metric("策略狀態", "🟢 持股" if df["Filtered_Signal"].iloc[-1] == 1 else "⚪ 觀望")

    # ===============================================================
    # 建立 2 層聯動圖表
    # ===============================================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(
            f"1. 均線斜率 (%): 確認趨勢慣性 (目前門檻: {buy_slope_limit}% / {sell_slope_limit}%)", 
            f"2. 價格走勢與『慣性過濾』訊號"
        ),
        row_heights=[0.3, 0.7],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
    )

    # 圖 1: 斜率 (Slope) - 增加 2%/-2% 的參考帶
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="SMA 斜率", fill='tozeroy', line=dict(color='gray', width=1)), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)
    # 畫出你的關鍵門檻帶
    fig.add_hrect(y0=-2, y1=2, fillcolor="yellow", opacity=0.1, line_width=0, row=1, col=1)

    # 圖 2: 價格與過濾訊號
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{b_name} 價", line=dict(color='blue', width=1.5)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color='orange', width=3)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name="槓桿ETF", opacity=0.15, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)

    # 標註你的進階過濾訊號
    buy_pts = df[df["Action"] == 1]
    sell_pts = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy_pts.index, y=buy_pts["Base"], mode='markers', marker=dict(symbol='triangle-up', size=20, color='green'), name='慣性確認突破'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell_pts.index, y=sell_pts["Base"], mode='markers', marker=dict(symbol='triangle-down', size=20, color='red'), name='慣性確認跌破'), row=2, col=1)

    # 圖表設定
    fig.update_layout(height=chart_height, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="dot")
    
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.caption(f"💡 **慣性過濾說明**：當斜率在 -2% ~ 2% 之間時，趨勢正處於『轉換慣性』，此時發生的突破或跌破最具參考價值。")

else:
    st.info("👆 請選擇參數開始量化分析")
