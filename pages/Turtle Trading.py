###############################################################
# app.py — 順勢突破 + 動能加碼 (Donchian + Pyramiding + SMA Stop + ATR Risk)
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
    page_title="0050LRS 順勢突破加碼策略",
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

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 順勢突破加碼系統 (Donchian + SMA Stop)</h1>", unsafe_allow_html=True)

st.info("""
**策略邏輯：**
1. **進場：** 收盤價突破過去 **20 日最高價** (Donchian Breakout)。
2. **加碼：** 進場後每當價格創 **波段新高**，加碼 20% 部位。
3. **出場：** 收盤價跌破 **60 日均線** (Trend Stop)。
4. **風控：** 透過 **ATR 波動率** 動態調整加碼力道，波動過大時減少單次投入比例。
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
    # 為了計算 ATR 與 Donchian，需保留 High, Low, Close
    for col in ["High", "Low", "Close"]:
        if col not in df.columns:
            df[col] = df["Price"] if "Price" in df.columns else df.iloc[:, 0]
    df["Price"] = df["Close"]
    return df[["High", "Low", "Close", "Price"]]

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

col3, col4, col5 = st.columns(3)
with col3: start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4: end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5: capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)

st.write("### ⚙️ 策略參數設定")
col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1: breakout_window = st.number_input("進場：創 N 日新高", 10, 120, 20, 5)
with col_p2: stop_window = st.number_input("出場：跌破 N 日均線", 10, 240, 60, 10)
with col_p3: pyramid_pct = st.number_input("加碼比例 (%)", 5, 100, 20, 5)
with col_p4: target_vol = st.number_input("目標日波動率 (ATR 風控)", 0.5, 5.0, 2.0, 0.1, help="當實際波動大於此值，加碼比例會降低。")

###############################################################
# 核心回測運算
###############################################################

if st.button("開始回測 🚀"):
    # 多抓一些早期資料來算長天期均線和通道
    start_early = start - dt.timedelta(days=int(max(breakout_window, stop_window) * 1.5) + 30)
    df_base_raw, df_lev_raw = load_csv(base_symbol), load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗"); st.stop()

    df = pd.DataFrame(index=df_base_raw.loc[start_early:end].index)
    df["Price_base"] = df_base_raw["Close"]
    
    # 槓桿 ETF 資料 (需包含 H, L, C 計算指標)
    df = df.join(df_lev_raw[["High", "Low", "Close"]].rename(
        columns={"High": "High_lev", "Low": "Low_lev", "Close": "Price_lev"}
    ), how="inner").sort_index()

    # --- 計算技術指標 (Shift(1) 避免未來數據) ---
    # 1. Donchian 20日高點
    df["Donchian_High"] = df["High_lev"].rolling(breakout_window).max().shift(1)
    
    # 2. 60日均線
    df["SMA_Stop"] = df["Price_lev"].rolling(stop_window).mean().shift(1)
    
    # 3. ATR (Average True Range) 計算
    df["Prev_Close"] = df["Price_lev"].shift(1)
    tr1 = df["High_lev"] - df["Low_lev"]
    tr2 = (df["High_lev"] - df["Prev_Close"]).abs()
    tr3 = (df["Low_lev"] - df["Prev_Close"]).abs()
    df["TR"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = df["TR"].rolling(20).mean().shift(1) # 預設 20 日 ATR

    # 截取使用者選擇的日期區間
    df = df.dropna(subset=["SMA_Stop", "Donchian_High", "ATR"]).loc[start:end]

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # --- 策略執行邏輯 ---
    executed_signals = [0] * len(df) # 1: 進場, 2: 加碼, -1: 出場
    positions = [0.0] * len(df)
    
    current_pos = 0.0
    highest_since_entry = 0.0
    base_increment = pyramid_pct / 100.0

    for i in range(1, len(df)):
        c = df["Price_lev"].iloc[i]
        donchian_h = df["Donchian_High"].iloc[i]
        sma_stop = df["SMA_Stop"].iloc[i]
        atr = df["ATR"].iloc[i]
        
        # 波動率縮放係數 (ATR 風控)
        current_vol_pct = (atr / c) * 100
        vol_scalar = target_vol / current_vol_pct if current_vol_pct > 0 else 1.0
        # 如果波動過大，vol_scalar < 1，加碼力道變小；限制最大加碼為設定的 base_increment
        actual_increment = min(base_increment, base_increment * vol_scalar)

        if current_pos == 0.0:
            # 條件 1：空手時，突破 20 日新高 -> 進場
            if c > donchian_h:
                current_pos = actual_increment
                highest_since_entry = c
                executed_signals[i] = 1
        else:
            # 條件 3：有部位時，跌破 60 日均線 -> 停損/停利出場
            if c < sma_stop:
                current_pos = 0.0
                highest_since_entry = 0.0
                executed_signals[i] = -1
            # 條件 2：持續在均線之上，且創進場後收盤新高 -> 加碼
            elif c > highest_since_entry:
                highest_since_entry = c
                if current_pos < 1.0: # 總部位上限 100%
                    current_pos = min(1.0, current_pos + actual_increment)
                    executed_signals[i] = 2 # 標記為加碼
                    
        positions[i] = round(current_pos, 4)

    df["Signal"] = executed_signals
    df["Position"] = positions

    # --- 資金曲線計算 ---
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        # 當天報酬 = 指數報酬 * 前一天的部位曝險
        equity_lrs.append(equity_lrs[-1] * (1 + (lev_ret * df["Position"].iloc[i-1])))
    
    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    ###############################################################
    # 圖表呈現
    ###############################################################

    st.markdown(f"<h3>📌 策略訊號與技術指標分析</h3>", unsafe_allow_html=True)
    fig_p = go.Figure()
    
    # 價格與指標線
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label} 價格", line=dict(color="#2980b9")))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Donchian_High"], name=f"{breakout_window}日高點 (進場線)", line=dict(color="#27ae60", dash="dot"), opacity=0.7))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["SMA_Stop"], name=f"{stop_window}SMA (出場線)", line=dict(color="#e74c3c", dash="dash")))
    
    # 標記訊號
    buys = df[df["Signal"] == 1]
    pyramids = df[df["Signal"] == 2]
    sells = df[df["Signal"] == -1]
    
    fig_p.add_trace(go.Scatter(x=buys.index, y=buys["Price_lev"], mode="markers", name="首發進場", marker=dict(symbol="triangle-up", size=14, color="#00C853", line=dict(width=2, color='DarkSlateGrey'))))
    fig_p.add_trace(go.Scatter(x=pyramids.index, y=pyramids["Price_lev"], mode="markers", name="創高加碼", marker=dict(symbol="chevron-up", size=10, color="#f1c40f")))
    fig_p.add_trace(go.Scatter(x=sells.index, y=sells["Price_lev"], mode="markers", name="均線出場", marker=dict(symbol="triangle-down", size=14, color="#D50000", line=dict(width=2, color='DarkSlateGrey'))))
    
    fig_p.update_layout(template="plotly_white", height=550, hovermode="x unified")
    st.plotly_chart(fig_p, use_container_width=True)

    # Tabs (各類分析圖)
    t1, t2, t3, t4 = st.tabs(["部位曝險與資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])
    with t1:
        # 子圖表：上面是淨值，下面是部位變化
        from plotly.subplots import make_subplots
        fig_eq = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="策略 (LRS)"), row=1, col=1)
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿 BH"), row=1, col=1)
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型 BH"), row=1, col=1)
        
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Position"], name="持倉比例", fill='tozeroy', line=dict(color="purple")), row=2, col=1)
        
        fig_eq.update_layout(template="plotly_white", height=600)
        fig_eq.update_yaxes(tickformat=".0%", row=1, col=1)
        fig_eq.update_yaxes(tickformat=".0%", range=[0, 1.1], title_text="Position", row=2, col=1)
        st.plotly_chart(fig_eq, use_container_width=True)
    
    with t2:
        for col, name in zip(["Equity_LRS", "Equity_BH_Lev", "Equity_BH_Base"], ["策略", "槓桿BH", "原型BH"]):
            dd = (df[col] / df[col].cummax() - 1) * 100
            st.plotly_chart(go.Figure(go.Scatter(x=df.index, y=dd, name=name, fill="tozeroy")).update_layout(height=250, title=name, margin=dict(t=30, b=0)), use_container_width=True)

    # 指標計算
    y_len = (df.index[-1] - df.index[0]).days / 365
    def get_stats(eq, rets):
        final = eq.iloc[-1]
        cagr = (final)**(1/y_len)-1 if y_len > 0 else 0
        mdd = 1 - (eq / eq.cummax()).min()
        v, sh, so = calc_metrics(rets)
        return final, cagr, mdd, v, sh, so

    s_lrs = get_stats(df["Equity_LRS"], df["Return_LRS"])
    s_lev = get_stats(df["Equity_BH_Lev"], df["Return_lev"])
    s_base = get_stats(df["Equity_BH_Base"], df["Return_base"])

    # KPI Cards
    st.write("### 🏆 回測績效摘要")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("期末資產", format_currency(s_lrs[0]*capital), f"{((s_lrs[0]/s_lev[0])-1)*100:.2f}% vs 槓桿")
    k2.metric("CAGR", format_percent(s_lrs[1]), f"{(s_lrs[1]-s_lev[1])*100:.2f}%")
    k3.metric("最大回撤", format_percent(s_lrs[2]), f"{(s_lrs[2]-s_lev[2])*100:.2f}%", delta_color="inverse")
    
    # 計算進出場與加碼次數
    num_trades = int((df["Signal"] == 1).sum())
    num_pyramids = int((df["Signal"] == 2).sum())
    k4.metric("交易數據", f"{num_trades} 次進場", f"{num_pyramids} 次加碼", delta_color="off")

    # 比較表格 HTML
    st.markdown("### 📊 績效詳細對照表")
    metrics = ["期末資產", "CAGR (年化)", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio"]
    data = {
        "順勢突破策略": [s_lrs[0]*capital, s_lrs[1], s_lrs[2], s_lrs[3], s_lrs[4]],
        f"{lev_label} (Buy&Hold)": [s_lev[0]*capital, s_lev[1], s_lev[2], s_lev[3], s_lev[4]],
        f"{base_label} (Buy&Hold)": [s_base[0]*capital, s_base[1], s_base[2], s_base[3], s_base[4]]
    }
    comp_df = pd.DataFrame(data, index=metrics)
    st.table(comp_df.style.format({col: "{:,.2f}" for col in comp_df.columns}))
