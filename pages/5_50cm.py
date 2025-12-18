import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 假訊號深度過濾", layout="wide")

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
    # 多抓一年資料計算均線
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
# 側邊欄：假訊號過濾器參數
# ===============================================================
with st.sidebar:
    st.markdown("### 🐹 假訊號過濾設定")
    selected_proto = st.selectbox("分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    # 核心過濾參數
    buffer_pct = st.slider("1. 緩衝區門檻 (%)", 0.0, 5.0, 2.0, 0.5) / 100
    slope_days = st.slider("2. 均線斜率參考天數", 5, 60, 20)
    
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表高度", 600, 1500, 800)

# ===============================================================
# 主運算與過濾邏輯
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 指標計算
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    # 斜率計算：過去 N 天均線的變動率
    df_raw["SMA_Slope"] = (df_raw["SMA"] - df_raw["SMA"].shift(slope_days)) / df_raw["SMA"].shift(slope_days) * 100
    
    # 核心：帶緩衝區的訊號判斷
    df_raw["Signal"] = np.nan
    # 突破確認：高於緩衝區上限
    df_raw.loc[df_raw["Base"] > df_raw["SMA"] * (1 + buffer_pct), "Signal"] = 1
    # 跌破確認：低於緩衝區下限
    df_raw.loc[df_raw["Base"] < df_raw["SMA"] * (1 - buffer_pct), "Signal"] = 0
    # 在緩衝區內保持原樣 (避免雜訊)
    df_raw["Signal"] = df_raw["Signal"].ffill().fillna(0)
    
    df_raw["Action"] = df_raw["Signal"].diff()

    # 裁切回顯示區間
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    b_name = selected_proto.split(" ")[2]

    # ===============================================================
    # 建立 2 層聯動子圖 (移除 12M Ret, 重分配比例)
    # ===============================================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(
            f"🟢 均線斜率 (%): > 0 代表長期上升趨勢", 
            f"🔵 價格與過濾後訊號 (已包含 {buffer_pct*100}% 緩衝門檻)"
        ),
        row_heights=[0.3, 0.7],  # 讓價格圖佔據更大的空間
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
    )

    # --- 圖 1: 斜率 (Slope) ---
    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA_Slope"], 
        name="SMA 斜率", 
        fill='tozeroy', 
        line=dict(color='gray', width=1)
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # --- 圖 2: 價格與過濾訊號 (雙軸) ---
    # 1. 緩衝區陰影
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"]*(1+buffer_pct), line=dict(width=0), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["SMA"]*(1-buffer_pct), 
        line=dict(width=0), 
        fill='tonexty', 
        fillcolor='rgba(255, 255, 0, 0.1)', # 黃色半透明緩衝區
        name="緩衝區(Buffer)"
    ), row=2, col=1)
    
    # 2. 價格與均線
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{b_name} 價", line=dict(color='blue', width=1.5)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color='orange', width=3)), row=2, col=1, secondary_y=False)
    
    # 3. 槓桿價格 (右軸)
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name="槓桿ETF", opacity=0.2, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)

    # 4. 標註訊號
    buy = df[df["Action"] == 1]
    sell = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy.index, y=buy["Base"], mode='markers', marker=dict(symbol='triangle-up', size=18, color='green'), name='真突破'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell.index, y=sell["Base"], mode='markers', marker=dict(symbol='triangle-down', size=18, color='red'), name='真跌破'), row=2, col=1)

    # 圖表設定
    fig.update_layout(height=chart_height, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="dot")
    fig.update_yaxes(title_text="斜率 (%)", row=1, col=1)
    fig.update_yaxes(title_text="原型價", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="槓桿價", row=2, col=1, secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

    # 決策輔助資訊
    st.subheader("💡 假訊號判斷指引")
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"""
        **如何辨識假跌破？**
        1. 股價雖然跌破橙線，但尚未跌破 **黃色緩衝區下緣**。
        2. 上方 **SMA 斜率** 仍為正值（灰色區域在 0 以上）。
        3. 若符合上述兩點，該訊號極可能是假跌破（震倉）。
        """)
    with c2:
        st.warning(f"""
        **如何辨識假突破？**
        1. 股價穿過橙線，但未站穩 **黃色緩衝區上限**。
        2. 上方 **SMA 斜率** 仍為負值（灰色區域在 0 以下）。
        3. 這通常只是空頭市場的跌深反彈，不要急著進場 00631L。
        """)

else:
    st.info("👆 請於左側調整濾網門檻，並觀察三角形訊號的變化。")
