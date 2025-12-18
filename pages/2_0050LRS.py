import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 字型與頁面設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC"]

st.set_page_config(
    page_title="0050LRS+Bias 回測系統",
    page_icon="🐹",
    layout="wide",
)

# 🔒 驗證守門員
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except:
    st.error("認證模組讀取失敗")
    st.stop()

###############################################################
# ETF 資料與工具
###############################################################

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}
WINDOW = 200
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1, df2 = load_csv(base_symbol), load_csv(lev_symbol)
    if df1.empty or df2.empty: return dt.date(2012, 1, 1), dt.date.today()
    return max(df1.index.min().date(), df2.index.min().date()), min(df1.index.max().date(), df2.index.max().date())

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std, downside = daily.mean(), daily.std(), daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

###############################################################
# UI 輸入區
###############################################################

with st.sidebar:
    st.title("倉鼠量化戰情室 🐹")
    st.page_link("Home.py", label="回到首頁", icon="🏠")
    st.divider()
    
    st.header("⚙️ 基本設定")
    base_label = st.selectbox("原型 ETF (訊號來源)", list(BASE_ETFS.keys()))
    lev_label = st.selectbox("槓桿 ETF (交易對象)", list(LEV_ETFS.keys()))
    
    s_min, s_max = get_full_range_from_csv(BASE_ETFS[base_label], LEV_ETFS[lev_label])
    start_date = st.date_input("開始日期", max(s_min, s_max - dt.timedelta(days=5*365)))
    end_date = st.date_input("結束日期", s_max)
    capital = st.number_input("投入本金", 1000, 10_000_000, 100_000)
    pos_init = st.radio("初始狀態", ["全倉買入", "空手起跑"])

    st.divider()
    st.header("🎯 乖離率套利加強版")
    use_bias = st.toggle("啟用乖離率進階策略", value=False)
    bias_high = st.slider("高位套利賣出點 (%)", 10, 60, 40) if use_bias else 40
    bias_low = st.slider("低位抄底買進點 (%)", -50, -5, -20) if use_bias else -20

st.markdown(f"<h1>📊 0050LRS {'+ 乖離套利' if use_bias else ''} 策略回測</h1>", unsafe_allow_html=True)

###############################################################
# 計算核心邏輯
###############################################################

