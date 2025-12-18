import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(
    page_title="倉鼠量化戰情室 - ETF 聯動分析",
    layout="wide",
)

# ===============================================================
# 全域設定：ETF 對照表
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

# ===============================================================
# 核心邏輯：資料抓取與計算
# ===============================================================
@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    # 多抓兩年資料以利計算 SMA 與 12M Return
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=2)
    df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
    if df.empty: return None
    
    # 處理可能的多重索引 (yfinance 升級後常見)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs("Close", axis=1, level=0) if "Close" in df.columns.levels[0] else df.xs("Adj Close", axis=1, level=0)
    
    return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()

# ===============================================================
# UI 側邊欄：快速連結與參數
# ===============================================================
with st.sidebar:
    st.image("https://hamr-lab.com/wp-content/uploads/2023/06/logo.png", width=150) # 假設網址
    st.title("🐹 倉鼠戰情控制台")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.divider()
    
    selected_proto = st.selectbox("1. 選擇原型 ETF", list(ETF_MAPPING.keys()))
    lev_options = ETF_MAPPING[selected_proto]["leverage_options"]
    selected_lev = st.selectbox("2. 選擇槓桿 ETF", list(lev_options.keys()))
    
    sma_window = st.number_input("3. SMA 週期 (日)", 10, 500, 200)
    start_date = st.date_input("4. 分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("5. 圖表總高度", 600, 2000, 1000)

# ===============================================================
# 主頁面運算
# ===============================================================
st.title(f"📊 {selected_proto.split(' ')[2]} vs {selected_lev.split(' ')[0]} 聯動分析")

proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = lev_options[selected_lev]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 指標計算
    df_raw["SMA_Base"] = df_raw["Base"].rolling(sma_window).mean()
    df_raw["SMA_Lev"]  = df_raw["Lev"].rolling(sma_window).mean()
    df_raw["Gap_Base"] = (df_raw["Base"] - df_raw["SMA_Base"]) / df_raw["SMA_Base"]
    df_raw["Gap_Lev"]  = (df_raw["Lev"] - df_raw["SMA_Lev"]) / df_raw["SMA_Lev"]
    df_raw["Ret12M_Base"] = df_raw["Base"].pct_change(periods=252) * 100
    df_raw["Ret12M_Lev"] = df_raw["Lev"].pct_change(periods=252) * 100
    
    # 裁切回使用者選取區間
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    base_name = selected_proto.split(" ")[2]
    lev_name = selected_lev.split(" ")[0]

    # 頂部績效卡
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{base_name} 最新價", f"{df['Base'].iloc[-1]:.2f}")
    m2.metric(f"{lev_name} 最新價", f"{df['Lev'].iloc[-1]:.2f}")
    m3.metric(f"{base_name} 12M報酬", f"{df['Ret12M_Base'].iloc[-1]:.1f}%")
    m4.metric(f"{lev_name} 12M報酬", f"{df['Ret12M_Lev'].iloc[-1]:.1f}%")

    # ===============================================================
    # 建立 3 層聯動子圖
    # ===============================================================
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,           # 核心：共享 X 軸
        vertical_spacing=0.06,       # 間距
        subplot_titles=(
            f"🟢 乖離率比較 (距離 {sma_window}SMA)", 
            "🔵 絕對價格走勢 (藍:原型 / 紅:槓桿)", 
            "🔴 近 12 個月滾動報酬率 (%)"
        ),
        specs=[[{"secondary_y": False}], 
               [{"secondary_y": True}], 
               [{"secondary_y": True}]]
    )

    # 第一層：Gap %
    fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Base"], name=f"{base_name} Gap%", line=dict(color='royalblue', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Gap_Lev"], name=f"{lev_name} Gap%", line=dict(color='crimson', width=1.5)), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", row=1, col=1)

    # 第二層：價格與 SMA (雙軸)
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{base_name} 價格", opacity=0.3, line=dict(color='royalblue', width=1)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{base_name} SMA", line=dict(color='blue', width=2.5)), row=2, col=1, secondary_y=False)
    
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{lev_name} 價格", opacity=0.3, line=dict(color='crimson', width=1)), row=2, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{lev_name} SMA", line=dict(color='red', width=2.5)), row=2, col=1, secondary_y=True)

    # 第三層：12M Return (雙軸)
    fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Base"], name=f"{base_name} 12M%", line=dict(color='blue', dash='dot')), row=3, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Lev"], name=f"{lev_name} 12M%", line=dict(color='red', width=2)), row=3, col=1, secondary_y=True)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=3, col=1)

    # ===============================================================
    # 圖表美化優化
    # ===============================================================
    fig.update_layout(
        height=chart_height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50)
    )

    # 開啟十字準星 (Spikelines) 以利對齊觀察
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot", spikethickness=1)
    
    # Y 軸格式與標題
    fig.update_yaxes(tickformat=".1%", row=1, col=1)
    fig.update_yaxes(title_text="價格(左)", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="價格(右)", row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text="報酬%(左)", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="報酬%(右)", row=3, col=1, secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("❌ 無法下載資料，請檢查網路或標的代號。")

st.markdown("---")
st.caption("🐹 倉鼠人生實驗室 | 本工具僅供量化研究參考，不構成任何投資建議。")
