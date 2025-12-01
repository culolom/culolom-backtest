###############################################################
# 0050LRS 回測（0050 / 006208 + 正2 槓桿 ETF）
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go

from hamster_data.loader import load_price, list_symbols

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
<small>（資料來源 data/ 資料夾中的 CSV）</small>
""",
    unsafe_allow_html=True,
)

###############################################################
# 固定 ETF 選單（去除 .TW 顯示）
###############################################################

BASE_DISPLAY = ["0050", "006208"]
LEV_DISPLAY = ["00631L", "00663L", "00675L", "00685L"]

def display_to_symbol(code: str) -> str:
    """顯示 0050 → 讀檔 0050.TW"""
    return f"{code}.TW"

def symbol_to_display(symbol: str) -> str:
    """0050.TW → 顯示 0050"""
    return symbol.replace(".TW", "")

# 確保 CSV 存在
symbols = list_symbols()
existing_display = [symbol_to_display(s) for s in symbols]

base_choices = [c for c in BASE_DISPLAY if c in existing_display]
lev_choices = [c for c in LEV_DISPLAY if c in existing_display]

if not base_choices:
    st.error("⚠️ 找不到原型 ETF（0050 / 006208）的資料檔！")
    st.stop()

if not lev_choices:
    st.error("⚠️ 找不到槓桿 ETF（00631L / 00663L / 00675L / 00685L）的資料檔！")
    st.stop()

###############################################################
# 介面：ETF 選擇與日期範圍（簡化後版本）
###############################################################

symbols = list_symbols()
existing_display = [s.replace(".TW", "") for s in symbols]

# 固定可選清單
BASE_DISPLAY = ["0050", "006208"]
LEV_DISPLAY = ["00631L", "00663L", "00675L", "00685L"]

base_choices = [c for c in BASE_DISPLAY if c in existing_display]
lev_choices = [c for c in LEV_DISPLAY if c in existing_display]

if not base_choices:
    st.error("⚠️ 找不到原型 ETF（0050 / 006208）的資料！")
    st.stop()

if not lev_choices:
    st.error("⚠️ 找不到槓桿 ETF（00631L / 00663L / 00675L / 00685L）的資料！")
    st.stop()


def to_symbol(x):   # 用來讀檔
    return f"{x}.TW"


# -------------------------
# 減少 UI：只保留原型 + 槓桿
# -------------------------
col1, col2 = st.columns(2)

with col1:
    base_display = st.selectbox("原型 ETF（訊號來源）", base_choices)
    base_symbol = to_symbol(base_display)

with col2:
    lev_display = st.selectbox("槓桿 ETF（實際進出場標的）", lev_choices)
    lev_symbol = to_symbol(lev_display)

st.markdown(f"### 使用原型：{base_display}　槓桿：{lev_display}")


###############################################################
# 載入資料
###############################################################

def select_price_column(df: pd.DataFrame) -> pd.Series:
    for col in ["Adj Close", "Close", "Price"]:
        if col in df.columns:
            return df[col]
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        return df[numeric_cols[0]]
    raise ValueError("缺少價格欄位（需包含 Adj Close/Close/Price）")


def load_price_series(symbol: str) -> pd.DataFrame:
    try:
        df = load_price(symbol)
    except Exception:
        st.error(f"⚠️ 找不到資料：data/{symbol}.csv")
        st.stop()

    price_series = select_price_column(df)

    out = pd.DataFrame({"Price": price_series})
    out = out.sort_index()
    return out


df_base_full = load_price_series(base_symbol)
df_lev_full = load_price_series(lev_symbol)

combined = pd.DataFrame(index=df_base_full.index)
combined["Price_base"] = df_base_full["Price"]
combined = combined.join(df_lev_full["Price"].rename("Price_lev"), how="inner")
combined = combined[~combined.index.duplicated(keep="first")]
combined = combined.sort_index()

if combined.empty:
    st.error("⚠️ 兩檔 ETF 無重疊日期，無法回測")
    st.stop()

###############################################################
# 日期區間
###############################################################

available_start = combined.index.min().date()
available_end = combined.index.max().date()
st.info(f"📌 可回測區間：{available_start} ~ {available_end}")

col3, col4, col5 = st.columns(3)
with col3:
    default_start = max(available_start, available_end - dt.timedelta(days=5 * 365))
    start = st.date_input("開始日期", value=default_start,
                          min_value=available_start, max_value=available_end)

with col4:
    end = st.date_input("結束日期", value=available_end,
                        min_value=available_start, max_value=available_end)

with col5:
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)

position_mode = st.radio(
    "策略初始狀態",
    ["空手起跑（標準 LRS）", "一開始就全倉槓桿 ETF"],
)

###############################################################
# 主回測程式（按下按鈕才執行）
###############################################################

if st.button("開始回測 🚀"):

    if start >= end:
        st.error("⚠️ 開始日期需早於結束日期")
        st.stop()

    WINDOW = 200
    start_early = start - dt.timedelta(days=365)

    df = combined.copy()
    df = df[(df.index >= pd.to_datetime(start_early)) & (df.index <= pd.to_datetime(end))]

    if len(df) < WINDOW:
        st.error(f"⚠️ 資料不足，無法計算 {WINDOW} 日 SMA")
        st.stop()

    # 計算 SMA
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df = df.dropna(subset=["MA_200"])
    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)].copy()

    if df.empty:
        st.error("⚠️ 無有效回測區間")
        st.stop()

    # 報酬
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # 訊號
    df["Signal"] = 0
    for i in range(1, len(df)):
        p, m = df["Price_base"].iloc[i], df["MA_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]
        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif p < m and p0 >= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = -1

    # 持倉
    if "空手" in position_mode:
        current_pos = 1 if df["Price_base"].iloc[0] > df["MA_200"].iloc[0] else 0
    else:
        current_pos = 1

    positions = [current_pos]
    for s in df["Signal"].iloc[1:]:
        if s == 1:
            current_pos = 1
        elif s == -1:
            current_pos = 0
        positions.append(current_pos)

    df["Position"] = positions

    # 資金曲線
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        if df["Position"].iloc[i] == 1 and df["Position"].iloc[i-1] == 1:
            r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]
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
    # 指標
    ###############################################################

    def calc_metrics(series):
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

    years_len = (df.index[-1] - df.index[0]).days / 365

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = final_eq - 1
        cagr = (1 + final_ret)**(1 / years_len) - 1 if years_len > 0 else np.nan
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
    # 價格圖
    ###############################################################

    st.markdown("<h3>📌 原型 ETF 價格 & 200SMA（訊號來源）</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price_base"],
        name=f"{base_display} 收盤價",
        mode="lines", line=dict(color="#1f77b4", width=2),
    ))

    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_200"],
        name="200 日 SMA",
        mode="lines", line=dict(color="#7f7f7f", width=2),
    ))

    if not buys.empty:
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price_base"],
            mode="markers", name="買進 Buy",
            marker=dict(symbol="circle-open", size=12, line=dict(width=2, color="#2ca02c")),
        ))

    if not sells.empty:
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price_base"],
            mode="markers", name="賣出 Sell",
            marker=dict(symbol="circle-open", size=12, line=dict(width=2, color="#d62728")),
        ))

    fig_price.update_layout(template="plotly_white", height=480)
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # Tabs：資金曲線 / 回撤 / 雷達圖 / 日報酬
    ###############################################################

    st.markdown("<h3>📊 三策略資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])

    with tab_equity:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], name=f"{base_display} BH"))
        fig.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], name=f"{lev_display} BH"))
        fig.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], name=f"{lev_display} LRS"))
        fig.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig, use_container_width=True)

    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df.index, y=dd_base, name=f"{base_display} BH"))
        fig2.add_trace(go.Scatter(x=df.index, y=dd_lev, name=f"{lev_display} BH"))
        fig2.add_trace(go.Scatter(x=df.index, y=dd_lrs, name=f"{lev_display} LRS", fill="tozeroy"))
        fig2.update_layout(template="plotly_white", height=450)
        st.plotly_chart(fig2, use_container_width=True)

    with tab_radar:
        def nz(x): return float(np.nan_to_num(x))
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        fig3 = go.Figure()
        fig3.add_trace(go.Scatterpolar(
            r=[nz(cagr_lrs), nz(sharpe_lrs), nz(sortino_lrs), nz(-mdd_lrs), nz(-vol_lrs)],
            theta=radar_categories, fill="toself", name="LRS"
        ))
        fig3.add_trace(go.Scatterpolar(
            r=[nz(cagr_lev), nz(sharpe_lev), nz(sortino_lev), nz(-mdd_lev), nz(-vol_lev)],
            theta=radar_categories, fill="toself", name="槓桿BH"
        ))
        fig3.add_trace(go.Scatterpolar(
            r=[nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)],
            theta=radar_categories, fill="toself", name="原型BH"
        ))
        fig3.update_layout(template="plotly_white", height=480)
        st.plotly_chart(fig3, use_container_width=True)

    with tab_hist:
        fig4 = go.Figure()
        fig4.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.6))
        fig4.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.6))
        fig4.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS", opacity=0.7))
        fig4.update_layout(barmode="overlay", template="plotly_white", height=480)
        st.plotly_chart(fig4, use_container_width=True)

    ###############################################################
    # 文字表格
    ###############################################################

    def fmt_money(v): return f"{v:,.0f} 元"
    def fmt_pct(v): return f"{v:.2%}"
    def fmt_num(v): return f"{v:.2f}" if not np.isnan(v) else "—"

    metrics_table = pd.DataFrame([
        {
            "策略": f"{lev_display} LRS",
            "期末資產": capital_lrs_final,
            "總報酬率": final_ret_lrs,
            "CAGR": cagr_lrs,
            "Calmar": calmar_lrs,
            "MDD": mdd_lrs,
            "波動": vol_lrs,
            "Sharpe": sharpe_lrs,
            "Sortino": sortino_lrs,
            "交易次數": trade_count_lrs,
        },
        {
            "策略": f"{lev_display} BH",
            "期末資產": capital_lev_final,
            "總報酬率": final_ret_lev,
            "CAGR": cagr_lev,
            "Calmar": calmar_lev,
            "MDD": mdd_lev,
            "波動": vol_lev,
            "Sharpe": sharpe_lev,
            "Sortino": sortino_lev,
            "交易次數": "—",
        },
        {
            "策略": f"{base_display} BH",
            "期末資產": capital_base_final,
            "總報酬率": final_ret_base,
            "CAGR": cagr_base,
            "Calmar": calmar_base,
            "MDD": mdd_base,
            "波動": vol_base,
            "Sharpe": sharpe_base,
            "Sortino": sortino_base,
            "交易次數": "—",
        }
    ])

    fmt = metrics_table.copy()
    fmt["期末資產"] = fmt["期末資產"].apply(fmt_money)
    fmt["總報酬率"] = fmt["總報酬率"].apply(fmt_pct)
    fmt["CAGR"] = fmt["CAGR"].apply(fmt_pct)
    fmt["Calmar"] = fmt["Calmar"].apply(fmt_num)
    fmt["MDD"] = fmt["MDD"].apply(fmt_pct)
    fmt["波動"] = fmt["波動"].apply(fmt_pct)
    fmt["Sharpe"] = fmt["Sharpe"].apply(fmt_num)
    fmt["Sortino"] = fmt["Sortino"].apply(fmt_num)

    st.dataframe(fmt, use_container_width=True)

    ###############################################################
    # Footer
    ###############################################################

    st.markdown(
        """
        <div style="margin-top:20px;padding:15px;background:#f7f7f7;border-left:4px solid #4a90e2;">
        <b>CAGR</b>：年化報酬。<br>
        <b>MDD</b>：最大回撤。越小越好。<br>
        <b>Sharpe</b>：每單位波動的報酬。<br>
        <b>Sortino</b>：針對下跌風險的報酬。<br>
        <b>Calmar</b>：報酬 ÷ 回撤，衡量效率。<br>
        </div>
        """,
        unsafe_allow_html=True,
    )
