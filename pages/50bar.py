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
    page_title="0050LRS 回測系統",
    page_icon="📈",
    layout="wide",
)
# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import auth 
    if not auth.check_password():
        st.stop()  # 驗證沒過就停止執行
except ImportError:
    pass 

# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
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
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold（0050 / 006208）<br>
2️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
3️⃣ 槓桿 ETF LRS（訊號來自原型 ETF 的 SMA 均線，實際進出槓桿 ETF）<br>
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

# 4 欄位：開始日期、結束日期、本金、SMA
col3, col4, col5, col6 = st.columns(4)
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

with col6:
    sma_window = st.number_input(
        "均線週期 (SMA)", 
        min_value=10, 
        max_value=240, 
        value=200, 
        step=10,
        help="設定 LRS 策略的均線參數，預設為 200，最高可設為 240。"
    )

position_mode = st.radio(
    "策略初始狀態",
    ["一開始就全倉槓桿 ETF","空手起跑（標準 LRS）"],
    index=0,
)

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60) # 動態緩衝

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

    # 使用 UI 設定的 sma_window
    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df = df.dropna(subset=["MA_Signal"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    ###############################################################
    # LRS 訊號與持倉邏輯 (修正版：過濾無效訊號)
    ###############################################################

    # 1. 初始化容器
    executed_signals = [0] * len(df) # 記錄真正執行的訊號
    positions = [0] * len(df)        # 記錄每天的持倉狀態

    # 2. 設定初始狀態
    # 如果選 "一開始就全倉"，第 0 天就是持倉 (1)，否則為空手 (0)
    current_pos = 1 if "全倉" in position_mode else 0
    positions[0] = current_pos

    # 3. 逐日遍歷 (將訊號與持倉邏輯綁定)
    for i in range(1, len(df)):
        p = df["Price_base"].iloc[i]
        m = df["MA_Signal"].iloc[i]
        p0 = df["Price_base"].iloc[i-1]
        m0 = df["MA_Signal"].iloc[i-1]

        # 先判斷技術面訊號 (Raw Signal)
        # 1 = 黃金交叉, -1 = 死亡交叉, 0 = 無
        raw_signal = 0
        if p > m and p0 <= m0:
            raw_signal = 1
        elif p < m and p0 >= m0:
            raw_signal = -1

        # 再判斷 "實際執行" (根據當下持倉過濾)
        daily_signal = 0 
        
        if current_pos == 0:
            # 狀況 A：目前空手 -> 只能接受買入訊號
            if raw_signal == 1:
                daily_signal = 1
                current_pos = 1 # 狀態轉為持倉
        
        elif current_pos == 1:
            # 狀況 B：目前持倉 -> 只能接受賣出訊號
            if raw_signal == -1:
                daily_signal = -1
                current_pos = 0 # 狀態轉為空手
            # 如果 raw_signal == 1 (又出現買訊)，因為已持倉，直接忽略
        
        # 記錄結果
        executed_signals[i] = daily_signal
        positions[i] = current_pos

    # 4. 寫回 DataFrame
    df["Signal"] = executed_signals
    df["Position"] = positions

    ###############################################################
    # 資金曲線 (修正版：包含賣出當日損益)
    ###############################################################

    equity_lrs = [1.0]
    for i in range(1, len(df)):
        # 邏輯修正：只要「昨天收盤」是持有狀態，今天就要計算漲跌幅
        # (因為是看收盤價進出，所以今天賣出代表今天整天的漲跌都要算)
        if df["Position"].iloc[i-1] == 1:
            r = df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]
            equity_lrs.append(equity_lrs[-1] * r)
        else:
            # 昨天空手，今天不管買不買，損益都是從明天開始算 (收盤才買進)
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

    # --- 原型 & MA & 槓桿價格 (雙軸圖表) ---
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    # 1. [左軸] 原型 ETF (訊號來源)
    fig_price.add_trace(go.Scatter(
        x=df.index, 
        y=df["Price_base"], 
        name=f"{base_label} (左軸)", 
        mode="lines",
        line=dict(width=2, color="#636EFA"),
        hovertemplate=f"<b>{base_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 2. [左軸] SMA (動態)
    fig_price.add_trace(go.Scatter(
        x=df.index, 
        y=df["MA_Signal"], 
        name=f"{sma_window} 日 SMA", 
        mode="lines",
        line=dict(width=1.5, color="#FFA15A"),
        hovertemplate=f"<b>{sma_window}SMA</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 3. [右軸] 槓桿 ETF (實際標的) - 使用虛線區隔
    fig_price.add_trace(go.Scatter(
        x=df.index, 
        y=df["Price_lev"], 
        name=f"{lev_label} (右軸)", 
        mode="lines",
        line=dict(width=1, color="#00CC96", dash='dot'), # 虛線
        opacity=0.6, # 半透明，避免搶戲
        yaxis="y2",  # 指定到右邊的 Y 軸
        hovertemplate=f"<b>{lev_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 4. [標記] 買進點 (顯示雙價格)
    if not buys.empty:
        # 準備 Tooltip 需要的數據：同時包含 Base 和 Lev 的價格
        buy_hover_text = [
            f"<b>▲ 買進訊號 (Buy)</b><br>"
            f"日期: {d.strftime('%Y-%m-%d')}<br>"
            f"------------------<br>"
            f"訊號 ({base_label}): {p_base:,.2f} 元<br>"
            f"成交 ({lev_label}): <b>{p_lev:,.2f} 元</b>"
            for d, p_base, p_lev in zip(buys.index, buys["Price_base"], buys["Price_lev"])
        ]

        fig_price.add_trace(go.Scatter(
            x=buys.index, 
            y=buys["Price_base"], # 標記還是畫在左軸(訊號線)上，視覺上才準
            mode="markers",
            name="買進訊號", 
            marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white")),
            hoverinfo="text", # 使用自定義 text
            hovertext=buy_hover_text
        ))

    # 5. [標記] 賣出點 (顯示雙價格)
    if not sells.empty:
        sell_hover_text = [
            f"<b>▼ 賣出訊號 (Sell)</b><br>"
            f"日期: {d.strftime('%Y-%m-%d')}<br>"
            f"------------------<br>"
            f"訊號 ({base_label}): {p_base:,.2f} 元<br>"
            f"成交 ({lev_label}): <b>{p_lev:,.2f} 元</b>"
            for d, p_base, p_lev in zip(sells.index, sells["Price_base"], sells["Price_lev"])
        ]

        fig_price.add_trace(go.Scatter(
            x=sells.index, 
            y=sells["Price_base"], 
            mode="markers",
            name="賣出訊號", 
            marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white")),
            hoverinfo="text",
            hovertext=sell_hover_text
        ))

    # 6. Layout 設定 (雙軸)
    fig_price.update_layout(
        template="plotly_white", 
        height=450,
        hovermode="x unified", # 統一顯示 x 軸資訊
        yaxis=dict(
            title=f"{base_label} 價格",
            showgrid=True,
            zeroline=False
        ),
        yaxis2=dict(
            title=f"{lev_label} 價格",
            overlaying="y", # 疊加在第一個 y 軸上
            side="right",   # 放在右邊
            showgrid=False, # 右軸不顯示網格，避免線條太亂
            zeroline=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    
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
    # KPI Summary (高級儀表板風格 + 正綠負紅邏輯)
    ###############################################################

    # 1. 計算 Gap (與槓桿BH相比)
    asset_gap_lrs_vs_lev = ((capital_lrs_final / capital_lev_final) - 1) * 100
    cagr_gap_lrs_vs_lev = (cagr_lrs - cagr_lev) * 100
    vol_gap_lrs_vs_lev = (vol_lrs - vol_lev) * 100
    mdd_gap_lrs_vs_lev = (mdd_lrs - mdd_lev) * 100

    # 2. 定義高級 CSS 樣式 (卡片、陰影、圓角)
    st.markdown("""
    <style>
        /* 卡片容器：背景色、圓角、陰影 */
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px; /* 更圓潤的角 */
            padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04); /* 靜態微陰影 */
            border: 1px solid rgba(128, 128, 128, 0.1);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            transition: all 0.3s ease; /* 動畫過渡 */
        }
        
        /* 滑鼠懸停效果：浮起 + 加深陰影 */
        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08);
            border-color: rgba(128, 128, 128, 0.2);
        }

        .kpi-label {
            font-size: 0.9rem;
            color: var(--text-color);
            opacity: 0.7;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase; /* 標籤全大寫看起來比較高級 */
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-size: 2.2rem; /* 數字再加大一點 */
            font-weight: 900; /* 使用最粗的字體 */
            color: var(--text-color);
            margin-bottom: 16px;
            font-family: 'Noto Sans TC', sans-serif;
            line-height: 1.2;
            /* 增加文字陰影來模擬更加粗的效果，確保視覺上的粗體 */
            text-shadow: 0.5px 0 0 currentColor; 
        }

        /* 漲跌幅標籤 (Chip) */
        .delta-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 12px;
            border-radius: 20px; /* 膠囊形狀 */
            font-size: 0.85rem;
            font-weight: 700;
            width: fit-content;
        }

        /* 正值 (>0) 樣式：綠色背景 + 深綠字 */
        .delta-positive {
            background-color: rgba(33, 195, 84, 0.12);
            color: #21c354;
        }

        /* 負值 (<0) 樣式：紅色背景 + 深紅字 */
        .delta-negative {
            background-color: rgba(255, 60, 60, 0.12);
            color: #ff3c3c;
        }

        /* 中性值 (=0) 樣式：灰色 */
        .delta-neutral {
            background-color: rgba(128, 128, 128, 0.1);
            color: var(--text-color);
            opacity: 0.6;
        }

    </style>
    """, unsafe_allow_html=True)

    # 3. 輔助函式 (邏輯：正數綠色，負數紅色)
    def kpi_card_html(label, value, gap_val):
        
        # 判定顏色與箭頭
        if gap_val > 0.001:
            delta_class = "delta-positive"
            icon = "▲"
            sign_str = "+"
        elif gap_val < -0.001:
            delta_class = "delta-negative"
            icon = "▼"
            sign_str = "" # 負數自帶負號
        else:
            delta_class = "delta-neutral"
            icon = "➖"
            sign_str = ""

        # 組合顯示文字
        delta_text = f"{icon} {sign_str}{gap_val:.2f}% (vs 槓桿)"

        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="font-weight:900;">{value}</div>
            <div class="delta-chip {delta_class}">
                {delta_text}
            </div>
        </div>
        """

    # 4. 建立佈局並渲染 (請確認這邊只有一次 st.columns)
    row_kpi = st.columns(4)

    with row_kpi[0]:
        st.markdown(kpi_card_html(
            "期末資產 (LRS)", 
            format_currency(capital_lrs_final), 
            asset_gap_lrs_vs_lev
        ), unsafe_allow_html=True)

    with row_kpi[1]:
        st.markdown(kpi_card_html(
            "CAGR (年化)", 
            format_percent(cagr_lrs), 
            cagr_gap_lrs_vs_lev
        ), unsafe_allow_html=True)

    with row_kpi[2]:
        st.markdown(kpi_card_html(
            "年化波動 (LRS)", 
            format_percent(vol_lrs), 
            vol_gap_lrs_vs_lev
        ), unsafe_allow_html=True)

    with row_kpi[3]:
        st.markdown(kpi_card_html(
            "最大回撤 (MDD)", 
            format_percent(mdd_lrs), 
            mdd_gap_lrs_vs_lev
        ), unsafe_allow_html=True)
    
    # 增加底部間距，避免與下方圖表太近
    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    ###############################################################
    # 完整比較表格 (極簡版：移除顏色，僅顯示冠軍 🏆)
    ###############################################################

    # 1. 定義要顯示的指標順序
    metrics_order = [
        "期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio",
        "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"
    ]

    # 2. 準備原始數據
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.85em; opacity:0.7'>LRS 策略</span>": {
            "期末資產": capital_lrs_final,
            "總報酬率": final_ret_lrs,
            "CAGR (年化)": cagr_lrs,
            "Calmar Ratio": calmar_lrs,
            "最大回撤 (MDD)": mdd_lrs,
            "年化波動": vol_lrs,
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
            "交易次數": -1, 
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
            "交易次數": -1,
        }
    }

    # 3. 建立 DataFrame 並排序
    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)

    # 4. 定義格式化與「好壞方向」
    # invert=True 代表數值「越小越好」
    metrics_config = {
        "期末資產":       {"fmt": fmt_money, "invert": False},
        "總報酬率":       {"fmt": fmt_pct,   "invert": False},
        "CAGR (年化)":    {"fmt": fmt_pct,   "invert": False},
        "Calmar Ratio":   {"fmt": fmt_num,   "invert": False},
        "最大回撤 (MDD)": {"fmt": fmt_pct,   "invert": True},  # 越小越贏
        "年化波動":       {"fmt": fmt_pct,   "invert": True},  # 越小越贏
        "Sharpe Ratio":   {"fmt": fmt_num,   "invert": False},
        "Sortino Ratio":  {"fmt": fmt_num,   "invert": False},
        "交易次數":       {"fmt": lambda x: fmt_int(x) if x >= 0 else "—", "invert": True} # 假設次數少較好，或不比較
    }

    # 5. 生成 HTML (樣式極簡化)
    html_code = """
    <style>
        .comparison-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            /* 極簡邊框 */
            border: 1px solid var(--secondary-background-color);
            font-family: 'Noto Sans TC', sans-serif;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }
        .comparison-table th {
            /* 表頭使用次要背景色 */
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            padding: 14px;
            text-align: center;
            font-weight: 600;
            border-bottom: 1px solid rgba(128,128,128, 0.1);
        }
        .comparison-table td.metric-name {
            background-color: transparent;
            color: var(--text-color);
            font-weight: 500;
            text-align: left;
            padding: 12px 16px;
            width: 25%;
            font-size: 0.9rem;
            border-bottom: 1px solid rgba(128,128,128, 0.1);
            opacity: 0.9;
        }
        .comparison-table td.data-cell {
            text-align: center;
            padding: 12px;
            color: var(--text-color);
            border-bottom: 1px solid rgba(128,128,128, 0.1);
        }
        /* 移除 LRS 的明顯底色，改為極淡的背景區分，或完全透明 */
        .comparison-table td.lrs-col {
            background-color: rgba(128, 128, 128, 0.03); 
        }
        /* 冠軍圖示樣式 */
        .trophy-icon {
            margin-left: 6px;
            font-size: 1.1em;
            text-shadow: 0 0 5px rgba(255, 215, 0, 0.4); /* 讓獎盃微微發光 */
        }
        .comparison-table tr:hover td {
            background-color: rgba(128,128,128, 0.05); /* Hover 整行微亮 */
        }
    </style>
    <table class="comparison-table">
        <thead>
            <tr>
                <th style="text-align:left; padding-left:16px; width:25%;">指標</th>
    """
    
    # 寫入表頭
    for col_name in df_vertical.columns:
        html_code += f"<th>{col_name}</th>"
    html_code += "</tr></thead><tbody>"

    # 寫入內容
    for metric in df_vertical.index:
        config = metrics_config.get(metric, {"fmt": fmt_num, "invert": False})
        
        # 1. 找出該列的「最佳值」(Winner Value)
        # 先取出所有有效數值
        raw_row_values = df_vertical.loc[metric].values
        valid_values = [x for x in raw_row_values if isinstance(x, (int, float)) and x != -1 and not pd.isna(x)]
        
        target_val = None
        if valid_values and metric != "交易次數": # 交易次數通常不比獎盃，看您需求
            if config["invert"]:
                target_val = min(valid_values) # 越小越好 (MDD, 波動)
            else:
                target_val = max(valid_values) # 越大越好 (報酬, Sharpe)

        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        
        # 2. 逐欄填入
        for i, strategy in enumerate(df_vertical.columns):
            val = df_vertical.at[metric, strategy]
            
            display_text = config["fmt"](val)
            
            # 判斷是否為冠軍
            is_winner = False
            if target_val is not None and isinstance(val, (int, float)) and val == target_val:
                is_winner = True
            
            # 如果是冠軍，加上獎盃
            if is_winner:
                display_text = f"{display_text} <span class='trophy-icon'>🏆</span>"
                # 也可以選擇讓冠軍文字變色，例如：
                # display_text = f"<span style='color:#e6a23c; font-weight:bold'>{display_text}</span> 🏆"
            
            # LRS 欄位樣式
            is_lrs = (i == 0)
            lrs_class = "lrs-col" if is_lrs else ""
            font_weight = "bold" if is_lrs else "normal"
            
            html_code += f"<td class='data-cell {lrs_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        
        html_code += "</tr>"

    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)
