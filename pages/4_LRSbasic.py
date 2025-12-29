###############################################################
# app.py — 0050LRS + DCA (槓桿自帶均線訊號版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path
import sys

###############################################################
# 字型設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei",
        "PingFang TC",
        "Heiti TC",
    ]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(
    page_title="0050LRS 回測系統 (槓桿均線版)",
    page_icon="📈",
    layout="wide",
)

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# --- Sidebar ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿 (槓桿 SMA 訊號)</h1>", unsafe_allow_html=True)

st.info("""
**邏輯更新：** 本版本直接使用 **槓桿 ETF (正2)** 的價格與 **槓桿 ETF 的 SMA 均線** 進行比較。
- **買進/賣出訊號：** 當正2價格 突破/跌破 自身的 SMA。
- **原型對照：** 0050 僅用於最後的績效表對比，不影響策略進出場。
""")

###############################################################
# ETF 名稱清單與工具函式
###############################################################

BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}

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

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"
def fmt_int(v): return f"{int(v):,}"
def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))
def format_currency(v): return f"{v:,.0f} 元"
def format_percent(v, d=2): return f"{v*100:.{d}f}%"

###############################################################
# UI 輸入
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF (僅供績效對照)", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF (訊號來源與操作標的)", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col3, col4, col5, col6 = st.columns(4)
with col3: start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4: end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5: capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)
with col6: sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, 10)

st.write("### ⚙️ 策略進階設定")
position_mode = st.radio("策略初始狀態", ["一開始就全倉槓桿 ETF", "空手起跑"], index=0)

with st.expander("📉 跌破均線後的 DCA (定期定額) 設定", expanded=True):
    col_dca1, col_dca2, col_dca3 = st.columns([1, 2, 2])
    with col_dca1: enable_dca = st.toggle("啟用 DCA", value=False)
    with col_dca2: dca_interval = st.number_input("間隔天數 (日)", 1, 60, 3, disabled=not enable_dca)
    with col_dca3: dca_pct = st.number_input("每次買進比例 (%)", 1, 100, 10, 5, disabled=not enable_dca)

###############################################################
# 核心回測運算
###############################################################

