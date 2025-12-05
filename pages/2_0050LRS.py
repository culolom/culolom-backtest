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
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿策略回測</h1>",
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
        # 1. 準備數據
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]

        # 這裡為了雷達圖好看，將數據標準化 (0~1) 或是直接繪製原始數值
        # 為了避免不同量級(如 30% 和 1.1) 顯示問題，建議先做簡單的 Min-Max Scaling 顯示相對強弱
        # 或者直接顯示數值，但要注意軸的刻度。這裡維持您的原始邏輯 (數值)，但優化視覺。
        
        # 建立數據 List
        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        # 為了讓雷達圖閉合，通常 Plotly 需要把最後一點重複加回第一點 (但在 Scatterpolar 有 fill 屬性時通常會自動閉合，保險起見這裡不手動加，直接畫)

        fig_radar = go.Figure()

        # LRS (主角 - 紫色系)
        fig_radar.add_trace(go.Scatterpolar(
            r=radar_lrs, 
            theta=radar_categories, 
            fill='toself', 
            name='LRS 策略',
            line=dict(color='#636EFA', width=3),
            fillcolor='rgba(99, 110, 250, 0.2)' # 半透明填充
        ))

        # 槓桿 BH (對照組1 - 紅色系)
        fig_radar.add_trace(go.Scatterpolar(
            r=radar_lev, 
            theta=radar_categories, 
            fill='toself', 
            name=f'{lev_label} BH',
            line=dict(color='#EF553B', width=2, dash='solid'),
            fillcolor='rgba(239, 85, 59, 0.15)'
        ))

        # 原型 BH (對照組2 - 綠色系)
        fig_radar.add_trace(go.Scatterpolar(
            r=radar_base, 
            theta=radar_categories, 
            fill='toself', 
            name=f'{base_label} BH',
            line=dict(color='#00CC96', width=2, dash='dash'),
            fillcolor='rgba(0, 204, 150, 0.1)'
        ))

        # 2. 視覺設定 (關鍵修復部分)
        fig_radar.update_layout(
            height=480,
            # 移除 template="plotly_white"，改為全透明設定
            paper_bgcolor='rgba(0,0,0,0)', # 外框透明
            plot_bgcolor='rgba(0,0,0,0)',  # 繪圖區透明
            polar=dict(
                bgcolor='rgba(0,0,0,0)',   # 雷達圖圓盤背景透明 (關鍵!)
                radialaxis=dict(
                    visible=True,
                    range=[None, None], # 自動抓範圍
                    showticklabels=True,
                    ticks='', # 不顯示刻度線
                    gridcolor='rgba(128, 128, 128, 0.2)', # 網格線改為淡灰色 (深淺通用)
                    linecolor='rgba(128, 128, 128, 0.3)'  # 軸線淡灰
                ),
                angularaxis=dict(
                    gridcolor='rgba(128, 128, 128, 0.2)',
                    linecolor='rgba(128, 128, 128, 0.3)'
                )
            ),
            legend=dict(
                orientation="h",  # 圖例水平排列
                yanchor="bottom",
                y=-0.15,          # 放在圖表下方
                xanchor="center",
                x=0.5
            ),
            font=dict(
                family="Noto Sans TC",
                size=12,
                # 不指定 color，讓 Streamlit 自動根據 theme 決定文字顏色 (黑/白)
            ),
            margin=dict(l=40, r=40, t=40, b=40)
        )

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
    # KPI Summary (美化卡片版 + 自動適應深淺色)
    ###############################################################

    # 計算 Gap (與槓桿BH相比)
    asset_gap_lrs_vs_lev = ((capital_lrs_final / capital_lev_final) - 1) * 100
    cagr_gap_lrs_vs_lev = (cagr_lrs - cagr_lev) * 100
    vol_gap_lrs_vs_lev = (vol_lrs - vol_lev) * 100
    mdd_gap_lrs_vs_lev = (mdd_lrs - mdd_lev) * 100

    # 定義 CSS 樣式 (使用 CSS Variables 適應深淺色)
    st.markdown("""
    <style>
        .kpi-card {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.15);
            border-radius: 12px;
            padding: 20px 16px;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            justify-content: space-between;
            height: 100%;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .kpi-card:hover {
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        .kpi-label {
            font-size: 0.9rem;
            color: var(--text-color);
            opacity: 0.7;
            font-weight: 500;
            margin-bottom: 4px;
        }
        .kpi-value {
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--text-color);
            margin-bottom: 12px;
            font-family: 'Noto Sans TC', sans-serif;
        }
        /* 漲跌幅標籤 (Chip 樣式) */
        .delta-chip {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            white-space: nowrap;
        }
        /* 正面狀態 (綠色) */
        .delta-positive {
            background-color: rgba(33, 195, 84, 0.15);
            color: #21c354;
        }
        /* 負面狀態 (紅色) */
        .delta-negative {
            background-color: rgba(255, 43, 43, 0.15);
            color: #ff2b2b;
        }
        /* 中性狀態 */
        .delta-neutral {
            background-color: rgba(128, 128, 128, 0.15);
            color: var(--text-color);
            opacity: 0.7;
        }
    </style>
    """, unsafe_allow_html=True)

    # 輔助函式：產生單張卡片的 HTML
    def kpi_card_html(label, value, gap_val, invert_logic=False):
        """
        invert_logic=True 代表「數值越低越好」(如 MDD, 波動率)
        Gap < 0 時顯示為綠色 (好)
        """
        # 判斷好壞顏色
        is_good = False
        if invert_logic:
            # 波動/MDD：Gap 為負 (下降) 是好事
            if gap_val < 0: is_good = True
        else:
            # 資產/CAGR：Gap 為正 (上升) 是好事
            if gap_val > 0: is_good = True

        # 決定顏色 class
        if abs(gap_val) < 0.01:
            delta_class = "delta-neutral"
            sign_str = ""
            icon = "➖"
        elif is_good:
            delta_class = "delta-positive"
            sign_str = "+" if gap_val > 0 else "" # 顯示 + 號，若原本就是負號則不用
            icon = "🔼" if not invert_logic else "🔽" # 變多用上箭頭，變少(好)用下箭頭
        else:
            delta_class = "delta-negative"
            sign_str = "+" if gap_val > 0 else ""
            icon = "🔽" if not invert_logic else "🔼" # 變少用下箭頭，變多(壞)用上箭頭
        
        # 格式化 Gap 文字
        delta_text = f"{icon} 較槓桿 {sign_str}{gap_val:.2f}%"

        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="delta-chip {delta_class}">
                {delta_text}
            </div>
        </div>
        """

    # 建立 4 欄佈局
    row1 = st.columns(4)

    with row1[0]:
        st.markdown(kpi_card_html(
            "期末資產 (LRS)", 
            format_currency(capital_lrs_final), 
            asset_gap_lrs_vs_lev, 
            invert_logic=False
        ), unsafe_allow_html=True)

    with row1[1]:
        st.markdown(kpi_card_html(
            "CAGR (年化)", 
            format_percent(cagr_lrs), 
            cagr_gap_lrs_vs_lev, 
            invert_logic=False
        ), unsafe_allow_html=True)

    with row1[2]:
        st.markdown(kpi_card_html(
            "年化波動 (LRS)", 
            format_percent(vol_lrs), 
            vol_gap_lrs_vs_lev, 
            invert_logic=True  # 波動率越低越好 -> invert=True
        ), unsafe_allow_html=True)

    with row1[3]:
        st.markdown(kpi_card_html(
            "最大回撤 (MDD)", 
            format_percent(mdd_lrs), 
            mdd_gap_lrs_vs_lev, 
            invert_logic=True  # MDD 越低越好 -> invert=True
        ), unsafe_allow_html=True)
    
    # 增加一點間距
    st.markdown("<div style='margin-bottom: 20px'></div>", unsafe_allow_html=True)

    ###############################################################
    # 完整比較表格（直式美化版 + 自動適應深淺色模式）
    ###############################################################

    # 1. 準備原始數據 (以策略名稱為 Index，方便轉置)
    # 這裡將 MDD 和 波動率 轉為負值存入 raw_data 僅是為了 heatmap 計算邏輯一致(越大越綠)，顯示時會轉回正值
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.85em; opacity:0.7'>LRS 策略</span>": {
            "期末資產": capital_lrs_final,
            "總報酬率": final_ret_lrs,
            "CAGR (年化)": cagr_lrs,
            "Calmar Ratio": calmar_lrs,
            "最大回撤 (MDD)": mdd_lrs, # 稍後處理顏色邏輯
            "年化波動": vol_lrs,       # 稍後處理顏色邏輯
            "Sharpe Ratio": sharpe_lrs,
            "Sortino Ratio": sortino_lrs,
            "交易次數": trade_count_lrs,
        },
        f"<b>{lev_label}</b><br><span style='font-size:0.85em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": capital_lev_final,
            "總報酬率": final_ret_lev,
            "CAGR (年化)": cagr_lev,
            "Calmar Ratio": calmar_lev,
            "最大回撤 (MDD)": mdd_lev,
            "年化波動": vol_lev,
            "Sharpe Ratio": sharpe_lev,
            "Sortino Ratio": sortino_lev,
            "交易次數": -1, # 無意義
        },
        f"<b>{base_label}</b><br><span style='font-size:0.85em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": capital_base_final,
            "總報酬率": final_ret_base,
            "CAGR (年化)": cagr_base,
            "Calmar Ratio": calmar_base,
            "最大回撤 (MDD)": mdd_base,
            "年化波動": vol_base,
            "Sharpe Ratio": sharpe_base,
            "Sortino Ratio": sortino_base,
            "交易次數": -1, # 無意義
        }
    }

    # 轉置：Index 變成指標，Columns 變成策略
    df_vertical = pd.DataFrame(data_dict)

    # 2. 定義格式化與顏色邏輯
    # invert_color: True 代表數值越小越好 (MDD, 波動)
    metrics_config = {
        "期末資產":       {"fmt": fmt_money, "invert": False},
        "總報酬率":       {"fmt": fmt_pct,   "invert": False},
        "CAGR (年化)":    {"fmt": fmt_pct,   "invert": False},
        "Calmar Ratio":   {"fmt": fmt_num,   "invert": False},
        "最大回撤 (MDD)": {"fmt": fmt_pct,   "invert": True},  # 越小越好
        "年化波動":       {"fmt": fmt_pct,   "invert": True},  # 越小越好
        "Sharpe Ratio":   {"fmt": fmt_num,   "invert": False},
        "Sortino Ratio":  {"fmt": fmt_num,   "invert": False},
        "交易次數":       {"fmt": lambda x: fmt_int(x) if x >=0 else "—", "invert": True} # 次數少比較省手續費? 或不套色
    }

    # 3. 建立 HTML 表格字串
    # 使用 CSS Variables (var(--...)) 確保深色/淺色模式都能正確顯示文字顏色
    html_code = """
    <style>
        .comparison-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--secondary-background-color);
            font-family: 'Noto Sans TC', sans-serif;
            margin-bottom: 1rem;
        }
        .comparison-table th {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            padding: 12px;
            text-align: center;
            font-weight: bold;
            border-bottom: 2px solid var(--background-color);
        }
        /* 第一欄 (指標名稱) 靠左並加強顯示 */
        .comparison-table td.metric-name {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            font-weight: 600;
            text-align: left;
            padding: 10px 15px;
            width: 20%;
            border-bottom: 1px solid var(--background-color);
        }
        .comparison-table td.data-cell {
            text-align: center;
            padding: 10px;
            color: var(--text-color);
            border-bottom: 1px solid var(--secondary-background-color);
            transition: background-color 0.3s;
        }
        .comparison-table tr:last-child td {
            border-bottom: none;
        }
        /* Hover 效果 */
        .comparison-table tr:hover td.data-cell {
            filter: brightness(0.95);
        }
    </style>
    <table class="comparison-table">
        <thead>
            <tr>
                <th style="text-align:left; padding-left:15px;">📊 策略指標</th>
    """
    
    # 寫入表頭 (策略名稱)
    for col_name in df_vertical.columns:
        html_code += f"<th>{col_name}</th>"
    html_code += "</tr></thead><tbody>"

    # 寫入內容 (逐列處理)
    import matplotlib.colors as mcolors

    # 定義顏色映射函數 (數值, 該列最小值, 該列最大值, 是否反轉)
    def get_color(val, vmin, vmax, invert=False):
        if np.isnan(val) or val == -1: return "transparent"
        
        # 防止除以零
        if vmax == vmin: return "transparent"
        
        # 歸一化 0~1
        norm = (val - vmin) / (vmax - vmin)
        if invert:
            norm = 1 - norm # 反轉：數值越小(MDD)，norm 越接近 1 (越綠)
            
        # 為了美觀且適應深淺色，我們使用帶透明度的顏色 (RGBA)
        # 紅(壞) -> 黃 -> 綠(好)
        # 0.0(Red) -> 0.5(Yellow) -> 1.0(Green)
        # 我們只取 "背景色"，文字顏色保持 var(--text-color)
        
        # 使用自定義的柔和色調
        # 壞 (Red): rgba(255, 80, 80, alpha)
        # 好 (Green): rgba(33, 195, 84, alpha)
        
        alpha = 0.15 + (norm * 0.25) # 透明度範圍 0.15 ~ 0.4 (不要太深，確保文字可讀)
        
        if norm > 0.5:
             # 偏綠 (好)
             return f"rgba(33, 195, 84, {alpha:.2f})"
        else:
             # 偏紅 (壞) - norm 越小越紅
             # 調整 alpha 讓紅色的強度隨差勁程度增加
             red_alpha = 0.15 + ((1-norm) * 0.25)
             return f"rgba(255, 80, 80, {red_alpha:.2f})"

    for metric in df_vertical.index:
        row_data = df_vertical.loc[metric]
        config = metrics_config.get(metric, {"fmt": fmt_num, "invert": False})
        
        # 計算該列的 min/max 用於 heatmap (排除無效值)
        valid_values = [x for x in row_data if isinstance(x, (int, float)) and x != -1]
        vmin = min(valid_values) if valid_values else 0
        vmax = max(valid_values) if valid_values else 0
        
        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        
        for strategy in df_vertical.columns:
            val = row_data[strategy]
            
            # 取得顯示文字
            display_text = config["fmt"](val)
            
            # 取得背景顏色
            bg_color = "transparent"
            if isinstance(val, (int, float)) and metric != "交易次數":
                bg_color = get_color(val, vmin, vmax, config["invert"])
            
            # 特別處理：如果是第一欄(LRS)，加粗顯示
            font_weight = "bold" if strategy == df_vertical.columns[0] else "normal"
            # LRS 欄位加個微邊框強調
            border_style = "border-left: 2px solid var(--primary-color);" if strategy == df_vertical.columns[0] else ""

            html_code += f"<td class='data-cell' style='background-color: {bg_color}; font-weight:{font_weight}; {border_style}'>{display_text}</td>"
        
        html_code += "</tr>"

    html_code += "</tbody></table>"
    
    st.write(html_code, unsafe_allow_html=True)
