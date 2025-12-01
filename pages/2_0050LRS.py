###############################################################
# app.py — 0050LRS 回測（0050 / 006208 + 正2 槓桿 ETF）
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go

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
    page_title="0050LRS 回測系統",
    page_icon="📈",
    layout="wide",
)
st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 槓桿策略回測</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold（0050 / 006208）<br>
2️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
3️⃣ 槓桿 ETF LRS（訊號來自原型 ETF 的 200 日 SMA，實際進出槓桿 ETF）<br>
<small>（價格已採用 yfinance 調整後收盤價，含拆股與股利再投資效果）</small>
""",
    unsafe_allow_html=True,
)

###############################################################
# ETF 名稱清單
###############################################################

BASE_ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
}

LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}

WINDOW = 200  # 固定 200 日 SMA

###############################################################
# 工具函式（新增格式化函式）
###############################################################

def calc_metrics(series: pd.Series):
    """計算年化波動率、Sharpe、Sortino"""
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

def fmt_money(v):
    try:
        return f"{v:,.0f} 元"
    except:
        return "—"

def fmt_pct(v, d=2):
    try:
        return f"{v:.{d}%}"
    except:
        return "—"

def fmt_num(v, d=2):
    try:
        return f"{v:.{d}f}"
    except:
        return "—"

def fmt_int(v):
    try:
        return f"{int(v):,}"
    except:
        return "—"

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

# 🔥 新增：KPI 使用的格式化函式
def format_currency(v):
    try:
        return f"{v:,.0f} 元"
    except:
        return "—"

def format_percent(v, d=2):
    try:
        return f"{v*100:.{d}f}%"
    except:
        return "—"

def format_number(v, d=2):
    try:
        return f"{v:.{d}f}"
    except:
        return "—"

###############################################################
# yfinance 下載資料
###############################################################

@st.cache_data(show_spinner=False)
def fetch_history(symbol: str, start: dt.date, end: dt.date):
    df = yf.download(symbol, start=start, end=end, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    df = df.sort_index()
    df = df[~df.index.duplicated()]

    if "Close" in df.columns:
        df["Price"] = df["Close"]
    elif "Adj Close" in df.columns:
        df["Price"] = df["Adj Close"]
    else:
        df["Price"] = df[df.columns[0]]

    return df[["Price"]]

@st.cache_data(show_spinner=False)
def load_price(symbol: str, start: dt.date, end: dt.date):
    df = fetch_history(symbol, start, end)
    return df[["Price"]] if not df.empty else df

@st.cache_data(show_spinner=False)
def get_full_range(base_symbol: str, lev_symbol: str):
    b = yf.Ticker(base_symbol).history(period="max", auto_adjust=True)
    l = yf.Ticker(lev_symbol).history(period="max", auto_adjust=True)
    if b.empty or l.empty:
        return dt.date(2012, 1, 1), dt.date.today()
    b = b.sort_index()
    l = l.sort_index()
    return max(b.index.min().date(), l.index.min().date()), min(b.index.max().date(), l.index.max().date())

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

s_min, s_max = get_full_range(base_symbol, lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input(
        "開始日期",
        value=max(s_min, s_max - dt.timedelta(days=5 * 365)),
        min_value=s_min,
        max_value=s_max,
    )
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input(
        "投入本金（元）",
        1000,
        5_000_000,
        100_000,
        step=10_000,
    )

position_mode = st.radio(
    "策略初始狀態",
    ["空手起跑（標準 LRS）", "一開始就全倉槓桿 ETF"],
    index=0,
)

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    if start >= end:
        st.error("⚠️ 開始日期需早於結束日期")
        st.stop()

    start_early = start - dt.timedelta(days=365)

    with st.spinner("下載資料中…"):
        df_base_raw = load_price(base_symbol, start_early, end)
        df_lev_raw = load_price(lev_symbol, start_early, end)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ ETF 資料抓取失敗")
        st.stop()

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner")
    df = df.sort_index()
    df = df[(df.index >= pd.to_datetime(start_early)) & (df.index <= pd.to_datetime(end))]

    # 200 SMA
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df = df.dropna(subset=["MA_200"])

    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)].copy()
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    # 報酬
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    ###############################################################
    # LRS 訊號
    ###############################################################

    df["Signal"] = 0
    for i in range(1, len(df)):
        p, m = df["Price_base"].iloc[i], df["MA_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i - 1], df["MA_200"].iloc[i - 1]
        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif p < m and p0 >= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = -1

    ###############################################################
    # Position
    ###############################################################

    current_pos = 0 if "空手" in position_mode else 1
    df["Position"] = [current_pos := (1 if s == 1 else 0 if s == -1 else current_pos) for s in df["Signal"]]

    ###############################################################
    # LRS 資金曲線
    ###############################################################

    equity_lrs = [1.0]
    for i in range(1, len(df)):
        if df["Position"].iloc[i] == 1 and df["Position"].iloc[i - 1] == 1:
            r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i - 1]
            equity_lrs.append(equity_lrs[-1] * r)
        else:
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

    years_len = (df.index[-1] - df.index[0]).days / 365 if len(df) > 1 else 0

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = final_eq - 1
        cagr = (1 + final_ret) ** (1 / years_len) - 1 if years_len > 0 else np.nan
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
    # 價格圖（含買賣點）
    ###############################################################

    st.markdown("<h3>📌 原型 ETF 價格 & 200SMA（訊號來源）</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    fig_price.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Price_base"],
            name=f"{base_label} 收盤價",
            mode="lines",
            line=dict(color="#1f77b4", width=2),
        )
    )

    fig_price.add_trace(
        go.Scatter(
            x=df.index,
            y=df["MA_200"],
            name="200 日 SMA",
            mode="lines",
            line=dict(color="#7f7f7f", width=2),
        )
    )

    # 買點
    if not buys.empty:
        fig_price.add_trace(
            go.Scatter(
                x=buys.index,
                y=buys["Price_base"],
                mode="markers",
                name="買進 Buy",
                marker=dict(symbol="circle-open", size=12, line=dict(width=2, color="#2ca02c")),
                customdata=buys["Price_lev"],
                hovertemplate=(
                    "📈 <b>買進訊號</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    + base_label + ": %{y:.2f}<br>"
                    + lev_label + ": %{customdata:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )

    # 賣點
    if not sells.empty:
        fig_price.add_trace(
            go.Scatter(
                x=sells.index,
                y=sells["Price_base"],
                mode="markers",
                name="賣出 Sell",
                marker=dict(symbol="circle-open", size=12, line=dict(width=2, color="#d62728")),
                customdata=sells["Price_lev"],
                hovertemplate=(
                    "📉 <b>賣出訊號</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    + base_label + ": %{y:.2f}<br>"
                    + lev_label + ": %{customdata:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )

    fig_price.update_layout(
        template="plotly_white",
        height=480,
        margin=dict(l=40, r=60, t=40, b=40),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_price, use_container_width=True)


    ###############################################################
    # Tabs：資金曲線 / 回撤 / 雷達圖 / 日報酬分佈
    ###############################################################

    st.markdown("<h3>📊 三策略資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])


    # ============================
    # 資金曲線
    # ============================
    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name=f"{base_label} BH（原型）"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name=f"{lev_label} BH（槓桿）"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name=f"{lev_label} LRS 槓桿策略"))

        fig_equity.update_layout(
            template="plotly_white",
            height=420,
            legend=dict(orientation="h"),
            yaxis=dict(tickformat=".0%"),
        )
        st.plotly_chart(fig_equity, use_container_width=True)


    # ============================
    # 回撤
    # ============================
    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name=f"{base_label} BH（原型）"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name=f"{lev_label} BH（槓桿）"))
        fig_dd.add_trace(
            go.Scatter(
                x=df.index,
                y=dd_lrs,
                name=f"{lev_label} LRS 槓桿策略",
                fill="tozeroy",
                fillcolor="rgba(231, 126, 34, 0.08)",
            )
        )
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)


    # ============================
    # 風險雷達圖
    # ============================
    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]

        radar_lrs = [nz(cagr_lrs), nz(sharpe_lrs), nz(sortino_lrs), nz(-mdd_lrs), nz(-vol_lrs)]
        radar_lev = [nz(cagr_lev), nz(sharpe_lev), nz(sortino_lev), nz(-mdd_lev), nz(-vol_lev)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill="toself", name="LRS"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill="toself", name="槓桿BH"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base, theta=radar_categories, fill="toself", name="原型BH"))
        fig_radar.update_layout(template="plotly_white", height=480)

        st.plotly_chart(fig_radar, use_container_width=True)


    # ============================
    # 日報酬直方圖
    # ============================
    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)

        st.plotly_chart(fig_hist, use_container_width=True)


    ###############################################################
    # KPI Summary Cards（比較三策略）
    ###############################################################


    # LRS vs 槓桿 BH
    asset_gap_lrs_vs_lev = ((capital_lrs_final / capital_lev_final) - 1) * 100
    cagr_gap_lrs_vs_lev = (cagr_lrs - cagr_lev) * 100
    vol_gap_lrs_vs_lev = (vol_lrs - vol_lev) * 100
    mdd_gap_lrs_vs_lev = (mdd_lrs - mdd_lev) * 100

    row1 = st.columns(4)
    with row1[0]:
        st.metric(
            label=f"期末資產（{lev_label} LRS）",
            value=format_currency(capital_lrs_final),
            delta=f"較 槓桿BH {asset_gap_lrs_vs_lev:+.2f}%",
        )

    with row1[1]:
        st.metric(
            label="年化報酬（CAGR, LRS）",
            value=format_percent(cagr_lrs),
            delta=f"較 槓桿BH {cagr_gap_lrs_vs_lev:+.2f}%",
        )

    with row1[2]:
        st.metric(
            label="年化波動（LRS）",
            value=format_percent(vol_lrs),
            delta=f"較 槓桿BH {vol_gap_lrs_vs_lev:+.2f}%",
            delta_color="inverse",
        )

    with row1[3]:
        st.metric(
            label="最大回撤（LRS）",
            value=format_percent(mdd_lrs),
            delta=f"較 槓桿BH {mdd_gap_lrs_vs_lev:+.2f}%",
            delta_color="inverse",
        )




    ###############################################################
    # 表格（策略完整比較）
    ###############################################################



    metrics_table = pd.DataFrame(
        [
            {
                "策略": f"{lev_label} LRS 槓桿策略",
                "期末資產": capital_lrs_final,
                "總報酬率": final_ret_lrs,
                "CAGR（年化）": cagr_lrs,
                "Calmar Ratio": calmar_lrs,
                "最大回撤（MDD）": mdd_lrs,
                "年化波動": vol_lrs,
                "Sharpe": sharpe_lrs,
                "Sortino": sortino_lrs,
                "交易次數": trade_count_lrs,
            },
            {
                "策略": f"{lev_label} BH（槓桿）",
                "期末資產": capital_lev_final,
                "總報酬率": final_ret_lev,
                "CAGR（年化）": cagr_lev,
                "Calmar Ratio": calmar_lev,
                "最大回撤（MDD）": mdd_lev,
                "年化波動": vol_lev,
                "Sharpe": sharpe_lev,
                "Sortino": sortino_lev,
                "交易次數": np.nan,
            },
            {
                "策略": f"{base_label} BH（原型）",
                "期末資產": capital_base_final,
                "總報酬率": final_ret_base,
                "CAGR（年化）": cagr_base,
                "Calmar Ratio": calmar_base,
                "最大回撤（MDD）": mdd_base,
                "年化波動": vol_base,
                "Sharpe": sharpe_base,
                "Sortino": sortino_base,
                "交易次數": np.nan,
            },
        ]
    )

    raw_table = metrics_table.copy()

    formatted = metrics_table.copy()
    formatted["期末資產"] = formatted["期末資產"].apply(fmt_money)
    formatted["總報酬率"] = formatted["總報酬率"].apply(fmt_pct)
    formatted["CAGR（年化）"] = formatted["CAGR（年化）"].apply(fmt_pct)
    formatted["Calmar Ratio"] = formatted["Calmar Ratio"].apply(fmt_num)
    formatted["最大回撤（MDD）"] = formatted["最大回撤（MDD）"].apply(fmt_pct)
    formatted["年化波動"] = formatted["年化波動"].apply(fmt_pct)
    formatted["Sharpe"] = formatted["Sharpe"].apply(fmt_num)
    formatted["Sortino"] = formatted["Sortino"].apply(fmt_num)
    formatted["交易次數"] = formatted["交易次數"].apply(fmt_int)

    styled = formatted.style.set_properties(subset=["策略"], **{"font-weight": "bold", "color": "#2c7be5"})

    highlight_rules = {
        "期末資產": "high",
        "總報酬率": "high",
        "CAGR（年化）": "high",
        "Calmar Ratio": "high",
        "最大回撤（MDD）": "low",
        "年化波動": "low",
        "Sharpe": "high",
        "Sortino": "high",
    }

    for col, direction in highlight_rules.items():
        valid = raw_table[col].dropna()
        if valid.empty:
            continue
        best = valid.max() if direction == "high" else valid.min()

        def style_col(_):
            styles = []
            for idx in raw_table.index:
                val = raw_table.loc[idx, col]
                is_best = (not np.isnan(val)) and (val == best)
                styles.append("color: #28a745; font-weight: bold;" if is_best else "color: #d9534f;")
            return styles

        styled = styled.apply(style_col, subset=[col], axis=0)

    st.write(styled.to_html(), unsafe_allow_html=True)


    ###############################################################
    # Footer：新版指標與策略說明
    ###############################################################

    st.markdown(
        """
<div style="
    margin-top: 20px;
    padding: 18px 22px;
    border-left: 4px solid #4A90E2;
    background: rgba(0,0,0,0.03);
    border-radius: 6px;
    font-size: 15px;
    line-height: 1.7;
">

<h4>📘 指標怎麼看？（快速理解版）</h4>

<b>CAGR（年化報酬）</b>：一年平均賺多少，是長期投資最重要的指標。<br>
<b>總報酬率</b>：整段時間一共賺多少。<br>
<b>Sharpe Ratio</b>：承受一單位波動，能換到多少報酬。越高越穩定。<br>
<b>Sortino Ratio</b>：只看「跌」的波動，越高越抗跌。<br>
<b>最大回撤（MDD）</b>：最慘跌到多深。越小越好。<br>
<b>年化波動</b>：每天跳來跳去的程度。越低越舒服。<br>
<b>Calmar Ratio</b>：把報酬和回撤放一起看，越高代表越有效率。<br>





</div>
        """,
        unsafe_allow_html=True,
    )



