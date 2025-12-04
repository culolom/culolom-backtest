###############################################################
# app.py — 0050LRS 回測系統 (Pro 深色模式完美支援版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import matplotlib.colors as mcolors
import plotly.graph_objects as go
from pathlib import Path

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
# Streamlit 頁面設定與全域 CSS 美化 (支援 Dark Mode)
###############################################################

st.set_page_config(
    page_title="0050LRS 回測系統 (Pro)",
    page_icon="📈",
    layout="wide",
)

# ⬇⬇⬇ CSS 美化區塊 (已修改為適應深色模式) ⬇⬇⬇
st.markdown(
    """
    <style>
        /* 1. 整體字體與間距優化 */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        h1, h2, h3 {
            font-weight: 700;
            color: var(--text-color); /* 自動適應文字顏色 */
        }
        
        /* 2. KPI 指標區塊卡片化 (適應 Dark Mode) */
        [data-testid="stMetric"] {
            background-color: var(--secondary-background-color); /* 自動切換淺灰/深灰 */
            border: 1px solid rgba(128, 128, 128, 0.2); /* 微弱邊框 */
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
        }
        [data-testid="stMetric"]:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-2px);
            border-color: rgba(128, 128, 128, 0.5);
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.9rem;
            color: var(--text-color);
            opacity: 0.7;
        }
        [data-testid="stMetricValue"] {
            font-weight: 700;
            color: var(--text-color);
        }

        /* 3. Tabs 樣式優化 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            border-radius: 8px;
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.1);
            font-weight: 500;
            color: var(--text-color);
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(41, 128, 185, 0.1) !important;
            color: #2980b9 !important;
            border: 1px solid #2980b9 !important;
        }

        /* 4. 表格容器樣式 */
        .table-container {
            border-radius: 12px; 
            overflow: hidden; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
            border: 1px solid rgba(128, 128, 128, 0.2);
            margin-top: 20px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)
# ⬆⬆⬆ CSS 結束 ⬆⬆⬆

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 槓桿策略回測 (Pro版)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <b>本工具比較三種策略：</b><br>
    <span style='color:#95a5a6'>●</span> 原型 ETF Buy & Hold (0050/006208)<br>
    <span style='color:#e67e22'>●</span> 槓桿 ETF Buy & Hold (正2系列)<br>
    <span style='color:#2980b9'>●</span> 槓桿 ETF LRS (200MA 趨勢策略)<br>
    <small style='color:var(--text-color); opacity:0.6;'>（資料來源：GitHub Actions 自動更新之 CSV）</small>
    """,
    unsafe_allow_html=True,
)

###############################################################
# 設定與資料讀取
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

# 專業配色定義
COLOR_BASE = "#95a5a6"  # 灰
COLOR_LEV = "#e67e22"   # 橘
COLOR_LRS = "#2980b9"   # 藍

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
# 計算指標函式
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

def fmt_pct(v):
    try: return f"{v:.2%}"
    except: return "—"

def fmt_num(v):
    try: return f"{v:.2f}"
    except: return "—"

def fmt_int(v):
    try: return f"{int(v):,}"
    except: return "—"

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

###############################################################
# UI 輸入
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF (訊號來源)", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF (交易標的)", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 資料庫區間：{s_min} ~ {s_max}")

col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金 (元)", 1000, 50_000_000, 100_000, step=10_000)

position_mode = st.radio("策略初始狀態", ["空手起跑 (標準)", "持有部位 (若在200MA上)"], index=0)

###############################################################
# 主程式運算
###############################################################

