import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(
    page_title="ETF 量化聯動分析戰情室",
    layout="wide",
)

# ===============================================================
# ETF 對照表
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {
        "symbol": "0050.TW",
        "leverage_options": {"00631L (元大台灣50正2)": "00631L.TW"}
    },
    "🇺🇸 美股 - QQQ (納斯達克100)": {
        "symbol": "QQQ",
        "leverage_options": {
            "QLD (兩倍做多)": "QLD",
            "TQQQ (三倍做多)": "TQQQ"
        }
    },
    "🇺🇸 美股 - SPY (標普500)": {
        "symbol": "SPY",
        "leverage_options": {
            "SSO (兩倍做多)": "SSO",
            "UPRO (三倍做多)": "UPRO"
        }
    }
}

st.title("📊 ETF 多維度聯動分析儀表板")

# ===============================================================
# 參數與資料抓取
# ===============================================================
sel_col1, sel_col2 = st.columns(2)
with sel_col1:
    selected_proto = st.selectbox("選擇原型 ETF", list(ETF_MAPPING.keys()))
    proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
with sel_col2:
    lev_options = ETF_MAPPING[selected_proto]["leverage_options"]
    selected_lev = st.selectbox("選擇槓桿 ETF", list(lev_options.keys()))
    lev_symbol = lev_options[selected_lev]

@st.cache_data(ttl=3600)
def get_data(p_sym, l_sym, start):
    # 多抓兩年資料以利計算 SMA 與 12M Return
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=2)
    df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
    if df.empty: return None
    # 處理可能的多重索引或單一索引
    df = df['Adj Close'] if 'Adj Close' in df.columns else df['Close']
    return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()

with st.form("control_panel"):
    c1, c2, c3 = st.columns(3)
    with c1: start_date = st.date_input("分析開始日期", pd.to_datetime("2020-01-01"))
    with c2: sma_window = st.number_input("SMA 週期", 10, 500, 200)
    with c3: chart_height = st.slider("圖表總高度", 600, 2000, 1000)
    submitted = st.form_submit_button("🚀 執行聯動回測", use_container_width=True)

if submitted:
    df_raw = get_data(proto_symbol, lev_symbol, start_date)
    
    if df_raw is not None:
        # 指標計算
        df_raw["SMA_Base"] = df_raw["Base"].rolling(sma_window).mean()
        df_raw["SMA_Lev"]  = df_raw["Lev"].rolling(sma_window).mean()
        df_raw["Gap_Base"] = (df_raw["Base"] - df_raw["SMA_Base"]) / df_raw["SMA_Base"]
        df_raw["Gap_Lev"]  = (df_raw["Lev"] - df_raw["SMA_Lev"]) / df_raw["SMA_Lev"]
        df_raw["Ret12M_Base"] = df_raw["Base"].pct_change(periods=252) * 100
        df_raw["Ret12M_Lev"] = df_raw["Lev"].pct_change(periods=252) * 100
        
        # 裁切回使用者選取區區間
        df = df_raw.loc[pd.to_datetime(start_date):].copy()
        base_name = selected_proto.split(" ")[2]
        lev_name = selected_lev.split(" ")[0]

        # ===============================================================
        # 建立 3 層子圖 (Subplots) - 已移除累積報酬圖
        # ===============================================================
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,           # 共享 X 軸縮放
            vertical_spacing=0.07,       # 子圖間距
            subplot_titles=(
                f"1. {sma_window}SMA 乖離率 (Gap %)", 
                "2. 絕對價格與均線對照 (雙軸)", 
                "3. 近 12 個月滾動報酬率 (%)"
            ),
            # 設定每一層的軸類型 (第二層與第三層需要雙軸支援)
            specs=[[{"secondary_y": False}], 
                   [{"secondary_y": True}], 
                   [{"secondary_y": True}]]
        )

        # --- Row 1: Gap % ---
        fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Base"], name=f"{base_name} Gap%", line=dict(color='blue')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Lev"], name=f"{lev_name} Gap%", line=dict(color='red')), row=1, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

        # --- Row 2: Price & SMA (Dual Y) ---
        fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{base_name} 收盤價", opacity=0.3, line=dict(color='blue', width=1)), row=2, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{base_name} SMA", line=dict(color='blue', width=2.5)), row=2, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{lev_name} 收盤價", opacity=0.3, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{lev_name} SMA", line=dict(color='red', width=2.5)), row=2, col=1, secondary_y=True)

        # --- Row 3: 12M Return (Dual Y) ---
        fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Base"], name=f"{base_name} 12M 報酬", line=dict(color='blue', dash='dot')), row=3, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Lev"], name=f"{lev_name} 12M 報酬", line=dict(color='red')), row=3, col=1, secondary_y=True)
        fig.add_hline(y=0, line_dash="dash", line_color="black", row=3, col=1)

        # ===============================================================
        # 佈局與軸設定
        # ===============================================================
        fig.update_layout(height=chart_height, hovermode="x unified", showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        
        # 格式化
        fig.update_yaxes(tickformat=".1%", title_text="乖離率 %", row=1, col=1)
        
        fig.update_yaxes(title_text=f"{base_name} 價格", row=2, col=1, secondary_y=False)
        fig.update_yaxes(title_text=f"{lev_name} 價格", row=2, col=1, secondary_y=True)
        
        fig.update_yaxes(title_text=f"{base_name} 報酬 %", row=3, col=1, secondary_y=False)
        fig.update_yaxes(title_text=f"{lev_name} 報酬 %", row=3, col=1, secondary_y=True)

        st.plotly_chart(fig, use_container_width=True)
        
        st.caption("💡 提示：您可以點擊圖例開啟/關閉特定線條，或使用滑鼠在圖表上框選區域進行縮放，三張圖會同步聯動。")

else:
    st.info("👆 請於上方設定參數並點擊執行按鈕，開始多維度聯動分析。")
