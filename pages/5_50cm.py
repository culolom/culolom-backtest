import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 訊號過濾版", layout="wide")

# ===============================================================
# ETF 對照表
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {"symbol": "0050.TW", "lev": "00631L.TW"},
    "🇺🇸 美股 - QQQ (納斯達克100)": {"symbol": "QQQ", "lev": "TQQQ"},
    "🇺🇸 美股 - SPY (標普500)": {"symbol": "SPY", "lev": "UPRO"}
}

@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    # 多抓兩年資料以利計算 SMA 與 12M Return
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=2)
    try:
        df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
        if df.empty: return None
        # 處理 yfinance 可能產生的 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            if "Adj Close" in df.columns.levels[0]:
                df = df["Adj Close"]
            else:
                df = df["Close"]
        return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return None

# ===============================================================
# 側邊欄：濾網與參數設定
# ===============================================================
with st.sidebar:
    st.markdown("### 🐹 戰情室控制台")
    selected_proto = st.selectbox("選擇分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    st.markdown("### 🛡️ 假訊號過濾設定")
    # 增加緩衝區，減少假訊號頻繁進出
    buffer_pct = st.slider("緩衝區門檻 (%)", 0.0, 5.0, 2.0, 0.5) / 100
    slope_days = st.slider("均線斜率參考天數", 5, 60, 20)
    
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表總高度", 600, 1800, 1000)

# ===============================================================
# 核心運算
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 1. 基礎指標計算
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    df_raw["Gap"] = (df_raw["Base"] - df_raw["SMA"]) / df_raw["SMA"]
    df_raw["Ret12M"] = df_raw["Base"].pct_change(periods=252) * 100
    
    # 2. 均線斜率 (判斷大趨勢是否轉向)
    df_raw["SMA_Slope"] = df_raw["SMA"].diff(slope_days) / df_raw["SMA"].shift(slope_days) * 100
    
    # 3. 過濾訊號邏輯 (考慮緩衝區)
    df_raw["Signal"] = np.nan
    # 價格 > SMA * (1 + buffer) --> 多頭
    df_raw.loc[df_raw["Base"] > df_raw["SMA"] * (1 + buffer_pct), "Signal"] = 1
    # 價格 < SMA * (1 - buffer) --> 空頭
    df_raw.loc[df_raw["Base"] < df_raw["SMA"] * (1 - buffer_pct), "Signal"] = 0
    # 緩衝區內的價格保持前一個狀態 (Forward Fill)
    df_raw["Signal"] = df_raw["Signal"].ffill().fillna(0)
    
    # 4. 偵測進出場點
    df_raw["Action"] = df_raw["Signal"].diff()

    # 裁切回使用者選取區間
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    b_name = selected_proto.split(" ")[2]
    l_name = "槓桿ETF"

    # ===============================================================
    # 建立 3 層聯動子圖
    # ===============================================================
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=(
            f"1. {sma_window}SMA 斜率 (趨勢強度指標)", 
            "2. 價格走勢與過濾訊號 (雙軸)", 
            "3. 近 12 個月滾動報酬率 (%)"
        ),
        specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": True}]]
    )

    # --- 圖 1: 斜率 (Slope) ---
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="SMA 斜率", fill='tozeroy', line=dict(color='gray')), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # --- 圖 2: 價格與過濾訊號 (雙軸) ---
    # 繪製緩衝區陰影 (更直觀判斷假訊號)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"]*(1+buffer_pct), line=dict(width=0), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"]*(1-buffer_pct), line=dict(width=0), fill='tonexty', fillcolor='rgba(255,255,0,0.1)', name="緩衝區"), row=2, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{b_name} 價", line=dict(color='blue', width=1.5)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="200SMA", line=dict(color='orange', width=3)), row=2, col=1, secondary_y=False)
    
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{l_name} 價", opacity=0.3, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)

    # 標註經過濾後的進出場點
    buy = df[df["Action"] == 1]
    sell = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy.index, y=buy["Base"], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name='突破買點'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell.index, y=sell["Base"], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name='跌破賣點'), row=2, col=1)

    # --- 圖 3: 12M 報酬率 (動能) ---
    fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M"], name="12M 報酬%", line=dict(color='purple', width=2)), row=3, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=3, col=1)

    # ===============================================================
    # 修正後的圖表設定 (解決 showspikes 報錯)
    # ===============================================================
    fig.update_layout(
        height=chart_height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    # 關鍵修正：使用 update_xaxes 與 update_yaxes
    fig.update_xaxes(
        showspikes=True, 
        spikemode="across", 
        spikesnap="cursor", 
        spikethickness=1, 
        spikedash="dot"
    )
    fig.update_yaxes(showspikes=True)

    st.plotly_chart(fig, use_container_width=True)

    # 數據指標卡
    c1, c2, c3 = st.columns(3)
    c1.metric("當前乖離率", f"{df['Gap'].iloc[-1]*100:.1f}%")
    c2.metric("SMA 斜率", f"{df['SMA_Slope'].iloc[-1]:.2f}%")
    c3.metric("12M 報酬率", f"{df['Ret12M'].iloc[-1]:.1f}%")

else:
    st.info("👆 請於左側選擇參數並開始分析")
