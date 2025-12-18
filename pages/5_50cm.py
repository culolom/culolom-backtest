import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 進階訊號過濾版", layout="wide")

# ===============================================================
# ETF 對照表與資料抓取
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {"symbol": "0050.TW", "lev": "00631L.TW"},
    "🇺🇸 美股 - QQQ (納斯達克100)": {"symbol": "QQQ", "lev": "TQQQ"},
    "🇺🇸 美股 - SPY (標普500)": {"symbol": "SPY", "lev": "UPRO"}
}

@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=2)
    df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs("Close", axis=1, level=0) if "Close" in df.columns.levels[0] else df.xs("Adj Close", axis=1, level=0)
    return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()

# ===============================================================
# 側邊欄：濾網設定
# ===============================================================
with st.sidebar:
    st.title("🐹 倉鼠策略濾網")
    selected_proto = st.selectbox("選擇原型 ETF", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期", 10, 500, 200)
    
    st.divider()
    st.markdown("### 🛡️ 假訊號過濾器")
    buffer_pct = st.slider("緩衝區幅度 (%)", 0.0, 5.0, 2.0, 0.5) / 100
    slope_period = st.slider("斜率參考天數", 5, 60, 20)
    
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表總高度", 600, 2000, 1000)

# ===============================================================
# 主運算區
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 基礎指標
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    df_raw["Gap"] = (df_raw["Base"] - df_raw["SMA"]) / df_raw["SMA"]
    df_raw["Ret12M"] = df_raw["Base"].pct_change(periods=252) * 100
    
    # 計算均線斜率 (SMA Slope)
    df_raw["SMA_Slope"] = df_raw["SMA"].pct_change(periods=slope_period) * 100
    
    # --- 關鍵：訊號過濾邏輯 ---
    # 只有當 價格 > SMA * (1 + buffer) 且 斜率 > 0 才視為真突破
    df_raw["Raw_Signal"] = np.where(df_raw["Base"] > df_raw["SMA"], 1, 0)
    
    # 過濾後的訊號 (考慮緩衝區)
    df_raw["Filtered_Signal"] = 0
    # 多頭確認：價格站上緩衝區 且 均線不向下
    df_raw.loc[(df_raw["Base"] > df_raw["SMA"] * (1 + buffer_pct)), "Filtered_Signal"] = 1
    # 空頭確認：價格跌破緩衝區 且 均線不向上
    df_raw.loc[(df_raw["Base"] < df_raw["SMA"] * (1 - buffer_pct)), "Filtered_Signal"] = 0
    
    df_raw["Action"] = df_raw["Filtered_Signal"].diff()

    # 裁切顯示區間
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    
    # ===============================================================
    # 建立聯動圖表
    # ===============================================================
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        subplot_titles=("1. 均線斜率 (SMA Slope %) - 趨勢強度", "2. 價格與過濾後訊號 (紅色/綠色標註)", "3. 12M 報酬率 (動能確認)"),
        specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": True}]]
    )

    # 圖 1: 斜率 (Slope) - 判斷大環境
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="SMA 斜率", fill='tozeroy', line=dict(color='gray')), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # 圖 2: 價格與過濾訊號
    # 繪製緩衝區
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"]*(1+buffer_pct), line=dict(color='green', dash='dot', width=1), name="緩衝上限", opacity=0.3), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"]*(1-buffer_pct), line=dict(color='red', dash='dot', width=1), name="緩衝下限", opacity=0.3), row=2, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name="原型價", line=dict(color='blue', width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="200SMA", line=dict(color='orange', width=3)), row=2, col=1)

    # 標註過濾後的真實進出場點
    buy_pts = df[df["Action"] == 1]
    sell_pts = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy_pts.index, y=buy_pts["Base"], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name='真突破確認'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell_pts.index, y=sell_pts["Base"], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name='真跌破確認'), row=2, col=1)

    # 圖 3: 12M Return
    fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M"], name="12M 報酬%", line=dict(color='purple')), row=3, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=3, col=1)

    fig.update_layout(height=chart_height, hovermode="x unified", showspikes=True)
    st.plotly_chart(fig, use_container_width=True)

    # 績效摘要表
    st.subheader("📋 策略分析報告")
    st.write(f"在 {buffer_pct*100}% 緩衝區設定下，共偵測到 {len(buy_pts)} 次趨勢轉換。")
