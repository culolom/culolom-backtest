import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(page_title="倉鼠量化戰情室 - 雙均線慣性分析", layout="wide")

# ===============================================================
# 全域設定：ETF 對照表
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {"symbol": "0050.TW", "lev": "00631L.TW"},
    "🇺🇸 美股 - QQQ (納斯達克100)": {"symbol": "QQQ", "lev": "TQQQ"},
    "🇺🇸 美股 - SPY (標普500)": {"symbol": "SPY", "lev": "UPRO"}
}

# ===============================================================
# 資料抓取與預處理
# ===============================================================
@st.cache_data(ttl=3600)
def load_data(p_sym, l_sym, start):
    # 多抓一年資料以利計算均線與斜率
    ext_start = pd.to_datetime(start) - pd.DateOffset(years=1)
    try:
        df = yf.download([p_sym, l_sym], start=ext_start, progress=False)
        if df.empty: return None
        
        # 處理 yfinance 可能產生的 MultiIndex 欄位
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
# 側邊欄控制台
# ===============================================================
with st.sidebar:
    st.markdown("### 🐹 倉鼠戰情控制台")
    selected_proto = st.selectbox("1. 選擇分析標的", list(ETF_MAPPING.keys()))
    sma_window = st.number_input("2. SMA 週期 (日)", 10, 500, 200)
    
    st.divider()
    st.markdown("### 🛡️ 趨勢慣性濾網")
    slope_days = st.slider("斜率計算天數", 5, 60, 20)
    
    # 你的核心邏輯參數
    buy_slope_limit = -2.0  # 突破時斜率需 > -2%
    sell_slope_limit = 2.0  # 跌破時斜率需 < 2%
    
    st.divider()
    start_date = st.date_input("分析起始日期", pd.to_datetime("2020-01-01"))
    chart_height = st.slider("圖表總高度", 600, 1500, 900)

# ===============================================================
# 核心運算：慣性過濾與雙均線
# ===============================================================
proto_symbol = ETF_MAPPING[selected_proto]["symbol"]
lev_symbol = ETF_MAPPING[selected_proto]["lev"]

df_raw = load_data(proto_symbol, lev_symbol, start_date)

if df_raw is not None:
    # 1. 雙均線計算
    df_raw["SMA_Base"] = df_raw["Base"].rolling(sma_window).mean()
    df_raw["SMA_Lev"]  = df_raw["Lev"].rolling(sma_window).mean()
    
    # 2. 斜率計算 (基於原型 ETF)
    df_raw["SMA_Slope"] = (df_raw["SMA_Base"] - df_raw["SMA_Base"].shift(slope_days)) / df_raw["SMA_Base"].shift(slope_days) * 100
    
    # 3. 慣性過濾信號
    df_raw["Signal"] = np.nan
    # [真突破]：價格 > 均線 且 斜率 > -2.0%
    buy_cond = (df_raw["Base"] > df_raw["SMA_Base"]) & (df_raw["SMA_Slope"] > buy_slope_limit)
    # [真跌破]：價格 < 均線 且 斜率 < 2.0%
    sell_cond = (df_raw["Base"] < df_raw["SMA_Base"]) & (df_raw["SMA_Slope"] < sell_slope_limit)
    
    df_raw.loc[buy_cond, "Signal"] = 1
    df_raw.loc[sell_cond, "Signal"] = 0
    # 狀態保持 (直到滿足下一個反向觸發條件)
    df_raw["Signal"] = df_raw["Signal"].ffill().fillna(0)
    df_raw["Action"] = df_raw["Signal"].diff()

    # 4. 績效統計
    df_raw["Daily_Ret"] = df_raw["Lev"].pct_change()
    df_raw["Strategy_Ret"] = df_raw["Signal"].shift(1) * df_raw["Daily_Ret"]
    
    # 裁切日期
    df = df_raw.loc[pd.to_datetime(start_date):].copy()
    
    # 計算累積報酬與 MDD
    cum_strategy = (1 + df["Strategy_Ret"].fillna(0)).cumprod()
    total_ret = (cum_strategy.iloc[-1] - 1) * 100
    mdd = ((cum_strategy / cum_strategy.cummax()) - 1).min() * 100
    
    b_name = selected_proto.split(" ")[2]
    l_name = lev_symbol.replace(".TW", "")

    # ===============================================================
    # 儀表板顯示
    # ===============================================================
    st.subheader(f"📊 慣性分析儀表板：{b_name}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("策略累計報酬", f"{total_ret:.1f}%")
    m2.metric("最大回撤 (MDD)", f"{mdd:.1f}%")
    m3.metric("當前均線斜率", f"{df['SMA_Slope'].iloc[-1]:.2f}%")
    m4.info("目前狀態：🟢 持股中" if df["Signal"].iloc[-1] == 1 else "目前狀態：⚪ 觀望中")

    # ===============================================================
    # 建立 2 層聯動圖表
    # ===============================================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(
            f"1. 均線斜率與慣性區間 (黃色帶: {buy_slope_limit}% ~ {sell_slope_limit}%)", 
            f"2. 雙均線對照走勢 (左軸:{b_name} / 右軸:{l_name})"
        ),
        row_heights=[0.3, 0.7],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]]
    )

    # --- 圖 1: 斜率 (Slope) ---
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Slope"], name="均線斜率", fill='tozeroy', line=dict(color='gray', width=1)), row=1, col=1)
    fig.add_hrect(y0=-2, y1=2, fillcolor="yellow", opacity=0.1, line_width=0, row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)

    # --- 圖 2: 雙均線與過濾訊號 ---
    # 左軸：原型 ETF
    fig.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{b_name} 收盤", line=dict(color='blue', width=1, opacity=0.4)), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{b_name} SMA", line=dict(color='blue', width=2.5)), row=2, col=1, secondary_y=False)
    
    # 右軸：正2 槓桿 ETF (補上 200SMA)
    fig.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{l_name} 收盤", line=dict(color='red', width=1, opacity=0.4)), row=2, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{l_name} SMA", line=dict(color='red', width=2.5, dash='dot')), row=2, col=1, secondary_y=True)

    # 標註買賣訊號
    buy_pts = df[df["Action"] == 1]
    sell_pts = df[df["Action"] == -1]
    fig.add_trace(go.Scatter(x=buy_pts.index, y=buy_pts["Base"], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name='慣性確認買入'), row=2, col=1)
    fig.add_trace(go.Scatter(x=sell_pts.index, y=sell_pts["Base"], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name='慣性確認賣出'), row=2, col=1)

    # 圖表佈局與連動準星設定 (修正 showspikes 錯誤)
    fig.update_layout(height=chart_height, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    # 同步開啟 X 與 Y 軸的準星線
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="dot", spikesnap="cursor")
    fig.update_yaxes(showspikes=True)

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.caption(f"🐹 倉鼠人生實驗室 | 策略邏輯：當價格站上均線且斜率 > {buy_slope_limit}% 時進場；跌破均線且斜率 < {sell_slope_limit}% 時離場。")

else:
    st.info("👆 請於左側選擇參數並開始分析。")
