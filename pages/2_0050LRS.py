###############################################################
# app.py — CSV 版 0050LRS 回測（不使用 yfinance）
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
from heat_square import render_heat_square


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
    page_title="0050LRS 回測系統（CSV）",
    page_icon="📈",
    layout="wide",
)
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 槓桿策略回測（CSV 版）</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較三種策略（已改成 CSV 資料，不使用 yfinance）：</b><br>
1️⃣ 原型 ETF Buy & Hold（0050 / 006208）<br>
2️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
3️⃣ 槓桿 ETF LRS（訊號來自原型 ETF 的 200 日 SMA，實際進出槓桿 ETF）<br>
<small>（資料來自 GitHub Actions 自動更新的 CSV）</small>
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

DATA_DIR = Path("data")

###############################################################
# 讀取 CSV
###############################################################

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]


def get_full_range_from_csv(base_symbol: str, lev_symbol: str):
    df1 = load_csv(base_symbol)
    df2 = load_csv(lev_symbol)

    if df1.empty or df2.empty:
        return dt.date(2012, 1, 1), dt.date.today()

    start = max(df1.index.min().date(), df2.index.min().date())
    end = min(df1.index.max().date(), df2.index.max().date())
    return start, end

###############################################################
# 工具函式
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


def fmt_money(v):
    try: return f"{v:,.0f} 元"
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


def format_currency(v):
    try: return f"{v:,.0f} 元"
    except: return "—"


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
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input(
        "開始日期",
        value=max(s_min, s_max - dt.timedelta(days=5 * 365)),
        min_value=s_min, max_value=s_max,
    )

with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)

