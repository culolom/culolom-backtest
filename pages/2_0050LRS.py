"""0050/006208 LRS 槓桿策略回測。"""
import os
import datetime as dt
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei", "PingFang TC", "Heiti TC"
    ]

matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="台股 LRS 回測系統", page_icon="📈", layout="wide")
st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 LRS 槓桿策略回測</h1>", unsafe_allow_html=True)

st.markdown(
    """
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold（0050 / 006208）<br>
2️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
3️⃣ 槓桿 ETF LRS（訊號來自原型 ETF 的 200 日 SMA，實際進出槓桿 ETF）<br>
""",
    unsafe_allow_html=True,
)

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

WINDOW = 200


@st.cache_data(show_spinner=False)
def fetch_history(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return df
    df = df.sort_index()
    df = df[~df.index.duplicated()]
    if "Adj Close" not in df.columns and "Close" in df.columns:
        df["Adj Close"] = df["Close"]
    return df


def adjust_for_splits(
    df: pd.DataFrame, price_col: str = "Adj Close", threshold: float = 0.3
) -> pd.DataFrame:
    df = df.copy()
    df["Price_raw"] = df[price_col]
    df["Price_adj"] = df["Price_raw"].copy()

    pct = df["Price_raw"].pct_change()
    jumps = pct[abs(pct) >= threshold].dropna()

    for date, r in jumps.items():
        ratio = 1 + r
        if ratio <= 0 or ratio >= 1:
            continue
        df.loc[df.index < date, "Price_adj"] *= ratio

    return df


@st.cache_data(show_spinner=False)
def load_price(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    df = fetch_history(symbol, start, end)
    if df.empty:
        return df
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    df = adjust_for_splits(df, price_col)
    return df


@st.cache_data(show_spinner=False)
def get_full_range(base_symbol: str, lev_symbol: str):
    b = yf.Ticker(base_symbol).history(period="max", auto_adjust=True)
    l = yf.Ticker(lev_symbol).history(period="max", auto_adjust=True)
    if b.empty or l.empty:
        return dt.date(2012, 1, 1), dt.date.today()
    b = b.sort_index()
    l = l.sort_index()
    start = max(b.index.min(), l.index.min()).date()
    end = min(b.index.max(), l.index.max()).date()
    return start, end


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
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)

if st.button("開始回測 🚀"):

    if start >= end:
        st.error("⚠️ 開始日期需早於結束日期")
        st.stop()

    start_early = start - dt.timedelta(days=365)

    with st.spinner("下載資料與處理拆股中…"):
        df_base_raw = load_price(base_symbol, start_early, end)
        df_lev_raw = load_price(lev_symbol, start_early, end)

    if df_base_raw.empty:
        st.error(f"⚠️ 無法取得 {base_symbol} 價格資料")
        st.stop()
    if df_lev_raw.empty:
        st.error(f"⚠️ 無法取得 {lev_symbol} 價格資料")
        st.stop()

    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price_adj"]
    df = df.join(df_lev_raw["Price_adj"].rename("Price_lev"), how="inner")
    df = df.sort_index()

    df = df[
        (df.index >= pd.to_datetime(start_early))
        & (df.index <= pd.to_datetime(end))
    ]

    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df = df.dropna(subset=["MA_200"]).copy()

    df = df.loc[pd.to_datetime(start) : pd.to_datetime(end)].copy()
    if df.empty:
        st.error("⚠️ 有效資料不足，請調整期間")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    df["Signal"] = 0
    df.iloc[0, df.columns.get_loc("Signal")] = 1

    for i in range(1, len(df)):
        p, m = df["Price_base"].iloc[i], df["MA_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i - 1], df["MA_200"].iloc[i - 1]

        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif p < m and p0 >= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = -1

    pos = []
    current = 1
    for sig in df["Signal"]:
        if sig == 1:
            current = 1
        elif sig == -1:
            current = 0
        pos.append(current)
    df["Position"] = pos

    equity_lrs = [1.0]
    for i in range(1, len(df)):
        if df["Position"].iloc[i] == 1:
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

    st.markdown(
        "<h3>📈 原型 ETF 價格 & 200SMA（含買賣點，hover 顯示槓桿買賣價）</h3>",
        unsafe_allow_html=True,
    )

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
            line=dict(color="#7f7f7f", width=2, dash="dot"),
        )
    )

    if not buys.empty:
        fig_price.add_trace(
            go.Scatter(
                x=buys.index,
                y=buys["Price_base"],
                mode="markers",
                name="買進 Buy",
                marker=dict(color="#2ca02c", symbol="triangle-up", size=14),
                customdata=buys["Price_lev"],
                hovertemplate=(
                    "📈 <b>買進訊號（來自原型 ETF）</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    + f"{base_label} 價格: "
                    + "%{y:.2f}<br>"
                    + f"{lev_label} 買進價: "
                    + "%{customdata:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )

    if not sells.empty:
        fig_price.add_trace(
            go.Scatter(
                x=sells.index,
                y=sells["Price_base"],
                mode="markers",
                name="賣出 Sell",
                marker=dict(color="#d62728", symbol="triangle-down", size=14),
                customdata=sells["Price_lev"],
                hovertemplate=(
                    "📉 <b>賣出訊號（來自原型 ETF）</b><br>"
                    "日期: %{x|%Y-%m-%d}<br>"
                    + f"{base_label} 價格: "
                    + "%{y:.2f}<br>"
                    + f"{lev_label} 賣出價: "
                    + "%{customdata:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )

    fig_price.update_layout(
        template="plotly_white",
        height=500,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h"),
        xaxis=dict(title="日期"),
        yaxis=dict(title="價格"),
    )

    st.plotly_chart(fig_price, use_container_width=True)

    st.markdown("<h3>📊 三種策略資金曲線（報酬率）</h3>", unsafe_allow_html=True)

    fig_equity = go.Figure()
    fig_equity.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Pct_Base"],
            mode="lines",
            name=f"{base_label} BH",
            line=dict(width=2),
        )
    )
    fig_equity.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Pct_Lev"],
            mode="lines",
            name=f"{lev_label} BH",
            line=dict(width=2, dash="dot"),
        )
    )
    fig_equity.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Pct_LRS"],
            mode="lines",
            name=f"{lev_label} LRS",
            line=dict(width=2, color="red"),
        )
    )

    fig_equity.update_layout(
        template="plotly_white",
        height=450,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h"),
        xaxis=dict(title="日期"),
        yaxis=dict(title="報酬率", tickformat=".0%"),
    )

    st.plotly_chart(fig_equity, use_container_width=True)

    def calc_metrics(eq: pd.Series, ret: pd.Series):
        final = eq.iloc[-1]
        total_ret = final - 1
        years = (eq.index[-1] - eq.index[0]).days / 365
        cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()

        daily = ret.dropna()
        if len(daily) <= 1:
            vol = sharpe = sortino = np.nan
        else:
            avg = daily.mean()
            std = daily.std()
            vol = std * np.sqrt(252)
            sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
            downside = daily[daily < 0].std()
            sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan

        return final, total_ret, cagr, mdd, vol, sharpe, sortino

    m_base = calc_metrics(df["Equity_BH_Base"], df["Return_base"])
    m_lev = calc_metrics(df["Equity_BH_Lev"], df["Return_lev"])
    m_lrs = calc_metrics(df["Equity_LRS"], df["Return_LRS"])

    st.markdown(
        """
    <style>
    .custom-table { width:100%; border-collapse:collapse; margin-top:1.2em; }
    .custom-table th {
        background:#f4f4f4; padding:10px; font-weight:700;
        border-bottom:2px solid #ddd;
    }
    .custom-table td {
        text-align:center; padding:8px;
        border-bottom:1px solid #eee; font-size:14px;
    }
    .custom-table tr:nth-child(even) td { background-color:#fafafa; }
    .custom-table tr:hover td { background-color:#f1f7ff; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    html_table = f"""
<table class="custom-table">
  <thead>
    <tr>
      <th>指標</th>
      <th>{base_label} BH</th>
      <th>{lev_label} BH</th>
      <th>{lev_label} LRS</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>總報酬</td>
      <td>{m_base[1]:.2%}</td>
      <td>{m_lev[1]:.2%}</td>
      <td>{m_lrs[1]:.2%}</td>
    </tr>
    <tr>
      <td>年化報酬 (CAGR)</td>
      <td>{m_base[2]:.2%}</td>
      <td>{m_lev[2]:.2%}</td>
      <td>{m_lrs[2]:.2%}</td>
    </tr>
    <tr>
      <td>最大回撤 (MDD)</td>
      <td>{m_base[3]:.2%}</td>
      <td>{m_lev[3]:.2%}</td>
      <td>{m_lrs[3]:.2%}</td>
    </tr>
    <tr>
      <td>年化波動率</td>
      <td>{m_base[4]:.2%}</td>
      <td>{m_lev[4]:.2%}</td>
      <td>{m_lrs[4]:.2%}</td>
    </tr>
    <tr>
      <td>Sharpe Ratio</td>
      <td>{m_base[5]:.2f}</td>
      <td>{m_lev[5]:.2f}</td>
      <td>{m_lrs[5]:.2f}</td>
    </tr>
    <tr>
      <td>Sortino Ratio</td>
      <td>{m_base[6]:.2f}</td>
      <td>{m_lev[6]:.2f}</td>
      <td>{m_lrs[6]:.2f}</td>
    </tr>
    <tr>
      <td>買進次數（LRS）</td>
      <td colspan="3">{len(buys)}</td>
    </tr>
    <tr>
      <td>賣出次數（LRS）</td>
      <td colspan="3">{len(sells)}</td>
    </tr>
  </tbody>
</table>
"""

    st.markdown(html_table, unsafe_allow_html=True)
    st.success("✅ 回測完成！已顯示三種策略的資金曲線與績效指標。")