if st.button("開始回測 🚀"):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    df_base_raw, df_lev_raw = load_csv(base_symbol), load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗"); st.stop()

    df = pd.DataFrame(index=df_base_raw.loc[start_early:end].index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()

    # --- 關鍵改動：MA 計算基礎改為 Price_lev ---
    df["MA_Signal"] = df["Price_lev"].rolling(sma_window).mean()
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # 策略邏輯
    executed_signals, positions = [0] * len(df), [0.0] * len(df)
    current_pos = 1.0 if "全倉" in position_mode else 0.0
    can_buy_permission = True if "全倉" in position_mode else False
    positions[0], dca_wait_counter = current_pos, 0

    for i in range(1, len(df)):
        # 判斷全部改用槓桿價格 Price_lev
        p, m, p0, m0 = df["Price_lev"].iloc[i], df["MA_Signal"].iloc[i], df["Price_lev"].iloc[i-1], df["MA_Signal"].iloc[i-1]
        
        if p > m: # 價格在均線上
            if can_buy_permission:
                current_pos = 1.0
                executed_signals[i] = 1 if p0 <= m0 else 0
            else:
                current_pos = 0.0
            dca_wait_counter = 0
        else: # 價格在均線下
            can_buy_permission = True
            if p0 > m0: # 死亡交叉
                current_pos, executed_signals[i], dca_wait_counter = 0.0, -1, 0
            else: # 均線下持續期間
                if enable_dca and current_pos < 1.0:
                    dca_wait_counter += 1
                    if dca_wait_counter >= dca_interval:
                        current_pos = min(1.0, current_pos + (dca_pct / 100.0))
                        executed_signals[i], dca_wait_counter = 2, 0
        positions[i] = round(current_pos, 4)

    df["Signal"], df["Position"] = executed_signals, positions

    # 資金曲線
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity_lrs.append(equity_lrs[-1] * (1 + (lev_ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    ###############################################################
    # 圖表呈現
    ###############################################################

    st.markdown(f"<h3>📌 策略訊號：{lev_label} vs 其 {sma_window}SMA</h3>", unsafe_allow_html=True)
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label}", line=dict(color="#00CC96")))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", dash="dash")))
    
    # 標記訊號
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    dca_pts = df[df["Signal"] == 2]
    
    fig_p.add_trace(go.Scatter(x=buys.index, y=buys["Price_lev"], mode="markers", name="全倉買進", marker=dict(symbol="triangle-up", size=12, color="#00C853")))
    fig_p.add_trace(go.Scatter(x=sells.index, y=sells["Price_lev"], mode="markers", name="清倉賣出", marker=dict(symbol="triangle-down", size=12, color="#D50000")))
    fig_p.add_trace(go.Scatter(x=dca_pts.index, y=dca_pts["Price_lev"], mode="markers", name="DCA 點", marker=dict(symbol="circle", size=6, color="#2E7D32")))
    
    fig_p.update_layout(template="plotly_white", height=450, hovermode="x unified")
    st.plotly_chart(fig_p, use_container_width=True)

    # Tabs (各類分析圖)
    t1, t2, t3, t4 = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])
    with t1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="LRS+DCA (策略)"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿 BH (對照)"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型 BH (對照)"))
        fig_eq.update_layout(template="plotly_white", yaxis_tickformat=".0%")
        st.plotly_chart(fig_eq, use_container_width=True)
    
    with t2:
        for col, name in zip(["Equity_LRS", "Equity_BH_Lev", "Equity_BH_Base"], ["策略", "槓桿BH", "原型BH"]):
            dd = (df[col] / df[col].cummax() - 1) * 100
            st.plotly_chart(go.Figure(go.Scatter(x=df.index, y=dd, name=name, fill="tozeroy")).update_layout(height=300, title=name), use_container_width=True)

    # 指標計算
    y_len = (df.index[-1] - df.index[0]).days / 365
    def get_stats(eq, rets):
        final = eq.iloc[-1]
        cagr = (final)**(1/y_len)-1
        mdd = 1 - (eq / eq.cummax()).min()
        v, sh, so = calc_metrics(rets)
        return final, cagr, mdd, v, sh, so

    s_lrs = get_stats(df["Equity_LRS"], df["Return_LRS"])
    s_lev = get_stats(df["Equity_BH_Lev"], df["Return_lev"])
    s_base = get_stats(df["Equity_BH_Base"], df["Return_base"])

    # KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", format_currency(s_lrs[0]*capital), f"{((s_lrs[0]/s_lev[0])-1)*100:.2f}% vs 槓桿")
    k2.metric("CAGR", format_percent(s_lrs[1]), f"{(s_lrs[1]-s_lev[1])*100:.2f}%")
    k3.metric("最大回撤", format_percent(s_lrs[2]), f"{(s_lrs[2]-s_lev[2])*100:.2f}%", delta_color="inverse")
    k4.metric("交易次數", int((df["Signal"] != 0).sum()))

    # 比較表格 HTML
    st.markdown("### 📊 績效詳細對照表")
    metrics = ["期末資產", "CAGR (年化)", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio"]
    data = {
        "LRS+DCA (策略)": [s_lrs[0]*capital, s_lrs[1], s_lrs[2], s_lrs[3], s_lrs[4]],
        f"{lev_label} BH": [s_lev[0]*capital, s_lev[1], s_lev[2], s_lev[3], s_lev[4]],
        f"{base_label} BH": [s_base[0]*capital, s_base[1], s_base[2], s_base[3], s_base[4]]
    }
    comp_df = pd.DataFrame(data, index=metrics)
    st.table(comp_df.style.format({col: "{:,.2f}" for col in comp_df.columns}))
