import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 慣性過濾與績效回測", layout="wide")

# ===============================================================
# ETF 對照表與資料處理
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {"symbol": "0050.TW", "lev": "00631L.TW"},
    "🇺🇸 美股 - QQQ (納斯達克100)": {"symbol": "QQQ", "lev": "TQQQ"},
    "🇺🇸 美股 - SPY (標普500)": {"symbol": "SPY", "lev": "UPRO"}
    "比特幣)": {"symbol": "BTC-USD", "lev": "BTC-USD"}
}

@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=1)
    try:
        df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
        if df.empty: return None
        # 處理 MultiIndex 欄位
        if isinstance(df.columns, pd.MultiIndex):
            df = df["Adj Close"] if "Adj Close" in df.columns.levels[0] else df["Close"]
        return df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()
    except Exception as e:
        st.error(f"資料讀取錯誤: {e}")
        return None

# ===============================================================
# 側邊欄控制台
# ===============================================================
with st.sidebar:
    st.title("🐹 戰情室控制台")
    selected_proto = st.selectbox("分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    st.markdown("### 🛡️ 趨勢慣性門檻")
    slope_days = st.slider("斜率計算天數", 5, 60, 20)
    # 你觀察到的關鍵門檻
    buy_slope_limit = -2.0  
    sell_slope_limit = 2.0  
    
    st.divider()
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表高度", 600, 1500, 900)

# ===============================================================
# 核心計算與策略回測
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]
df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 1. 均線與斜率計算
    df_raw["SMA"] = df_raw["Base"].rolling(sma_window).mean()
    df_raw["SMA_Slope"] = (df_raw["SMA"] - df_raw["SMA"].shift(slope_days)) / df_raw["SMA"].shift(slope_days) * 100
    
    # 2. 慣性過濾訊號
    df_raw["Signal"] = np.nan
    buy_cond = (df_raw["Base"] > df_raw["SMA"]) & (df_raw["SMA_Slope"] > buy_slope_limit)
    sell_cond = (df_raw["Base"] < df_raw["SMA"]) & (df_raw["SMA_Slope"] < sell_slope_limit)
    
    df_raw.loc[buy_cond, "Signal"] = 1
    df_raw.loc[sell_cond, "Signal"] = 0
    df_raw["Signal"] = df_raw["Signal"].ffill().fillna(0)
    df_raw["Action"] = df_raw["Signal"].diff()

    # 3. 策略績效計算 (以槓桿 ETF 為交易對象)
    df_raw["Daily_Return"] = df_raw["Lev"].pct_change()
    # 策略報酬：今日訊號為 1，則獲得「明日」的報酬
    df_raw["Strategy_Return"] = df_raw["Signal"].shift(1) * df_raw["Daily_Return"]
    
    # 裁切日期
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    
    # 績效統計指標
    cum_strategy = (1 + df["Strategy_Return"]).cumprod()
    cum_bh = (df["Lev"] / df["Lev"].iloc[0])
    
    total_ret = (cum_strategy.iloc[-1] - 1) * 100
    mdd = ((cum_strategy / cum_strategy.cummax()) - 1).min() * 100
    bh_ret = (cum_bh.iloc[-1] - 1) * 100

    # ===============================================================
    # 儀表板顯示
    # ===============================================================
    st.subheader(f"📊 慣性策略績效摘要 ({selected_proto.split(' ')[2]})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("策略累計報酬", f"{total_ret:.1f}%", f"{total_ret - bh_ret:.1f}% vs 持有")
    c2.metric("最大回撤 (MDD)", f"{mdd:.1f}%")
    c3.metric("當前斜率位階", f"{df['SMA_Slope'].iloc[-1]:.2f}%")
    
    curr_sig = df["Signal"].iloc[-1]
    c4.info("目前狀態：🟢 持股" if curr_sig == 1 else "目前狀態：⚪ 觀望")

    # ===============================================================
    # 繪圖區
    # ===============================================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("1. 趨勢斜率與慣性門檻 (-2% ~ 2%)", "2. 價格走勢與過濾買賣點"),
        row_heights=[0.3, 0.7],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
    )

    # 圖 1: 斜率
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="均線斜率", fill='tozeroy', line=dict(color='gray')), row=1, col=1)
    fig.add_hrect(y0=-2, y1=2, fillcolor="yellow", opacity=0.1, line_width=0, row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # 圖 2: 價格與訊號
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name="原型 ETF", line=dict(color='blue', width=1.5)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="200SMA", line=dict(color='orange', width=3)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name="槓桿 ETF", opacity=0.2, line=dict(color='red', width=1)), row=2, col=1, secondary_y=True)

    # 標註買賣點
    buy = df[df["Action"] == 1]
    sell = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy.index, y=buy["Base"], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name='慣性確認買入'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell.index, y=sell["Base"], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name='慣性確認賣出'), row=2, col=1)

    fig.update_layout(height=chart_height, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="dot")
    
    st.plotly_chart(fig, use_container_width=True)

    # 補充：累計報酬對照圖 (小圖)
    with st.expander("查看策略累計報酬曲線"):
        fig_perf = go.Figure()
        fig_perf.add_trace(go.Scatter(x=df.index, y=cum_strategy, name="慣性過濾策略", line=dict(color='green')))
        fig_perf.add_trace(go.Scatter(x=df.index, y=cum_bh, name="單純持有槓桿ETF", line=dict(color='red', dash='dot')))
        fig_perf.update_layout(title="累計報酬率對照 (起始=1.0)", height=400)
        st.plotly_chart(fig_perf, use_container_width=True)

else:
    st.info("👆 請於左側調整參數開始量化分析")
