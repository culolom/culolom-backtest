###############################################################
# app.py — ETF SMA 策略戰情室 (圖例與標籤修復版)
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 頁面設定
st.set_page_config(
    page_title="ETF SMA 戰情室 (修復版)",
    layout="wide",
)

# ===============================================================
# 全域設定：ETF 對照表
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {
        "symbol": "0050.TW",
        "leverage_options": {
            "00631L (元大台灣50正2)": "00631L.TW",
        }
    },
    "🇺🇸 美股 - QQQ (納斯達克100)": {
        "symbol": "QQQ",
        "leverage_options": {
            "QLD (ProShares 兩倍做多)": "QLD",
            "TQQQ (ProShares 三倍做多)": "TQQQ"
        }
    },
    "🇺🇸 美股 - SPY (標普500)": {
        "symbol": "SPY",
        "leverage_options": {
            "SSO (ProShares 兩倍做多)": "SSO",
            "UPRO (ProShares 三倍做多)": "UPRO"
        }
    },
    "GD 黃金 - 00635U (期元大S&P黃金)": {
        "symbol": "00635U.TW",
        "leverage_options": {
            "00708L (期元大S&P黃金正2)": "00708L.TW" 
        }
    }
}

with st.sidebar:
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.divider()

st.title("📊 ETF SMA 深度量化分析戰情室")

# ===============================================================
# 區塊 1: 標的選擇與區間偵測
# ===============================================================

sel_col1, sel_col2 = st.columns(2)

with sel_col1:
    proto_keys = list(ETF_MAPPING.keys())
    selected_proto_name = st.selectbox("原型 ETF (訊號來源)", proto_keys)
    proto_symbol = ETF_MAPPING[selected_proto_name]["symbol"]

with sel_col2:
    lev_options = ETF_MAPPING[selected_proto_name]["leverage_options"]
    selected_lev_name = st.selectbox("槓桿 ETF (實際進出場標的)", list(lev_options.keys()))
    lev_symbol = lev_options[selected_lev_name]

@st.cache_data(ttl=3600)
def get_common_date_range(sym1, sym2):
    try:
        df1 = yf.download(sym1, period="max", progress=False, auto_adjust=False)
        df2 = yf.download(sym2, period="max", progress=False, auto_adjust=False)
        if df1.empty or df2.empty: return None, None
        
        if isinstance(df1.columns, pd.MultiIndex): df1 = df1.xs("Close", axis=1, level=0, drop_level=True)
        if isinstance(df2.columns, pd.MultiIndex): df2 = df2.xs("Close", axis=1, level=0, drop_level=True)
        
        common_start = max(df1.index.min().date(), df2.index.min().date())
        common_end = min(df1.index.max().date(), df2.index.max().date())
        return common_start, common_end
    except:
        return None, None

with st.spinner("正在偵測可回測區間..."):
    min_date, max_date = get_common_date_range(proto_symbol, lev_symbol)

if not min_date:
    st.error("❌ 無法抓取標的資料，請檢查網路或代號。")
    st.stop()

# ===============================================================
# 區塊 2: 日期與參數設定
# ===============================================================

if 'start_date' not in st.session_state: st.session_state['start_date'] = pd.to_datetime("2015-01-01").date()
if 'end_date' not in st.session_state: st.session_state['end_date'] = max_date

# 校正日期範圍
st.session_state['start_date'] = max(st.session_state['start_date'], min_date)
st.session_state['end_date'] = min(st.session_state['end_date'], max_date)

def update_dates(years=None, is_all=False):
    st.session_state['end_date'] = max_date
    if is_all: st.session_state['start_date'] = min_date
    elif years: st.session_state['start_date'] = max(max_date - pd.DateOffset(years=years), pd.Timestamp(min_date)).date()

st.subheader("🛠️ 參數設定")
btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5)
with btn_col1: st.button("一年", on_click=update_dates, kwargs={'years': 1}, use_container_width=True)
with btn_col2: st.button("三年", on_click=update_dates, kwargs={'years': 3}, use_container_width=True)
with btn_col3: st.button("五年", on_click=update_dates, kwargs={'years': 5}, use_container_width=True)
with btn_col4: st.button("十年", on_click=update_dates, kwargs={'years': 10}, use_container_width=True)
with btn_col5: st.button("全都要", on_click=update_dates, kwargs={'is_all': True}, use_container_width=True)