if st.button("🚀 開始回測", type="primary"):
    start_early = start - dt.timedelta(days=365)

    with st.spinner("正在分析歷史數據..."):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error("⚠️ 資料讀取失敗")
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

    # --- LRS 訊號 ---
    df["Signal"] = 0
    for i in range(1, len(df)):
        p, m = df["Price_base"].iloc[i], df["MA_200"].iloc[i]
        p0, m0 = df["Price_base"].iloc[i-1], df["MA_200"].iloc[i-1]
        if p > m and p0 <= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = 1
        elif p < m and p0 >= m0:
            df.iloc[i, df.columns.get_loc("Signal")] = -1

    # --- Position ---
    current_pos = 0 if "空手" in position_mode else 1
    df["Position"] = [
        current_pos := (1 if s == 1 else 0 if s == -1 else current_pos)
        for s in df["Signal"]
    ]

    # --- Equity ---
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

    # --- Metrics ---
    years_len = (df.index[-1] - df.index[0]).days / 365
    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = final_eq - 1
        cagr = (1 + final_ret)**(1/years_len) - 1 if years_len > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else np.nan
        return final_eq, final_ret, cagr, mdd, vol, sharpe, sortino, calmar

    eq_lrs, ret_lrs, cagr_lrs, mdd_lrs, vol_lrs, sharpe_lrs, sortino_lrs, calmar_lrs = calc_core(df["Equity_LRS"], df["Return_LRS"])
    eq_lev, ret_lev, cagr_lev, mdd_lev, vol_lev, sharpe_lev, sortino_lev, calmar_lev = calc_core(df["Equity_BH_Lev"], df["Return_lev"])
    eq_base, ret_base, cagr_base, mdd_base, vol_base, sharpe_base, sortino_base, calmar_base = calc_core(df["Equity_BH_Base"], df["Return_base"])

    capital_lrs = eq_lrs * capital
    capital_lev = eq_lev * capital
    capital_base = eq_base * capital
    trade_count = int((df["Signal"] != 0).sum())

    ###############################################################
    # 圖表呈現 (使用 Plotly White Template 但背景透明化)
    ###############################################################

    st.markdown("<h3>📈 價格走勢與交易訊號</h3>", unsafe_allow_html=True)
    
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label}", mode="lines", line=dict(color=COLOR_BASE, width=1)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200MA", mode="lines", line=dict(color="#f39c12", width=1.5)))
    
    if not buys.empty:
        fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="買進", marker=dict(color="green", size=10, symbol="triangle-up")))
    if not sells.empty:
        fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="賣出", marker=dict(color="red", size=10, symbol="triangle-down")))
    
    fig_price.update_layout(template="plotly_white", height=400, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_price, use_container_width=True)

    st.markdown("<h3>📊 策略績效深度分析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "最大回撤", "風險雷達", "分佈圖"])

    with tab_equity:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], name="原型 BH", line=dict(color=COLOR_BASE, width=1.5, dash='dot')))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], name="槓桿 BH", line=dict(color=COLOR_LEV, width=2)))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], name="LRS 策略", line=dict(color=COLOR_LRS, width=3), fill='tozeroy', fillcolor='rgba(41, 128, 185, 0.1)'))
        
        fig_eq.update_layout(template="plotly_white", height=450, hovermode="x unified", yaxis=dict(tickformat=".0%", title="累積報酬"), legend=dict(orientation="h", y=1.02, x=1, xanchor="right"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型 BH", line=dict(color=COLOR_BASE, width=1)))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿 BH", line=dict(color=COLOR_LEV, width=1)))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS 策略", line=dict(color=COLOR_LRS, width=1), fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=400, yaxis=dict(title="回撤幅度 %"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        cats = ["CAGR", "Sharpe", "Sortino", "-MDD", "Inv-Vol"]
        v_lrs = [nz(cagr_lrs), nz(sharpe_lrs), nz(sortino_lrs), nz(-mdd_lrs), nz(-vol_lrs)]
        v_lev = [nz(cagr_lev), nz(sharpe_lev), nz(sortino_lev), nz(-mdd_lev), nz(-vol_lev)]
        v_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]
        
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(r=v_lrs, theta=cats, fill='toself', name='LRS', line_color=COLOR_LRS))
        fig_r.add_trace(go.Scatterpolar(r=v_lev, theta=cats, fill='toself', name='槓桿 BH', line_color=COLOR_LEV))
        fig_r.add_trace(go.Scatterpolar(r=v_base, theta=cats, fill='toself', name='原型 BH', line_color=COLOR_BASE))
        fig_r.update_layout(template="plotly_white", height=400, polar=dict(radialaxis=dict(visible=True)), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_r, use_container_width=True)

    with tab_hist:
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(x=df["Return_base"]*100, name="原型 BH", marker_color=COLOR_BASE, opacity=0.6))
        fig_h.add_trace(go.Histogram(x=df["Return_lev"]*100, name="槓桿 BH", marker_color=COLOR_LEV, opacity=0.6))
        fig_h.add_trace(go.Histogram(x=df["Return_LRS"]*100, name="LRS", marker_color=COLOR_LRS, opacity=0.7))
        fig_h.update_layout(barmode='overlay', template="plotly_white", height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_h, use_container_width=True)

    ###############################################################
    # KPI 與 直式表格 (Dark Mode 修復)
    ###############################################################
    
    # KPI Summary
    diff_asset = ((capital_lrs / capital_lev) - 1) * 100
    diff_cagr = (cagr_lrs - cagr_lev) * 100
    diff_mdd = (mdd_lrs - mdd_lev) * 100
    
    r1 = st.columns(4)
    r1[0].metric("期末資產 (LRS)", fmt_money(capital_lrs), f"{diff_asset:+.2f}% vs 槓桿BH")
    r1[1].metric("CAGR 年化", fmt_pct(cagr_lrs), f"{diff_cagr:+.2f}%")
    r1[2].metric("最大回撤 (MDD)", fmt_pct(mdd_lrs), f"{diff_mdd:+.2f}%", delta_color="inverse")
    r1[3].metric("Sharpe Ratio", fmt_num(sharpe_lrs))

    st.markdown("<br>", unsafe_allow_html=True)

    # 1. 建立原始數據表
    raw_table = pd.DataFrame([
        {
            "策略": f"{lev_label} LRS",
            "期末資產": capital_lrs,
            "總報酬率": ret_lrs,
            "CAGR (年化)": cagr_lrs,
            "夏普值 (Sharpe)": sharpe_lrs,
            "索提諾 (Sortino)": sortino_lrs,
            "風報比 (Calmar)": calmar_lrs,
            "最大回撤 (MDD)": mdd_lrs,
            "年化波動率": vol_lrs,
            "交易次數": trade_count,
        },
        {
            "策略": f"{lev_label} BH",
            "期末資產": capital_lev,
            "總報酬率": ret_lev,
            "CAGR (年化)": cagr_lev,
            "夏普值 (Sharpe)": sharpe_lev,
            "索提諾 (Sortino)": sortino_lev,
            "風報比 (Calmar)": calmar_lev,
            "最大回撤 (MDD)": mdd_lev,
            "年化波動率": vol_lev,
            "交易次數": np.nan,
        },
        {
            "策略": f"{base_label} BH",
            "期末資產": capital_base,
            "總報酬率": ret_base,
            "CAGR (年化)": cagr_base,
            "夏普值 (Sharpe)": sharpe_base,
            "索提諾 (Sortino)": sortino_base,
            "風報比 (Calmar)": calmar_base,
            "最大回撤 (MDD)": mdd_base,
            "年化波動率": vol_base,
            "交易次數": np.nan,
        },
    ])

    # 2. 轉置表格 (Transpose)
    df_vertical = raw_table.set_index("策略").T

    # 3. 準備顯示用的表格 (Formatted)
    df_display = df_vertical.copy()
    format_map = {
        "期末資產": fmt_money, "總報酬率": fmt_pct, "CAGR (年化)": fmt_pct,
        "夏普值 (Sharpe)": fmt_num, "索提諾 (Sortino)": fmt_num, "風報比 (Calmar)": fmt_num,
        "最大回撤 (MDD)": fmt_pct, "年化波動率": fmt_pct, "交易次數": fmt_int,
    }
    for idx_name, func in format_map.items():
        if idx_name in df_display.index:
            df_display.loc[idx_name] = df_display.loc[idx_name].apply(func)

    # 4. 定義樣式與柔和熱力圖 (移除強制文字顏色)
    custom_cmap = mcolors.LinearSegmentedColormap.from_list("soft_ryg", ["#e74c3c", "#f1c40f", "#2ecc71"])

    def get_color_soft(val, vmin, vmax, invert=False):
        if pd.isna(val): return ""
        if vmax - vmin < 1e-9: norm = 0.5
        else: norm = (val - vmin) / (vmax - vmin)
        if invert: norm = 1 - norm
        rgba = custom_cmap(norm)
        # 不再強制 color: #2c3e50，讓 CSS 變數決定黑/白字
        return f"background-color: rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, 0.25); font-weight: 600;"

    styled = df_display.style
    # 基礎 CSS (使用變數適應深淺色)
    styled = styled.set_table_attributes('class="table-finance"')
    styled = styled.set_properties(**{
        "text-align": "center", "padding": "12px 10px", "border-bottom": "1px solid rgba(128, 128, 128, 0.2)",
        "font-family": "Helvetica Neue, Arial, sans-serif", "font-size": "15px",
    })
    # 表頭與第一欄樣式
    styled = styled.set_table_styles([
        {"selector": "th", "props": [
            ("text-align", "center"), 
            ("background-color", "var(--secondary-background-color)"), # 自動變換背景
            ("color", "var(--text-color)"), # 自動變換文字
            ("font-weight", "700"), ("font-size", "15px"), ("padding", "12px")
        ]},
        {"selector": "th.index_name", "props": [
            ("background-color", "var(--background-color)"), # 主背景色
            ("color", "var(--text-color)"), 
            ("text-align", "right"), 
            ("border-right", "2px solid rgba(128, 128, 128, 0.2)")
        ]},
        {"selector": "tbody tr:hover", "props": [("background-color", "rgba(128, 128, 128, 0.1)")]},
    ])

    # 5. 應用熱力圖
    invert_metrics = ["最大回撤 (MDD)", "年化波動率"]
    for idx, row in df_vertical.iterrows():
        vals = row.astype(float).values
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        invert = idx in invert_metrics
        styles = [get_color_soft(v, vmin, vmax, invert) for v in vals]
        styled = styled.apply(lambda x, s=styles: s, axis=1, subset=pd.IndexSlice[idx, :])

    # 6. 輸出
    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.write(styled.to_html(), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
