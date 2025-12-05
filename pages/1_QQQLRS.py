###############################################################
# app.py — CSV 版 QQQ LRS 回測 (QQQ / QLD / TQQQ)
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

###############################################################
# 字型設定 (維持不變，確保中文顯示正常)
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
    page_title="QQQ LRS 回測系統",
    page_icon="🦅",
    layout="wide",
)
# ------------------------------------------------------
# 🔒 驗證守門員 (必須放在 set_page_config 之後，sidebar 之前)
# ------------------------------------------------------
import sys
# 讓 pages 資料夾能讀到根目錄的 auth.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import auth 

if not auth.check_password():
    st.stop()  # 驗證沒過就停止執行
# ------------------------------------------------------

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
     

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 QQQ LRS 動態槓桿策略回測</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較三種策略 (美股 Nasdaq 100 系列)：</b><br>
1️⃣ <b>原型 Buy & Hold</b>：持有 QQQ (納斯達克100 ETF)<br>
2️⃣ <b>槓桿 Buy & Hold</b>：持有 QLD (2倍) 或 TQQQ (3倍)<br>
3️⃣ <b>LRS 動態槓桿</b>：以 QQQ 200日均線為訊號，操作槓桿 ETF (站上均線持有槓桿，跌破均線空手或轉保守)<br>
<small>（請確保 data 資料夾內有 QQQ.csv, QLD.csv, TQQQ.csv）</small>
""",
    unsafe_allow_html=True,
)

###############################################################
# ETF 名稱清單 (修改處)
###############################################################

# 字典格式： {"顯示名稱": "CSV檔名(不含.csv)"}
BASE_ETFS = {
    "QQQ Invesco納斯達克100信託": "QQQ",
}

LEV_ETFS = {
    "QLD ProShares兩倍做多 (2x)": "QLD",
    "TQQQ ProShares三倍做多 (3x)": "TQQQ",
}

WINDOW = 200  # 固定 200 日 SMA

DATA_DIR = Path("data")

###############################################################
# 讀取 CSV
###############################################################

def load_csv(symbol: str) -> pd.DataFrame:
    # 這裡會讀取 data/QQQ.csv 或 data/TQQQ.csv
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    # 兼容性處理：美股 CSV 通常是 Close 或 Adj Close
    col_name = "Adj Close" if "Adj Close" in df.columns else "Close"
    df["Price"] = df[col_name]
    return df[["Price"]]


def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1 = load_csv(base_symbol)
    df2 = load_csv(lev_symbol)

    if df1.empty or df2.empty:
        # 預設時間若讀不到檔案
        return dt.date(2010, 1, 1), dt.date.today()

    start = max(df1.index.min().date(), df2.index.min().date())
    end = min(df1.index.max().date(), df2.index.max().date())
    return start, end

###############################################################
# 工具函式 (修改幣別顯示)
###############################################################

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1:
        return np.nan, np.nan, np.nan
    avg = daily.mean()
    std = daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

# 修改為美金格式
def fmt_money(v):
    try: return f"${v:,.2f}"
    except: return "—"

def format_currency(v):
    try: return f"${v:,.2f}"
    except: return "—"

def fmt_pct(v, d=2):
    try: return f"{v:.{d}%}"
    except: return "—"

def fmt_num(v, d=2):
    try: return f"{v:.{d}f}"
    except: return "—"

def fmt_int(v):
    try: return f"{int(v):,}"
    except: return "—"

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

def format_percent(v, d=2):
    try: return f"{v*100:.{d}f}%"
    except: return "—"

def format_number(v, d=2):
    try: return f"{v:.{d}f}"
    except: return "—"

###############################################################
# UI 輸入
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 資料庫可回測區間：{s_min} ~ {s_max}")

col3, col4, col5 = st.columns(3)
with col3:
    # 預設回測 5 年，或資料的最早開始時間
    default_start = max(s_min, s_max - dt.timedelta(days=10 * 365))
    start = st.date_input(
        "開始日期",
        value=default_start,
        min_value=s_min, max_value=s_max,
    )

with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)

with col5:
    capital = st.number_input(
        "投入本金 (USD)", 1_000, 10_000_000, 10_000, step=1_000,
    )

position_mode = st.radio(
    "策略初始狀態",
    ["空手起跑 (標準 LRS)", "一開始就全倉槓桿 ETF"],
    index=0,
)

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=365) # 預讀一年算 MA

    with st.spinner(f"讀取 {base_symbol} 與 {lev_symbol} 資料中…"):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error(f"⚠️ 資料讀取失敗！請確認 data 資料夾內是否有 {base_symbol}.csv 與 {lev_symbol}.csv")
        st.stop()

    df_base_raw = df_base_raw.loc[start_early:end]
    df_lev_raw = df_lev_raw.loc[start_early:end]

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner")
    df = df.sort_index()

    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df = df.dropna(subset=["MA_200"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足 (可能是 MA 計算導致前段資料被截除)")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    ###############################################################
    # LRS 訊號
    ###############################################################

    df["Signal"] = 0
    for i in range(1, len(df)):
        p, m = df["Price_base"].iloc[i], df["MA_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]

        # 黃金交叉 (站上 MA)
        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        # 死亡交叉 (跌破 MA)
        elif p < m and p0 >= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = -1

    ###############################################################
    # Position
    ###############################################################

    current_pos = 0 if "空手" in position_mode else 1
    df["Position"] = [
        current_pos := (1 if s == 1 else 0 if s == -1 else current_pos)
        for s in df["Signal"]
    ]

    ###############################################################
    # 資金曲線
    ###############################################################

    equity_lrs = [1.0]
    for i in range(1, len(df)):
        # 若持有部位
        if df["Position"].iloc[i] == 1 and df["Position"].iloc[i-1] == 1:
            r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]
            equity_lrs.append(equity_lrs[-1] * r)
        else:
            # 空手 (持有現金，假設報酬為 0)
            equity_lrs.append(equity_lrs[-1])

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)

    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    df["Pct_Base"] = df["Equity_BH_Base"] - 1
    df["Pct_Lev"] = df["Equity_BH_Lev"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]

    ###############################################################
    # 指標計算
    ###############################################################

    years_len = (df.index[-1] - df.index[0]).days / 365

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = final_eq - 1
        cagr = (1 + final_ret)**(1/years_len) - 1 if years_len > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else np.nan
        return final_eq, final_ret, cagr, mdd, vol, sharpe, sortino, calmar

    eq_lrs_final, final_ret_lrs, cagr_lrs, mdd_lrs, vol_lrs, sharpe_lrs, sortino_lrs, calmar_lrs = calc_core(
        df["Equity_LRS"], df["Return_LRS"]
    )
    eq_lev_final, final_ret_lev, cagr_lev, mdd_lev, vol_lev, sharpe_lev, sortino_lev, calmar_lev = calc_core(
        df["Equity_BH_Lev"], df["Return_lev"]
    )
    eq_base_final, final_ret_base, cagr_base, mdd_base, vol_base, sharpe_base, sortino_base, calmar_base = calc_core(
        df["Equity_BH_Base"], df["Return_base"]
    )

    capital_lrs_final = eq_lrs_final * capital
    capital_lev_final = eq_lev_final * capital
    capital_base_final = eq_base_final * capital
    trade_count_lrs = int((df["Signal"] != 0).sum())

    ###############################################################
    # 視覺化區塊
    ###############################################################

    # --- 原型 & MA ---
    st.markdown(f"<h3>📌 {base_label.split(' ')[0]} 價格 & 200SMA (訊號來源)</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_symbol}", mode="lines"))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200 日 SMA", mode="lines"))

    if not buys.empty:
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price_base"], mode="markers",
            name="買進訊號 (Buy)", marker=dict(color="green", size=10, symbol="triangle-up")
        ))

    if not sells.empty:
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price_base"], mode="markers",
            name="賣出訊號 (Sell)", marker=dict(color="red", size=10, symbol="triangle-down")
        ))

    fig_price.update_layout(template="plotly_white", height=420)
    st.plotly_chart(fig_price, use_container_width=True)

    # ###############################################################
    # Tabs
    # ###############################################################

    st.markdown("<h3>📊 策略績效與風險分析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["💰 資金曲線", "📉 回撤比較", "🕸️ 風險雷達", "📊 日報酬分佈"])

    # --- 資金曲線 ---
    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name=f"{base_symbol} (原型)"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name=f"{lev_symbol} (槓桿BH)"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS 策略", line=dict(width=3)))

        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    # --- 回撤 ---
    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型 BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿 BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS 策略", fill="tozeroy"))

        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    # --- 雷達 ---
    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]

        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill="toself", name="LRS 策略"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill="toself", name="槓桿 BH"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base, theta=radar_categories, fill="toself", name="原型 BH"))

        fig_radar.update_layout(template="plotly_white", height=480)
        st.plotly_chart(fig_radar, use_container_width=True)

    # --- 日報酬分佈 ---
    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型 BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿 BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS 策略", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480, xaxis_title="日漲跌幅 (%)")

        st.plotly_chart(fig_hist, use_container_width=True)

    ###############################################################
    # KPI Summary
    ###############################################################

    asset_gap_lrs_vs_lev = ((capital_lrs_final / capital_lev_final) - 1) * 100
    cagr_gap_lrs_vs_lev = (cagr_lrs - cagr_lev) * 100
    vol_gap_lrs_vs_lev = (vol_lrs - vol_lev) * 100
    mdd_gap_lrs_vs_lev = (mdd_lrs - mdd_lev) * 100

    row1 = st.columns(4)
    with row1[0]:
        st.metric("期末資產 (LRS)", format_currency(capital_lrs_final),
                  f"較槓桿BH {asset_gap_lrs_vs_lev:+.2f}%")
    with row1[1]:
        st.metric("CAGR (LRS)", format_percent(cagr_lrs),
                  f"較槓桿BH {cagr_gap_lrs_vs_lev:+.2f}%")
    with row1[2]:
        st.metric("年化波動 (LRS)", format_percent(vol_lrs),
                  f"較槓桿BH {vol_gap_lrs_vs_lev:+.2f}%", delta_color="inverse")
    with row1[3]:
        st.metric("最大回撤 (LRS)", format_percent(mdd_lrs),
                  f"較槓桿BH {mdd_gap_lrs_vs_lev:+.2f}%", delta_color="inverse")

    ###############################################################
    # 完整比較表格
    ###############################################################
    
    raw_table = pd.DataFrame([
        {
            "策略": f"{lev_label.split(' ')[0]} LRS 策略",
            "期末資產": capital_lrs_final,
            "總報酬率": final_ret_lrs,
            "CAGR (年化)": cagr_lrs,
            "Calmar Ratio": calmar_lrs,
            "最大回撤 (MDD)": mdd_lrs,
            "年化波動": vol_lrs,
            "Sharpe": sharpe_lrs,
            "Sortino": sortino_lrs,
            "交易次數": trade_count_lrs,
        },
        {
            "策略": f"{lev_label.split(' ')[0]} Buy&Hold",
            "期末資產": capital_lev_final,
            "總報酬率": final_ret_lev,
            "CAGR (年化)": cagr_lev,
            "Calmar Ratio": calmar_lev,
            "最大回撤 (MDD)": mdd_lev,
            "年化波動": vol_lev,
            "Sharpe": sharpe_lev,
            "Sortino": sortino_lev,
            "交易次數": np.nan,
        },
        {
            "策略": f"{base_label.split(' ')[0]} Buy&Hold",
            "期末資產": capital_base_final,
            "總報酬率": final_ret_base,
            "CAGR (年化)": cagr_base,
            "Calmar Ratio": calmar_base,
            "最大回撤 (MDD)": mdd_base,
            "年化波動": vol_base,
            "Sharpe": sharpe_base,
            "Sortino": sortino_base,
            "交易次數": np.nan,
        },
    ]).reset_index(drop=True)

    # --- 格式化表格 (顯示用) ---
    formatted = raw_table.copy()
    formatted["期末資產"] = formatted["期末資產"].apply(fmt_money)
    formatted["總報酬率"] = formatted["總報酬率"].apply(fmt_pct)
    formatted["CAGR (年化)"] = formatted["CAGR (年化)"].apply(fmt_pct)
    formatted["Calmar Ratio"] = formatted["Calmar Ratio"].apply(fmt_num)
    formatted["最大回撤 (MDD)"] = formatted["最大回撤 (MDD)"].apply(fmt_pct)
    formatted["年化波動"] = formatted["年化波動"].apply(fmt_pct)
    formatted["Sharpe"] = formatted["Sharpe"].apply(fmt_num)
    formatted["Sortino"] = formatted["Sortino"].apply(fmt_num)
    formatted["交易次數"] = formatted["交易次數"].apply(fmt_int)

    # --- Styler ---
    styled = formatted.style

    # 置中樣式
    styled = styled.set_properties(**{"text-align": "center"})
    styled = styled.set_properties(
        subset=["策略"],
        **{"font-weight": "bold", "color": "#2c7be5"}
    )

    # --- Heatmap 欄位 ---
    heat_cols = [
        "期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio",
        "最大回撤 (MDD)", "年化波動", "Sharpe", "Sortino"
    ]

    from matplotlib import cm

    def colormap(series, cmap_name="RdYlGn"):
        s = series.astype(float).fillna(0.0)
        if s.max() - s.min() < 1e-9:
            norm = (s - s.min())
        else:
            norm = (s - s.min()) / (s.max() - s.min())
        cmap = cm.get_cmap(cmap_name)
        return norm.map(lambda x: f"background-color: rgba{cmap(x)}")

    for col in heat_cols:
        # MDD 和 波動率 越小越好 (反轉顏色: RdYlGn_r)
        c_map = "RdYlGn_r" if col in ["最大回撤 (MDD)", "年化波動"] else "RdYlGn"
        styled = styled.apply(lambda s: colormap(raw_table[col], c_map), subset=[col])

    styled = styled.set_table_styles([
        {"selector": "tbody tr:hover", "props": [("background-color", "#f0f8ff")]},
        {"selector": "th", "props": [("text-align", "center")]},
    ])

    styled = styled.hide(axis="index")

    st.write(styled.to_html(), unsafe_allow_html=True)
