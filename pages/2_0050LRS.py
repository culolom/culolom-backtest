###############################################################
# app.py — 0050LRS 回測系統 (Sidebar + Dark Mode 完美整合版)
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
# 字型設定 (支援中文字型)
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    # Mac/Windows 通用 fallback
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei",
        "PingFang TC",
        "Heiti TC",
        "Arial Unicode MS",
        "sans-serif"
    ]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# 1. Streamlit 頁面與全域 CSS 設定
###############################################################

st.set_page_config(
    page_title="0050LRS 智能回測",
    page_icon="📈",
    layout="wide",
)

# 使用 CSS 變數 (var) 來自動適應深色/淺色模式
st.markdown(
    """
    <style>
        /* A. 全域字體與間距優化 */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        h1, h2, h3 {
            font-weight: 700 !important;
            color: var(--text-color) !important;
        }

        /* B. KPI 指標卡片 (Metric Cards) - 自動適應黑/白底 */
        [data-testid="stMetric"] {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.2);
            padding: 15px 20px;
            border-radius: 12px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-color: rgba(128, 128, 128, 0.4);
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

        /* C. Tabs 分頁籤樣式 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            margin-bottom: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
            height: 42px;
            border-radius: 8px;
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.1);
            font-weight: 500;
            color: var(--text-color);
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(41, 128, 185, 0.15) !important;
            color: #3498db !important;
            border: 1px solid #3498db !important;
        }

        /* D. 表格容器 */
        .table-container {
            border-radius: 12px; 
            overflow: hidden; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.05); 
            border: 1px solid rgba(128, 128, 128, 0.2);
            margin-top: 10px;
        }
        
        /* 修正表格內的字體顏色適應 */
        th, td {
            color: var(--text-color) !important;
        }
        
        /* 側邊欄美化 */
        section[data-testid="stSidebar"] {
            background-color: var(--secondary-background-color);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# 標題區
st.markdown("<h1 style='margin-bottom:0.2em;'>📊 0050LRS 槓桿策略回測系統</h1>", unsafe_allow_html=True)
st.markdown(
    """
    <div style='background-color: rgba(128,128,128,0.1); padding: 10px 15px; border-radius: 8px; margin-bottom: 20px;'>
        <small style='color: var(--text-color); opacity: 0.8;'>
        <b>策略比較：</b>
        <span style='color:#bdc3c7'>●</span> 原型 Buy&Hold &nbsp;&nbsp;
        <span style='color:#e67e22'>●</span> 槓桿 Buy&Hold &nbsp;&nbsp;
        <span style='color:#3498db'>●</span> <b>LRS 趨勢策略 (200MA)</b>
        </small>
    </div>
    """, 
    unsafe_allow_html=True
)

###############################################################
# 2. 資料讀取與常數設定
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

WINDOW = 200  
DATA_DIR = Path("data")

# 專業配色 (適用深/淺色模式)
COLOR_BASE = "#bdc3c7"  # 淺灰 (在黑底白底都安全)
COLOR_LEV = "#e67e22"   # 亮橘
COLOR_LRS = "#3498db"   # 亮藍

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
# 3. 計算工具函式
###############################################################

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std = daily.mean(), daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def fmt_money(v): return f"{v:,.0f} 元" if pd.notnull(v) else "—"
def fmt_pct(v): return f"{v:.2%}" if pd.notnull(v) else "—"
def fmt_num(v): return f"{v:.2f}" if pd.notnull(v) else "—"
def fmt_int(v): return f"{int(v):,}" if pd.notnull(v) else "—"
def nz(x): return float(np.nan_to_num(x, nan=0.0))

###############################################################
# 4. UI 輸入區 (側邊欄 Sidebar)
###############################################################

with st.sidebar:
    st.header("⚙️ 參數設定")
    
    # 1. ETF 選擇
    st.subheader("1. 標的選擇")
    base_label = st.selectbox("原型 ETF (訊號來源)", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
    
    lev_label = st.selectbox("槓桿 ETF (交易標的)", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]
    
    # 取得資料範圍
    s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
    
    st.markdown("---")

    # 2. 回測參數
    st.subheader("2. 回測參數")
    
    # 日期選擇
    start = st.date_input(
        "開始日期", 
        value=max(s_min, s_max - dt.timedelta(days=5*365)), 
        min_value=s_min, 
        max_value=s_max
    )
    end = st.date_input(
        "結束日期", 
        value=s_max, 
        min_value=s_min, 
        max_value=s_max
    )
    
    # 資金與模式
    capital = st.number_input("投入本金", 1000, 50_000_000, 100_000, step=10_000)
    position_mode = st.radio(
        "策略初始狀態", 
        ["空手起跑 (標準)", "若在均線上則持有"], 
        index=0
    )
    
    st.markdown("---")
    
    # 3. 執行按鈕 (使用 Session State 防止切換 Tab 時重置)
    if st.button("🚀 開始分析", type="primary", use_container_width=True):
        st.session_state.run_analysis = True
    
###############################################################
# 5. 主程式運算
###############################################################

# 初始化 session state
if 'run_analysis' not in st.session_state:
    st.session_state.run_analysis = False

if st.session_state.run_analysis:
    start_early = start - dt.timedelta(days=365)
    
    with st.spinner("正在讀取數據並模擬交易..."):
        df_base_raw = load_csv(base_symbol)
        df_lev_raw = load_csv(lev_symbol)

    if df_base_raw.empty or df_lev_raw.empty:
        st.error(f"⚠️ 找不到資料，請確認 data 資料夾是否有 {base_symbol}.csv 與 {lev_symbol}.csv")
        st.stop()

    # 數據合併與前處理
    df_base_raw = df_base_raw.loc[start_early:end]
    df_lev_raw = df_lev_raw.loc[start_early:end]
    df = pd.DataFrame(index=df_base_raw.index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()

    # 指標計算
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    df = df.dropna(subset=["MA_200"]).loc[start:end]
    
    if df.empty:
        st.error("⚠️ 選定區間內無足夠數據 (MA200 需要前置資料)")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # 訊號生成
    signals = np.zeros(len(df))
    price = df["Price_base"].values
    ma = df["MA_200"].values
    
    # 向量化邏輯太複雜，維持迴圈確保正確性
    for i in range(1, len(df)):
        if price[i] > ma[i] and price[i-1] <= ma[i-1]:
            signals[i] = 1
        elif price[i] < ma[i] and price[i-1] >= ma[i-1]:
            signals[i] = -1
    df["Signal"] = signals

    # 部位計算
    pos = 0 if "空手" in position_mode else 1
    pos_arr = []
    for s in df["Signal"]:
        if s == 1: pos = 1
        elif s == -1: pos = 0
        pos_arr.append(pos)
    df["Position"] = pos_arr

    # 資金曲線
    eq = [1.0]
    lev_price = df["Price_lev"].values
    pos_vals = df["Position"].values
    
    for i in range(1, len(df)):
        if pos_vals[i] == 1 and pos_vals[i-1] == 1:
            r = lev_price[i] / lev_price[i-1]
            eq.append(eq[-1] * r)
        else:
            eq.append(eq[-1])
            
    df["Equity_LRS"] = eq
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    
    # 基準與槓桿持有
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    # 換算百分比 (繪圖用)
    df["Pct_Base"] = df["Equity_BH_Base"] - 1
    df["Pct_Lev"] = df["Equity_BH_Lev"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]

    # 績效統計
    years = (df.index[-1] - df.index[0]).days / 365.25
    def get_stats(equity_col, ret_col):
        eq_series = df[equity_col]
        final_eq = eq_series.iloc[-1]
        cagr = (final_eq**(1/years) - 1) if years > 0 else 0
        mdd = 1 - (eq_series / eq_series.cummax()).min()
        vol, sharpe, sortino = calc_metrics(df[ret_col])
        calmar = cagr / mdd if mdd > 0 else np.nan
        return final_eq * capital, final_eq - 1, cagr, mdd, vol, sharpe, sortino, calmar

    stats_lrs = get_stats("Equity_LRS", "Return_LRS")
    stats_lev = get_stats("Equity_BH_Lev", "Return_lev")
    stats_base = get_stats("Equity_BH_Base", "Return_base")
    
    trade_count = int((df["Signal"] != 0).sum())

    ###############################################################
    # 6. 圖表繪製 (Plotly 美化版)
    ###############################################################
    
    # 通用 X 軸設定 (時間按鈕)
    xaxis_config = dict(
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1月", step="month", stepmode="backward"),
                dict(count=6, label="6月", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1年", step="year", stepmode="backward"),
                dict(step="all", label="全部")
            ]),
            bgcolor="var(--secondary-background-color)",
            activecolor="#3498db",
            font=dict(color="var(--text-color)")
        ),
        type="date",
        gridcolor="rgba(128, 128, 128, 0.1)"
    )
    
    yaxis_config = dict(
        gridcolor="rgba(128, 128, 128, 0.1)",
        zerolinecolor="rgba(128, 128, 128, 0.3)"
    )

    # 圖 1: 價格與訊號
    st.markdown("<h3>📈 價格趨勢與交易訊號</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=base_label, mode="lines", line=dict(color=COLOR_BASE, width=1.5)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200MA (生命線)", mode="lines", line=dict(color="#f1c40f", width=1.5)))
    
    if not buys.empty:
        fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="買進訊號", 
                                     marker=dict(color="#2ecc71", size=12, symbol="triangle-up", line=dict(color="white", width=1))))
    if not sells.empty:
        fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="賣出訊號", 
                                     marker=dict(color="#e74c3c", size=12, symbol="triangle-down", line=dict(color="white", width=1))))
    
    fig_price.update_layout(
        template="plotly_white", height=450, 
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=xaxis_config, yaxis=yaxis_config,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center")
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # 圖 2: 績效分析 (Tabs)
    st.markdown("<h3>📊 策略績效深度分析</h3>", unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["💰 資金曲線", "📉 歷史回撤", "🕸️ 風險雷達", "📊 報酬分佈"])

    with tab1:
        fig_eq = go.Figure()
        # 原型 (虛線、弱化)
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], name="原型 BH", 
                                  line=dict(color=COLOR_BASE, width=1.5, dash='dash'), opacity=0.7))
        # 槓桿 (實線)
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], name="槓桿 BH", 
                                  line=dict(color=COLOR_LEV, width=2)))
        # LRS (實線 + 填充 + 醒目)
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], name="LRS 策略 (主角)", 
                                  line=dict(color=COLOR_LRS, width=3),
                                  fill='tozeroy', fillcolor='rgba(52, 152, 219, 0.15)')) # 半透明藍色填充
        
        fig_eq.update_layout(
            template="plotly_white", height=480, 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=xaxis_config, 
            yaxis=dict(title="累積報酬率", tickformat=".0%", **yaxis_config),
            hovermode="x unified",
            legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab2:
        fig_dd = go.Figure()
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1)
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1)
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1)
        
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型 BH", line=dict(color=COLOR_BASE, width=1), fill=None))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿 BH", line=dict(color=COLOR_LEV, width=1.5), fill=None))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS 策略", line=dict(color=COLOR_LRS, width=2), fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.1)'))
        
        fig_dd.update_layout(
            template="plotly_white", height=450,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=xaxis_config,
            yaxis=dict(title="回撤幅度", tickformat=".1%", **yaxis_config),
            hovermode="x unified"
        )
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab3:
        cats = ["年化報酬 (CAGR)", "夏普值 (Sharpe)", "索提諾 (Sortino)", "抗回撤能力 (Inv-MDD)", "穩定度 (Inv-Vol)"]
        v_lrs = [nz(stats_lrs[2]), nz(stats_lrs[5]), nz(stats_lrs[6]), nz(-stats_lrs[3]), nz(-stats_lrs[4])]
        v_lev = [nz(stats_lev[2]), nz(stats_lev[5]), nz(stats_lev[6]), nz(-stats_lev[3]), nz(-stats_lev[4])]
        v_base = [nz(stats_base[2]), nz(stats_base[5]), nz(stats_base[6]), nz(-stats_base[3]), nz(-stats_base[4])]
        
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(r=v_lrs, theta=cats, fill='toself', name='LRS', line_color=COLOR_LRS))
        fig_r.add_trace(go.Scatterpolar(r=v_lev, theta=cats, fill='toself', name='槓桿 BH', line_color=COLOR_LEV))
        fig_r.add_trace(go.Scatterpolar(r=v_base, theta=cats, fill='toself', name='原型 BH', line_color=COLOR_BASE))
        
        fig_r.update_layout(
            template="plotly_white", height=450,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            polar=dict(radialaxis=dict(visible=True, gridcolor="rgba(128,128,128,0.2)"), bgcolor='rgba(0,0,0,0)')
        )
        st.plotly_chart(fig_r, use_container_width=True)

    with tab4:
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(x=df["Return_base"]*100, name="原型 BH", marker_color=COLOR_BASE, opacity=0.6))
        fig_h.add_trace(go.Histogram(x=df["Return_lev"]*100, name="槓桿 BH", marker_color=COLOR_LEV, opacity=0.6))
        fig_h.add_trace(go.Histogram(x=df["Return_LRS"]*100, name="LRS", marker_color=COLOR_LRS, opacity=0.8))
        fig_h.update_layout(
            barmode='overlay', template="plotly_white", height=450,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(title="日報酬率 (%)", **yaxis_config),
            yaxis=yaxis_config
        )
        st.plotly_chart(fig_h, use_container_width=True)

    ###############################################################
    # 7. KPI 與 直式表格 (Dark Mode 修復版)
    ###############################################################
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # KPI 差異計算
    diff_asset = ((stats_lrs[0] / stats_lev[0]) - 1)
    diff_cagr = (stats_lrs[2] - stats_lev[2])
    diff_mdd = (stats_lrs[3] - stats_lev[3])
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    col_kpi1.metric("期末總資產 (LRS)", fmt_money(stats_lrs[0]), f"{diff_asset:+.2%} vs 槓桿BH")
    col_kpi2.metric("年化報酬率 CAGR", fmt_pct(stats_lrs[2]), f"{diff_cagr:+.2%}")
    # MDD 越小越好，所以 LRS < LEV 是好事 (顯示綠色)，Streamlit delta 預設正=綠，這裡用 inverse
    col_kpi3.metric("最大回撤 MDD", fmt_pct(stats_lrs[3]), f"{diff_mdd:+.2%}", delta_color="inverse") 
    col_kpi4.metric("夏普值 Sharpe", fmt_num(stats_lrs[5]))

    st.markdown("<br>", unsafe_allow_html=True)

    # 建立比較表
    raw_data = [
        {
            "策略": f"{lev_label} LRS",
            "期末資產": stats_lrs[0], "總報酬率": stats_lrs[1], "年化報酬 (CAGR)": stats_lrs[2],
            "夏普值 (Sharpe)": stats_lrs[5], "索提諾 (Sortino)": stats_lrs[6], "風報比 (Calmar)": stats_lrs[7],
            "最大回撤 (MDD)": stats_lrs[3], "年化波動率": stats_lrs[4], "交易次數": trade_count
        },
        {
            "策略": f"{lev_label} BH",
            "期末資產": stats_lev[0], "總報酬率": stats_lev[1], "年化報酬 (CAGR)": stats_lev[2],
            "夏普值 (Sharpe)": stats_lev[5], "索提諾 (Sortino)": stats_lev[6], "風報比 (Calmar)": stats_lev[7],
            "最大回撤 (MDD)": stats_lev[3], "年化波動率": stats_lev[4], "交易次數": np.nan
        },
        {
            "策略": f"{base_label} BH",
            "期末資產": stats_base[0], "總報酬率": stats_base[1], "年化報酬 (CAGR)": stats_base[2],
            "夏普值 (Sharpe)": stats_base[5], "索提諾 (Sortino)": stats_base[6], "風報比 (Calmar)": stats_base[7],
            "最大回撤 (MDD)": stats_base[3], "年化波動率": stats_base[4], "交易次數": np.nan
        }
    ]
    
    df_table = pd.DataFrame(raw_data).set_index("策略").T

    # 顯示用 DataFrame
    df_display = df_table.copy()
    format_map = {
        "期末資產": fmt_money, "總報酬率": fmt_pct, "年化報酬 (CAGR)": fmt_pct,
        "夏普值 (Sharpe)": fmt_num, "索提諾 (Sortino)": fmt_num, "風報比 (Calmar)": fmt_num,
        "最大回撤 (MDD)": fmt_pct, "年化波動率": fmt_pct, "交易次數": fmt_int
    }
    for idx, func in format_map.items():
        if idx in df_display.index:
            df_display.loc[idx] = df_display.loc[idx].apply(func)

    # 自定義色階 (紅-黃-綠)
    cmap = mcolors.LinearSegmentedColormap.from_list("custom", ["#e74c3c", "#f1c40f", "#2ecc71"])

    def get_style(val, vmin, vmax, invert=False):
        if pd.isna(val): return ""
        if vmax == vmin: norm = 0.5
        else: norm = (val - vmin) / (vmax - vmin)
        if invert: norm = 1 - norm
        
        rgba = cmap(norm)
        # 關鍵：使用透明度 0.2，這樣文字顏色會沿用 CSS 變數 (黑或白)，背景則有淡淡色彩
        return f"background-color: rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, 0.2); font-weight: 600;"

    styled = df_display.style
    # 應用表格 CSS Class
    styled = styled.set_table_attributes('class="table-finance"')
    
    # 應用熱力圖
    invert_metrics = ["最大回撤 (MDD)", "年化波動率"]
    for idx, row in df_table.iterrows():
        vals = row.astype(float).values
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        invert = idx in invert_metrics
        styles = [get_style(v, vmin, vmax, invert) for v in vals]
        styled = styled.apply(lambda x, s=styles: s, axis=1, subset=pd.IndexSlice[idx, :])

    # 針對 Header 和 Index 做樣式修正 (透過 CSS 變數)
    styled = styled.set_table_styles([
        {"selector": "th", "props": [
            ("background-color", "var(--secondary-background-color)"), 
            ("color", "var(--text-color)"),
            ("text-align", "center"), ("padding", "12px"), ("border-bottom", "2px solid rgba(128,128,128,0.2)")
        ]},
        {"selector": "th.index_name", "props": [
            ("background-color", "var(--background-color)"),
            ("text-align", "right"), ("border-right", "2px solid rgba(128,128,128,0.1)")
        ]},
        {"selector": "td", "props": [("text-align", "center"), ("padding", "10px"), ("border-bottom", "1px solid rgba(128,128,128,0.1)")]}
    ])

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.write(styled.to_html(), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# 當還沒按開始時的提示
elif not st.session_state.run_analysis:
    st.info("👈 請在左側側邊欄設定參數，並點擊「🚀 開始分析」按鈕。")
