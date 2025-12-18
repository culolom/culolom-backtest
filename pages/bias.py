###############################################################
# app.py — ETF/個股 SMA 策略戰情室 (新增極端值警戒線)
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# 1. 頁面設定
st.set_page_config(page_title="SMA 量化戰情室", layout="wide")

# ===============================================================
# 區塊 1: 標的選擇與輸入
# ===============================================================
st.title("📊 SMA 深度量化分析 — 尋找極端買賣點")

with st.sidebar:
    st.header("🔍 標的設定")
    mode = st.radio("選擇模式", ["熱門 ETF 對照", "自定義個股回測"])
    
    if mode == "熱門 ETF 對照":
        ETF_MAPPING = {
            "🇹🇼 0050 vs 00631L": ("0050.TW", "00631L.TW"),
            "🇺🇸 QQQ vs TQQQ": ("QQQ", "TQQQ"),
            "🇺🇸 SPY vs UPRO": ("SPY", "UPRO"),
            "GD 黃金 vs 00708L": ("00635U.TW", "00708L.TW")
        }
        selection = st.selectbox("選擇組合", list(ETF_MAPPING.keys()))
        proto_symbol, lev_symbol = ETF_MAPPING[selection]
    else:
        st.info("提示：台股請加 .TW (例如 2330.TW)")
        proto_symbol = st.text_input("輸入標的 A (基準)", value="2330.TW").upper()
        lev_symbol = st.text_input("輸入標的 B (對照/槓桿)", value="00631L.TW").upper()

    st.divider()
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

# ===============================================================
# 區塊 2: 自動偵測區間
# ===============================================================
@st.cache_data(ttl=3600)
def get_range(s1, s2):
    try:
        d1 = yf.download(s1, period="max", progress=False)['Close']
        d2 = yf.download(s2, period="max", progress=False)['Close']
        common_start = max(d1.index.min().date(), d2.index.min().date())
        common_end = min(d1.index.max().date(), d2.index.max().date())
        return common_start, common_end
    except: return None, None

min_date, max_date = get_range(proto_symbol, lev_symbol)

if not min_date:
    st.error("❌ 找不到資料，請確認代號是否正確。")
    st.stop()

# ===============================================================
# 區塊 3: 參數設定
# ===============================================================
st.subheader("🛠️ 策略參數")
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    sma_window = st.number_input("SMA 週期", 10, 500, 200)
with c2:
    # 新增：讓使用者可以調整您發現的極端值
    overbought = st.number_input("高位警戒 (%)", 0, 100, 40) / 100
    oversold = st.number_input("低位警戒 (%)", -100, 0, -20) / 100
with c3:
    start_date = st.date_input("開始日期", min_date)
    end_date = st.date_input("結束日期", max_date)

# ===============================================================
# 區塊 4: 繪圖核心
# ===============================================================
if st.button("🚀 執行量化分析", use_container_width=True):
    raw = yf.download([proto_symbol, lev_symbol], start=start_date, end=end_date, progress=False)
    
    if not raw.empty:
        # 清洗數據
        data = raw['Close'].copy()
        data = data.rename(columns={proto_symbol: "Base", lev_symbol: "Lev"}).dropna()
        
        # 計算指標
        data["SMA_Base"] = data["Base"].rolling(sma_window).mean()
        data["SMA_Lev"] = data["Lev"].rolling(sma_window).mean()
        data["Gap_Base"] = (data["Base"] - data["SMA_Base"]) / data["SMA_Base"]
        data["Gap_Lev"] = (data["Lev"] - data["SMA_Lev"]) / data["SMA_Lev"]
        data = data.dropna()

        # 建立圖表
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
            subplot_titles=("📉 SMA Gap% 乖離率與警戒區", "📈 價格走勢對照"),
            specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
        )

        # --- 上圖：Gap% ---
        label_a = proto_symbol.replace(".TW", "")
        label_b = lev_symbol.replace(".TW", "")
        
        fig.add_trace(go.Scatter(x=data.index, y=data["Gap_Base"], name=f"{label_a} Gap%", line=dict(color='blue', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["Gap_Lev"], name=f"{label_b} Gap%", line=dict(color='red', width=1.5)), row=1, col=1)
        
        # 基準線與警戒線
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)
        fig.add_hline(y=overbought, line_dash="dot", line_color="orange", annotation_text=f"過熱({overbought:.0%})", row=1, col=1)
        fig.add_hline(y=oversold, line_dash="dot", line_color="green", annotation_text=f"恐慌({oversold:.0%})", row=1, col=1)

        # --- 下圖：價格 ---
        fig.add_trace(go.Scatter(x=data.index, y=data["Base"], name=f"{label_a} 價格", line=dict(color='rgba(0,0,255,0.2)', width=1)), row=2, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=data.index, y=data["SMA_Base"], name=f"{label_a} SMA", line=dict(color='blue', width=2)), row=2, col=1, secondary_y=False)
        
        fig.add_trace(go.Scatter(x=data.index, y=data["Lev"], name=f"{label_b} 價格", line=dict(color='rgba(255,0,0,0.2)', width=1)), row=2, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(x=data.index, y=data["SMA_Lev"], name=f"{label_b} SMA", line=dict(color='red', width=2)), row=2, col=1, secondary_y=True)

        # 佈局優化
        fig.update_layout(height=800, hovermode="x unified", legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
        fig.update_yaxes(title_text="乖離率", tickformat=".0%", row=1, col=1)
        fig.update_yaxes(title_text=f"{label_a} 價格", row=2, col=1, secondary_y=False)
        fig.update_yaxes(title_text=f"{label_b} 價格", row=2, col=1, secondary_y=True, showgrid=False)

        st.plotly_chart(fig, use_container_width=True)
        
        # 統計資訊
        st.subheader("📊 數據摘要")
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{label_a} 最大乖離", f"{data['Gap_Base'].max():.1%}")
        m2.metric(f"{label_a} 最小乖離", f"{data['Gap_Base'].min():.1%}")
        m3.metric("總交易日數", len(data))
    else:
        st.error("抓取不到資料，請檢查區間或代號。")