if st.button("啟動回測分析 🚀"):
    df_base = load_csv(BASE_ETFS[base_label])
    df_lev = load_csv(LEV_ETFS[lev_label])
    
    if df_base.empty or df_lev.empty:
        st.error("找不到資料檔案，請檢查 data/ 目錄")
        st.stop()

    # 準備資料
    df = df_base.loc[start_date - dt.timedelta(days=365):end_date].copy()
    df.rename(columns={"Price": "Price_base"}, inplace=True)
    df = df.join(df_lev["Price"].rename("Price_lev"), how="inner")
    
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price_base"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[start_date:end_date]

    # --- 關鍵：訊號生成邏輯 ---
    df["Signal"] = 0  # 1: 買進, -1: 賣出
    df["Signal_Type"] = "" # 紀錄是 LRS 還是 Bias 觸發
    
    current_pos = 1 if pos_init == "全倉買入" else 0
    
    for i in range(1, len(df)):
        p, m, b = df["Price_base"].iloc[i], df["MA_200"].iloc[i], df["Bias_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]
        
        # 邏輯 A: 乖離率策略 (優先級可自行調整，此處設為優先偵測)
        if use_bias:
            if b > bias_high and current_pos == 1:
                df.iloc[i, df.columns.get_loc("Signal")] = -1
                df.iloc[i, df.columns.get_loc("Signal_Type")] = "Bias_High"
                current_pos = 0
                continue # 觸發後當天不判斷 LRS
            elif b < bias_low and current_pos == 0:
                df.iloc[i, df.columns.get_loc("Signal")] = 1
                df.iloc[i, df.columns.get_loc("Signal_Type")] = "Bias_Low"
                current_pos = 1
                continue

        # 邏輯 B: 標準 LRS 均線策略
        if p > m and p0 <= m0 and current_pos == 0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
            df.iloc[i, df.columns.get_loc("Signal_Type")] = "LRS_Buy"
            current_pos = 1
        elif p < m and p0 >= m0 and current_pos == 1:
            df.iloc[i, df.columns.get_loc("Signal")] = -1
            df.iloc[i, df.columns.get_loc("Signal_Type")] = "LRS_Sell"
            current_pos = 0

    # 計算持倉與資產曲線
    # 使用 ffill 補全 Position
    temp_sig = df["Signal"].replace(0, np.nan)
    if pos_init == "全倉買入":
        df["Position"] = temp_sig.fillna(method='ffill').fillna(1)
    else:
        df["Position"] = temp_sig.fillna(method='ffill').fillna(0)

    # 報酬率計算
    df["Ret_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        # 如果「前一天」有持倉，則享受「今天」的漲跌幅
        r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1] if df["Position"].iloc[i-1] == 1 else 1.0
        equity_lrs.append(equity_lrs[-1] * r)
    
    df["Equity_LRS"] = equity_lrs
    df["Equity_Lev_BH"] = (df["Price_lev"] / df["Price_lev"].iloc[0])
    df["Equity_Base_BH"] = (df["Price_base"] / df["Price_base"].iloc[0])

    ###############################################################
    # 視覺化圖表
    ###############################################################

    # 1. 價格與均線圖 (標註 LRS 與 Bias 訊號)
    st.markdown("<h3>📌 策略訊號執行點</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="原型價格", line=dict(color="#636EFA", width=2)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200SMA", line=dict(color="#FFA15A", width=1.5, dash="dash")))

    # 標註買進點
    lrs_buys = df[df["Signal_Type"] == "LRS_Buy"]
    bias_buys = df[df["Signal_Type"] == "Bias_Low"]
    fig_price.add_trace(go.Scatter(x=lrs_buys.index, y=lrs_buys["Price_base"], mode="markers", name="LRS 買進", marker=dict(symbol="triangle-up", size=12, color="#00C853")))
    fig_price.add_trace(go.Scatter(x=bias_buys.index, y=bias_buys["Price_base"], mode="markers", name="乖離抄底", marker=dict(symbol="star", size=12, color="#FFD700")))

    # 標註賣出點
    lrs_sells = df[df["Signal_Type"] == "LRS_Sell"]
    bias_sells = df[df["Signal_Type"] == "Bias_High"]
    fig_price.add_trace(go.Scatter(x=lrs_sells.index, y=lrs_sells["Price_base"], mode="markers", name="LRS 賣出", marker=dict(symbol="triangle-down", size=12, color="#D50000")))
    fig_price.add_trace(go.Scatter(x=bias_sells.index, y=bias_sells["Price_base"], mode="markers", name="乖離套利", marker=dict(symbol="x", size=10, color="#FF69B4")))

    fig_price.update_layout(height=500, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_price, use_container_width=True)

    # 2. 乖離率副圖
    st.markdown("<h3>📈 200MA 乖離率監測</h3>", unsafe_allow_html=True)
    fig_bias = go.Figure()
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率 (%)", fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)'))
    if use_bias:
        fig_bias.add_hline(y=bias_high, line_dash="dash", line_color="red", annotation_text="高位套利線")
        fig_bias.add_hline(y=bias_low, line_dash="dash", line_color="green", annotation_text="低位抄底線")
    fig_bias.update_layout(height=300, template="plotly_white", yaxis_suffix="%")
    st.plotly_chart(fig_bias, use_container_width=True)

    # 3. 績效曲線
    st.markdown("<h3>💰 累積報酬比較</h3>", unsafe_allow_html=True)
    fig_perf = go.Figure()
    fig_perf.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="本策略績效", line=dict(color="#AB63FA", width=3)))
    fig_perf.add_trace(go.Scatter(x=df.index, y=df["Equity_Lev_BH"]-1, name=f"{lev_label} 買入持有", line=dict(color="#EF553B", opacity=0.5)))
    fig_perf.update_layout(height=400, template="plotly_white", yaxis_tickformat=".0%")
    st.plotly_chart(fig_perf, use_container_width=True)

    ###############################################################
    # KPI 結算
    ###############################################################
    st.divider()
    final_equity = df["Equity_LRS"].iloc[-1]
    mdd = 1 - (df["Equity_LRS"] / df["Equity_LRS"].cummax()).min()
    cagr = (final_equity)**(1/years_len) - 1
    
    c1, c2, c3 = st.columns(3)
    c1.metric("最終資產價值", f"{final_equity * capital:,.0f} 元", f"{(final_equity-1):.2%}")
    c2.metric("年化報酬率 (CAGR)", f"{cagr:.2%}")
    c3.metric("最大回撤 (MDD)", f"-{mdd:.2%}")

    st.info(f"💡 本次測試共觸發 {len(df[df['Signal']!=0])} 次交易訊號。")