with st.form("param_form"):
    c1, c2, c3 = st.columns(3)
    with c1: start_date = st.date_input("開始日期", key="start_date", min_value=min_date, max_value=max_date)
    with c2: end_date = st.date_input("結束日期", key="end_date", min_value=min_date, max_value=max_date)
    with c3: sma_window = st.number_input("SMA 均線週期", min_value=10, max_value=500, value=200)
    submitted = st.form_submit_button("🚀 開始量化回測", use_container_width=True)

# ===============================================================
# 資料處理與繪圖核心
# ===============================================================
@st.cache_data
def load_analysis_data(start, end, p_sym, l_sym):
    raw = yf.download([p_sym, l_sym], start=start, end=end, auto_adjust=False, progress=False)
    if raw.empty: return None
    # 處理 MultiIndex columns
    try:
        target = "Adj Close" if "Adj Close" in raw.columns.get_level_values(0) else "Close"
        df = raw[target].copy()
    except KeyError:
         # Fallback if structure is different
        df = raw.xs("Close", axis=1, level=0, drop_level=True) if "Close" in raw.columns else raw

    # 重新命名欄位以便識別
    cols_map = {p_sym: "Base", l_sym: "Lev"}
    # 防止 yfinance 返回的 column 名稱帶有額外資訊導致對應失敗
    actual_cols = {col: cols_map[col] for col in df.columns if col in cols_map}
    if len(actual_cols) < 2: return None # 確保抓到兩個標的

    df = df.rename(columns=actual_cols)[["Base", "Lev"]]
    df = df.dropna()
    return df

if submitted:
    with st.spinner("正在計算與繪圖..."):
        df = load_analysis_data(start_date, end_date, proto_symbol, lev_symbol)
        
        if df is not None and not df.empty:
            # --- [修正1: 改用代號作為標籤] ---
            # 直接使用代號，並移除 .TW 以保持簡潔，這樣最準確
            base_label = proto_symbol.replace(".TW", "")
            lev_label = lev_symbol.replace(".TW", "")

            # 計算指標
            df["SMA_Base"] = df["Base"].rolling(sma_window).mean()
            df["SMA_Lev"] = df["Lev"].rolling(sma_window).mean()
            df["Gap_Base"] = (df["Base"] - df["SMA_Base"]) / df["SMA_Base"]
            df["Gap_Lev"] = (df["Lev"] - df["SMA_Lev"]) / df["SMA_Lev"]
            df = df.dropna()

            # 建立上下子圖
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.08,
                subplot_titles=(f"📈 SMA Gap% 乖離率比較 ({sma_window}SMA)", "📉 價格與均線走勢對照"),
                specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
            )

            # 上圖：Gap% (第一列)
            fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Base"], name=f"{base_label} Gap%", line=dict(color='blue', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Lev"], name=f"{lev_label} Gap%", line=dict(color='red', width=1.5)), row=1, col=1)
            fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)

            # 下圖：Price (第二列，左軸 Base, 右軸 Lev)
            fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{base_label} 價格", line=dict(color='rgba(0,0,255,0.3)', width=1)), row=2, col=1, secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{base_label} SMA", line=dict(color='blue', width=2)), row=2, col=1, secondary_y=False)
            
            fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{lev_label} 價格", line=dict(color='rgba(255,0,0,0.3)', width=1)), row=2, col=1, secondary_y=True)
            fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{lev_label} SMA", line=dict(color='red', width=2)), row=2, col=1, secondary_y=True)

            # --- [修正2: 優化圖例位置] ---
            fig.update_layout(
                height=750, 
                hovermode="x unified", 
                # 將圖例改為垂直 (v)，並移到右側外部 (x=1.02)
                legend=dict(
                    orientation="v", 
                    yanchor="top", 
                    y=1, 
                    xanchor="left", 
                    x=1.02,
                    bgcolor="rgba(255,255,255,0.8)", # 增加一點背景色增加可讀性
                    bordercolor="LightGrey",
                    borderwidth=1
                )
            )
            
            # 設定座標軸標題
            fig.update_yaxes(title_text="乖離率 %", tickformat=".1%", row=1, col=1)
            fig.update_yaxes(title_text=f"{base_label} 價格", row=2, col=1, secondary_y=False)
            fig.update_yaxes(title_text=f"{lev_label} 價格", row=2, col=1, secondary_y=True, showgrid=False) # 右軸不顯示網格以免混亂

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("❌ 資料獲取失敗或是資料不足以計算均線。")

else:
    st.info("👆 請設定參數並點擊「🚀 開始量化回測」")
