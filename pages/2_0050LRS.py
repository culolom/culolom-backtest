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
    page_title="0050LRS 回測系統（含乖離率）",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證守門員 (需確保同目錄或上層有 auth.py)
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    st.warning("⚠️ 未偵測到 auth.py，請確保驗證模組已備齊。")

###############################################################
# 資料設定與工具函式
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

# 格式化工具
fmt_money = lambda v: f"{v:,.0f} 元"
fmt_pct = lambda v: f"{v:.2%}"
fmt_num = lambda v: f"{v:.2f}"
fmt_int = lambda v: f"{int(v):,}"
nz = lambda x, default=0.0: float(np.nan_to_num(x, nan=default))

###############################################################
# UI 側邊欄與輸入
###############################################################

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### ⚙️ 策略參數")
    base_label = st.selectbox("原型 ETF (訊號來源)", list(BASE_ETFS.keys()))
    lev_label = st.selectbox("槓桿 ETF (實際交易)", list(LEV_ETFS.keys()))
    s_min, s_max = get_full_range_from_csv(BASE_ETFS[base_label], LEV_ETFS[lev_label])
    
    start = st.date_input("回測起點", max(s_min, s_max - dt.timedelta(days=5*365)))
    end = st.date_input("回測終點", s_max)
    capital = st.number_input("本金", 1000, 5_000_000, 100_000, 10000)
    pos_mode = st.radio("初始狀態", ["一開始就全倉", "空手起跑"])

st.markdown("<h1>📊 0050LRS 策略回測系統</h1>", unsafe_allow_html=True)

###############################################################
# 主計算邏輯
###############################################################

if st.button("開始執行策略分析 🚀"):
    df_b = load_csv(BASE_ETFS[base_label])
    df_l = load_csv(LEV_ETFS[lev_label])
    
    if df_b.empty or df_l.empty:
        st.error("資料讀取失敗，請檢查 data/ 資料夾。")
        st.stop()

    # 預留 200 天計算均線
    df = df_b.loc[start - dt.timedelta(days=365):end].copy()
    df.rename(columns={"Price": "Price_base"}, inplace=True)
    df = df.join(df_l["Price"].rename("Price_lev"), how="inner")
    
    # 核心指標計算
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    # ✨ 乖離率計算公式：(現價 - 均線) / 均線
    df["Bias_200"] = (df["Price_base"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[start:end]

    # LRS 訊號與倉位
    df["Signal"] = 0
    for i in range(1, len(df)):
        p, m, p0, m0 = df["Price_base"].iloc[i], df["MA_200"].iloc[i], df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]
        if p > m and p0 <= m0: df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif p < m and p0 >= m0: df.iloc[i, df.columns.get_loc("Signal")] = -1

    curr = 0 if "空手" in pos_mode else 1
    pos = []
    for s in df["Signal"]:
        if s == 1: curr = 1
        elif s == -1: curr = 0
        pos.append(curr)
    df["Position"] = pos

    # 報酬率計算
    df["Ret_base"] = df["Price_base"].pct_change().fillna(0)
    df["Ret_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1] if df["Position"].iloc[i-1] == 1 else 1.0
        equity_lrs.append(equity_lrs[-1] * r)
    df["Equity_LRS"] = equity_lrs
    df["Equity_Base"] = (1 + df["Ret_base"]).cumprod()
    df["Equity_Lev"] = (1 + df["Ret_lev"]).cumprod()

    ###############################################################
    # 視覺化圖表
    ###############################################################

    # A. 乖離率與價格對照圖 (依據圖片需求新增)
    st.markdown("<h3>🎯 200MA 乖離率與價格趨勢</h3>", unsafe_allow_html=True)
    fig_bias = go.Figure()
    # 乖離率區域
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率 (%)", fill='tozeroy', 
                                 line=dict(color='rgba(100, 149, 237, 0.8)', width=1.5), 
                                 fillcolor='rgba(100, 149, 237, 0.1)', yaxis="y1"))
    # 收盤價
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="收盤價", 
                                 line=dict(color='#FF8C00', width=2), yaxis="y2"))
    # 200 SMA
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200 SMA", 
                                 line=dict(color='silver', width=1, dash='dash'), yaxis="y2"))
    
    fig_bias.update_layout(height=450, template="plotly_white", hovermode="x unified",
                           yaxis=dict(title="乖離率 %", side="left", showgrid=True),
                           yaxis2=dict(title="價格 (元)", side="right", overlaying="y", showgrid=False),
                           legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_bias, use_container_width=True)

    # B. 三策略資金曲線
    st.markdown("<h3>📈 策略績效比較</h3>", unsafe_allow_html=True)
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="LRS 策略", line=dict(width=2.5)))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Lev"]-1, name="槓桿 ETF B&H"))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"]-1, name="原型 ETF B&H"))
    fig_eq.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"), height=400)
    st.plotly_chart(fig_eq, use_container_width=True)

    ###############################################################
    # KPI 與 表格 (簡化呈現)
    ###############################################################
    
    y_len = (df.index[-1] - df.index[0]).days / 365
    def get_stats(eq, rets):
        final = eq.iloc[-1]
        cagr = (final)**(1/y_len)-1 if y_len>0 else 0
        mdd = 1 - (eq / eq.cummax()).min()
        v, sh, so = calc_metrics(rets)
        return final, cagr, mdd, v, sh
    
    # 快速 KPI
    res_lrs = get_stats(df["Equity_LRS"], df["Equity_LRS"].pct_change())
    
    st.divider()
    cols = st.columns(4)
    cols[0].metric("期末資產", fmt_money(res_lrs[0] * capital))
    cols[1].metric("年化報酬 (CAGR)", f"{res_lrs[1]:.2%}")
    cols[2].metric("最大回撤 (MDD)", f"-{res_lrs[2]:.2%}")
    cols[3].metric("Sharpe Ratio", f"{res_lrs[4]:.2f}")

    st.success(f"回測完成！目前 200MA 乖離率為：{df['Bias_200'].iloc[-1]:.2f}%")