with col5:
    capital = st.number_input(
        "投入本金（元）", 1000, 5_000_000, 100_000, step=10_000,
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

    start_early = start - dt.timedelta(days=365)

    with st.spinner("讀取 CSV 中…"):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
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
        st.error("⚠️ 有效回測區間不足")
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

        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
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
    # ⬇⬇⬇ 以下內容完全保留（圖表 + KPI + 表格）
    ###############################################################

    # --- 原型 & MA ---
    st.markdown("<h3>📌 原型 ETF 價格 & 200SMA（訊號來源）</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label} 收盤價", mode="lines"))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200 日 SMA", mode="lines"))

    if not buys.empty:
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price_base"], mode="markers",
            name="買進 Buy", marker=dict(color="green", size=10)
        ))

    if not sells.empty:
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price_base"], mode="markers",
            name="賣出 Sell", marker=dict(color="red", size=10)
        ))

    fig_price.update_layout(template="plotly_white", height=420)
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # Tabs
    ###############################################################

    st.markdown("<h3>📊 三策略資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])

    # --- 資金曲線 ---
    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name="槓桿BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS"))

        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    # --- 回撤 ---
    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS", fill="tozeroy"))

        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    # --- 雷達 ---
    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]

        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill="toself", name="LRS"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill="toself", name="槓桿BH"))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base, theta=radar_categories, fill="toself", name="原型BH"))

        fig_radar.update_layout(template="plotly_white", height=480)
        st.plotly_chart(fig_radar, use_container_width=True)

    # --- 日報酬分佈 ---
    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)

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
        st.metric("期末資產（LRS）", format_currency(capital_lrs_final),
                  f"較槓桿BH {asset_gap_lrs_vs_lev:+.2f}%")
    with row1[1]:
        st.metric("CAGR（LRS）", format_percent(cagr_lrs),
                  f"較槓桿BH {cagr_gap_lrs_vs_lev:+.2f}%")
    with row1[2]:
        st.metric("年化波動（LRS）", format_percent(vol_lrs),
                  f"較槓桿BH {vol_gap_lrs_vs_lev:+.2f}%", delta_color="inverse")
    with row1[3]:
        st.metric("最大回撤（LRS）", format_percent(mdd_lrs),
                  f"較槓桿BH {mdd_gap_lrs_vs_lev:+.2f}%", delta_color="inverse")
    
    ###############################################################
    #  強化版：轉置表格 + highlight_best + heatmap（深色/亮色OK）
    ###############################################################
    
    import pandas as pd
    import numpy as np
    from matplotlib import cm
    
    # ===== 格式化工具 =====
    def fmt_money(x):
        return f"{x:,.0f} 元"
    
    def fmt_pct(x):
        return f"{x:.2%}"
    
    def fmt_num(x):
        return f"{x:.2f}"
    
    def fmt_int(x):
        return "—" if (pd.isna(x) or x == 0) else str(int(x))
    
    
    # ===== 建立 Raw table（不格式化） =====
    raw_table = pd.DataFrame([
        {
            "策略": f"{lev_label} LRS 槓桿策略",
            "期末資產": float(capital_lrs_final),
            "總報酬率": float(final_ret_lrs),
            "CAGR（年化）": float(cagr_lrs),
            "Calmar Ratio": float(calmar_lrs),
            "最大回撤（MDD）": float(mdd_lrs),
            "年化波動": float(vol_lrs),
            "Sharpe": float(sharpe_lrs),
            "Sortino": float(sortino_lrs),
            "交易次數": float(trade_count_lrs),
        },
        {
            "策略": f"{lev_label} BH（槓桿）",
            "期末資產": float(capital_lev_final),
            "總報酬率": float(final_ret_lev),
            "CAGR（年化）": float(cagr_lev),
            "Calmar Ratio": float(calmar_lev),
            "最大回撤（MDD）": float(mdd_lev),
            "年化波動": float(vol_lev),
            "Sharpe": float(sharpe_lev),
            "Sortino": float(sortino_lev),
            "交易次數": np.nan,
        },
        {
            "策略": f"{base_label} BH（原型）",
            "期末資產": float(capital_base_final),
            "總報酬率": float(final_ret_base),
            "CAGR（年化）": float(cagr_base),
            "Calmar Ratio": float(calmar_base),
            "最大回撤（MDD）": float(mdd_base),
            "年化波動": float(vol_base),
            "Sharpe": float(sharpe_base),
            "Sortino": float(sortino_base),
            "交易次數": np.nan,
        },
    ]).set_index("策略")
    
    
    # ===== 轉置 =====
    t_raw = raw_table.T           # 真正比較用
    t_fmt = t_raw.copy()          # 顯示用（格式化）
    
    
    # ===== 套格式 =====
    for col in t_fmt.columns:
        t_fmt.loc["期末資產", col] = fmt_money(t_raw.loc["期末資產", col])
        t_fmt.loc["總報酬率", col] = fmt_pct(t_raw.loc["總報酬率", col])
        t_fmt.loc["CAGR（年化）", col] = fmt_pct(t_raw.loc["CAGR（年化）", col])
        t_fmt.loc["Calmar Ratio", col] = fmt_num(t_raw.loc["Calmar Ratio", col])
        t_fmt.loc["最大回撤（MDD）", col] = fmt_pct(t_raw.loc["最大回撤（MDD）", col])
        t_fmt.loc["年化波動", col] = fmt_pct(t_raw.loc["年化波動", col])
        t_fmt.loc["Sharpe", col] = fmt_num(t_raw.loc["Sharpe", col])
        t_fmt.loc["Sortino", col] = fmt_num(t_raw.loc["Sortino", col])
        t_fmt.loc["交易次數", col] = fmt_int(t_raw.loc["交易次數", col])
    
    
    # ===== highlight best =====
    def highlight_best(row):
        s = t_raw.loc[row.name]
    
        # MDD、波動是愈小愈好
        if row.name in ["最大回撤（MDD）", "年化波動"]:
            best = s.astype(float).idxmin()
        else:
            best = s.astype(float).idxmax()
    
        return ["background-color: #d8f5d0" if c == best else "" for c in row.index]
    
    
    # ===== heatmap（每個 cell 自己算顏色） =====
    def make_heatmap():
        styles = pd.DataFrame("", index=t_raw.index, columns=t_raw.columns)
    
        for row_name in t_raw.index:
            vals = t_raw.loc[row_name].astype(float)
            vmin, vmax = vals.min(), vals.max()
            span = vmax - vmin if vmax > vmin else 1.0
    
            # Normalize
            norm = (vals - vmin) / span
    
            for col in t_raw.columns:
                x = float(norm[col])
                r, g, b, _ = cm.get_cmap("BuGn")(x)
                # rgba(,,,0.18) → 深色模式也 ok
                styles.loc[row_name, col] = f"background-color: rgba({int(r*255)}, {int(g*255)}, {int(b*255)}, 0.18)"
    
        return styles
    
    
    heatmap_styles = make_heatmap()
    
    
    # ===== 合併 Styler =====
    styled = t_fmt.style
    styled = styled.apply(highlight_best, axis=1)
    styled = styled.apply(lambda _: heatmap_styles, axis=None)
    
    styled = styled.set_properties(**{"text-align": "center"})
    
    styled = styled.set_table_styles([
        {"selector": "th.col_heading", "props": [("text-align", "center"), ("font-weight", "bold")]}
    ])
    
    
    st.markdown("### 📊 策略比較（升級版轉置表格）")
    st.write(styled.to_html(), unsafe_allow_html=True)



    ###############################################################
