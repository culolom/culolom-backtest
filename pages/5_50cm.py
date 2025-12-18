import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 慣性過濾分析", layout="wide")

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
    # 多抓一年資料以利計算均線與斜率
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=1)
    try:
        df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
        if df.empty: return None
        # 處理 MultiIndex 欄位 (yfinance 特性)
        if isinstance(df.columns, pd.MultiIndex):
            df = df["Adj Close"] if "Adj Close" in df.columns.levels[0] else df["Close"]
        return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()
    except Exception as e:
        st.error(f"資料抓取失敗: {e}")
        return None

# ===============================================================
# 側邊欄控制台
# ===============================================================
with st.sidebar:
    st.markdown("### 🐹 倉鼠戰情控制台")
    selected_proto = st.selectbox("分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    st.markdown("### 🛡️ 慣性過濾門檻")
    slope_days = st.slider("斜率計算天數", 5, 60, 20)
    # 你觀察到的核心門檻：突破 > -2%, 跌破 < 2%
    buy_slope_limit = -2.0  
    sell_slope_limit = 2.0  
    
    st.divider()
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表高度", 600, 1500, 900)

# ===============================================================
# 核心運算與慣性策略
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]
df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 1. 指標計算
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    # 斜率 = (目前均線 - N天前均線) / N天前均線
    df_raw["SMA_Slope"] = (df_raw["SMA"] - df_raw["SMA"].shift(slope_days)) / df_raw["SMA"].shift(slope_days) * 100
    
    # 2. 慣性過濾邏輯
    # 只有當符合條件時才改變訊號，不符合則維持前一天的狀態 (ffill)
    df_raw["Signal"] = np.nan
    
    # [突破條件]：站上 SMA 且 斜率 > -2% (跌勢衰竭或築底)
    buy_cond = (df_raw["Base"] > df_raw["SMA"]) & (df_raw["SMA_Slope"] > buy_slope_limit)
    # [跌破條件]：跌下 SMA 且 斜率 < 2% (漲勢耗盡或轉空)
    sell_cond = (df_raw["Base"] < df_raw["SMA"]) & (df_raw["SMA_Slope"] < sell_slope_limit)
    
    df_raw.loc[buy_cond, "Signal"] = 1
    df_raw.loc[sell_cond, "Signal"] = 0
    
    # 填補中間的空白狀態 (維持持倉或觀望)
    df_raw["Signal"] = df_raw["Signal"].ffill().fillna(0)
    df_raw["Action"] = df_raw["Signal"].diff()

    # 3. 簡單回測統計
    df_raw["Daily_Ret"] = df_raw["Lev"].pct_change()
    df_raw["Strategy_Ret"] = df_raw["Signal"].shift(1) * df_raw["Daily_Ret"]
    
    # 裁切日期
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    
    # 績效計算
    cum_strategy = (1 + df["Strategy_Ret"].fillna(0)).cumprod()
    total_ret = (cum_strategy.iloc[-1] - 1) * 100
    mdd = ((cum_strategy / cum_strategy.cummax()) - 1).min() * 100

    # ===============================================================
    # 儀表板
    # ===============================================================
    st.subheader(f"📊 慣性過濾回測：{selected_proto.split(' ')[2]}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("策略累計報酬", f"{total_ret:.1f}%")
    m2.metric("最大回撤 (MDD)", f"{mdd:.1f}%")
    m3.metric("當前均線斜率", f"{df['SMA_Slope'].iloc[-1]:.2f}%")
    m4.info("狀態：持股中" if df["Signal"].iloc[-1] == 1 else "狀態：觀望中")

    # ===============================================================
    # 繪圖區 (2層聯動)
    # ===============================================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("1. 均線斜率與慣性門檻 (-2% ~ 2%)", "2. 價格走勢與『慣性確認』訊號"),
        row_heights=[0.3, 0.7],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
    )

    # 圖 1: 斜率圖
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="均線斜率", fill='tozeroy', line=dict(color='gray')), row=1, col=1)
    fig.add_hrect(y0=-2, y1=2, fillcolor="yellow", opacity=0.1, line_width=0, row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # 圖 2: 價格圖
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name="原型 ETF", line=dict(color='blue', width=1.5)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="均線", line=dict(color='orange', width=3)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name="槓桿 ETF (參考)", opacity=0.15, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)

    # 標註買賣訊號
    buy = df[df["Action"] == 1]
    sell = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy.index, y=buy["Base"], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name='慣性突破'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell.index, y=sell["Base"], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name='慣性跌破'), row=2, col=1)

    # 佈局美化
    fig.update_layout(height=chart_height, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    # 修正 SpikeLines 錯誤：統一開啟所有子圖的準星
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="dot", spikesnap="cursor")
    fig.update_yaxes(showspikes=True)

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.info(f"💡 **慣性濾網邏輯**：突破 200SMA 且斜率 > {buy_slope_limit}% 才進場；跌破 200SMA 且斜率 < {sell_slope_limit}% 才離場。")

else:
    st.info("👆 請於左側控制台選擇參數並開始分析。")
