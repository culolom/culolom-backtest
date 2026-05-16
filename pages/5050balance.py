###############################################################
# app.py — 新手友善版：固定比例 + 訊號觸發再平衡策略
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
    page_title="新手友善再平衡回測系統",
    page_icon="⚖️",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
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
    "<h1 style='margin-bottom:0.5em;'>⚖️ 新手友善：紀律再平衡策略</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具專為新手設計，解決「不知何時再平衡」的痛點：</b><br>
1️⃣ 選擇你心儀的資產配置 (5050 或 433)<br>
2️⃣ 設定再平衡的技術觸發條件 (目前採用 200SMA 紀律觸發)<br>
3️⃣ 程式將自動回測：平時放著不管，<b>只有當價格碰到設定的條件時，才執行一次再平衡 (將比例校正回初始設定)</b>。
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

@st.cache_data
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

###############################################################
# UI 輸入
###############################################################

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號與標的）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（標的）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(base_symbol, lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

# 基本參數
col3, col4, col5 = st.columns(3)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 再平衡策略設定")

col_strat1, col_strat2 = st.columns(2)

with col_strat1:
    portfolio_mode = st.radio(
        "選擇資產配置比例",
        [
            "5050 策略 (50% 現金, 50% 正2)",
            "433 策略 (40% 原型, 30% 正2, 30% 現金)"
        ]
    )

with col_strat2:
    enable_200sma = st.checkbox(
        "啟用再平衡：收盤價穿越 200SMA", 
        value=True, 
        help="當原型 ETF 收盤價「穿越」200日均線時，將強制觸發資產比例校正。"
    )

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):
    
    # 確保 200SMA 有足夠的歷史資料可算
    max_lookback = 200
    start_early = start - dt.timedelta(days=int(max_lookback * 1.5) + 30) 

    with st.spinner("計算指標與回測中…"):
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

    # 計算技術指標 (以原型 ETF 為準)
    df["SMA_200"] = df["Price_base"].rolling(200).mean()

    # 濾掉 MA 計算期間的空值
    df = df.dropna(subset=["SMA_200"])
    df = df.loc[start:end]
    
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    ###############################################################
    # 再平衡策略邏輯
    ###############################################################

    # 設定目標權重
    if "5050" in portfolio_mode:
        target_w_base = 0.0
        target_w_lev = 0.5
        target_w_cash = 0.5
    else: # 433
        target_w_base = 0.4
        target_w_lev = 0.3
        target_w_cash = 0.3

    # 初始化每日資金
    val_base = target_w_base * 1.0
    val_lev = target_w_lev * 1.0
    val_cash = target_w_cash * 1.0

    equity_curve = [1.0]
    rebalance_signals = [0] * len(df) # 記錄再平衡天數

    for i in range(1, len(df)):
        # 1. 根據昨日持倉更新今日價值
        ret_b = df["Return_base"].iloc[i]
        ret_l = df["Return_lev"].iloc[i]
        
        val_base = val_base * (1 + ret_b)
        val_lev = val_lev * (1 + ret_l)
        # 現金價值不變 (無風險利率設為0)

        # 總資產
        total_equity = val_base + val_lev + val_cash
        equity_curve.append(total_equity)

        # 2. 檢查是否觸發再平衡 (發生穿越)
        p = df["Price_base"].iloc[i]
        p0 = df["Price_base"].iloc[i-1]
        
        trigger_rebalance = False
        
        if enable_200sma:
            sma = df["SMA_200"].iloc[i]
            sma0 = df["SMA_200"].iloc[i-1]
            # 判斷黃金交叉或死亡交叉
            if (p0 < sma0 and p >= sma) or (p0 > sma0 and p <= sma):
                trigger_rebalance = True

        # 3. 執行再平衡
        if trigger_rebalance:
            val_base = total_equity * target_w_base
            val_lev = total_equity * target_w_lev
            val_cash = total_equity * target_w_cash
            rebalance_signals[i] = 1

    df["Equity_Strat"] = equity_curve
    df["Return_Strat"] = df["Equity_Strat"].pct_change().fillna(0)
    df["Signal"] = rebalance_signals

    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    # 計算「策略不再平衡 (Buy & Hold from Day 1)」的資金曲線
    df["Equity_No_Rebal"] = (target_w_base * df["Equity_BH_Base"]) + \
                            (target_w_lev * df["Equity_BH_Lev"]) + \
                            (target_w_cash * 1.0)
    df["Return_No_Rebal"] = df["Equity_No_Rebal"].pct_change().fillna(0)

    # 計算繪圖用的累積報酬率 Pct
    df["Pct_Base"] = df["Equity_BH_Base"] - 1
    df["Pct_No_Rebal"] = df["Equity_No_Rebal"] - 1
    df["Pct_Strat"] = df["Equity_Strat"] - 1

    rebalance_dates = df[df["Signal"] == 1]

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

    eq_strat_final, final_ret_strat, cagr_strat, mdd_strat, vol_strat, sharpe_strat, sortino_strat, calmar_strat = calc_core(df["Equity_Strat"], df["Return_Strat"])
    eq_no_rebal_final, final_ret_no_rebal, cagr_no_rebal, mdd_no_rebal, vol_no_rebal, sharpe_no_rebal, sortino_no_rebal, calmar_no_rebal = calc_core(df["Equity_No_Rebal"], df["Return_No_Rebal"])
    eq_base_final, final_ret_base, cagr_base, mdd_base, vol_base, sharpe_base, sortino_base, calmar_base = calc_core(df["Equity_BH_Base"], df["Return_base"])

    capital_strat_final = eq_strat_final * capital
    capital_no_rebal_final = eq_no_rebal_final * capital
    capital_base_final = eq_base_final * capital
    trade_count_strat = int(df["Signal"].sum())

    ###############################################################
    # 圖表 + KPI + 表格
    ###############################################################

    # --- 統一顏色設定 ---
    COLOR_BASE = "#FFA15A"    # 橘色 (原型 B&H)
    COLOR_NO_REBAL = "#00CC96" # 綠色 (策略不再平衡)
    COLOR_STRAT = "#636EFA"   # 藍色 (策略再平衡)

    st.markdown("<h3>📌 技術指標與再平衡觸發點</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    # 原型 ETF 與指標
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label}", mode="lines", line=dict(width=2, color=COLOR_BASE)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["SMA_200"], name="200SMA", mode="lines", line=dict(width=1.5, color="#1f77b4", dash='dot')))

    # 再平衡點
    if not rebalance_dates.empty:
        hover_txt = [f"<b>🔄 執行再平衡</b><br>{d.strftime('%Y-%m-%d')}<br>價格: {p:.2f}" for d, p in zip(rebalance_dates.index, rebalance_dates["Price_base"])]
        fig_price.add_trace(go.Scatter(
            x=rebalance_dates.index, y=rebalance_dates["Price_base"], mode="markers", name="再平衡觸發點", 
            marker=dict(color="#FFD700", size=10, symbol="star", line=dict(width=1, color="black")),
            hoverinfo="text", hovertext=hover_txt
        ))

    fig_price.update_layout(template="plotly_white", height=450, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.02, x=1, xanchor="right"))
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # Tabs
    ###############################################################

    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar = st.tabs(["資金曲線", "回撤比較", "風險雷達"])

    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型 B&H", line=dict(color=COLOR_BASE)))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_No_Rebal"], mode="lines", name="策略不再平衡", line=dict(color=COLOR_NO_REBAL, dash='dash')))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Strat"], mode="lines", name="策略再平衡", line=dict(color=COLOR_STRAT, width=2.5)))
        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_no_rebal = (df["Equity_No_Rebal"] / df["Equity_No_Rebal"].cummax() - 1) * 100
        dd_strat = (df["Equity_Strat"] / df["Equity_Strat"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型 B&H", line=dict(color=COLOR_BASE)))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_no_rebal, name="策略不再平衡", line=dict(color=COLOR_NO_REBAL, dash='dash')))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略再平衡", fill="tozeroy", line=dict(color=COLOR_STRAT)))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_strat  = [nz(cagr_strat),  nz(sharpe_strat),  nz(sortino_strat),  nz(-mdd_strat),  nz(-vol_strat)]
        radar_no_rebal = [nz(cagr_no_rebal), nz(sharpe_no_rebal), nz(sortino_no_rebal), nz(-mdd_no_rebal), nz(-vol_no_rebal)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_strat, theta=radar_categories, fill='toself', name='策略再平衡', line=dict(color=COLOR_STRAT, width=3)))
        fig_radar.add_trace(go.Scatterpolar(r=radar_no_rebal, theta=radar_categories, fill='toself', name='策略不再平衡', line=dict(color=COLOR_NO_REBAL, width=2)))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base, theta=radar_categories, fill='toself', name=f'{base_label} B&H', line=dict(color=COLOR_BASE, width=2)))
        
        fig_radar.update_layout(height=480, paper_bgcolor='rgba(0,0,0,0)', polar=dict(radialaxis=dict(visible=True, showticklabels=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    ###############################################################
    # 表格 
    ###############################################################
    st.markdown("<br>", unsafe_allow_html=True)
    
    metrics_order = ["期末資產", "CAGR (年化)", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "總觸發再平衡次數"]
    
    data_dict = {
        f"策略再平衡 ({portfolio_mode[:4]})": {
            "期末資產": fmt_money(capital_strat_final),
            "CAGR (年化)": fmt_pct(cagr_strat),
            "最大回撤 (MDD)": fmt_pct(mdd_strat),
            "年化波動": fmt_pct(vol_strat),
            "Sharpe Ratio": fmt_num(sharpe_strat),
            "總觸發再平衡次數": fmt_int(trade_count_strat),
        },
        f"{base_label} (B&H)": {
            "期末資產": fmt_money(capital_base_final),
            "CAGR (年化)": fmt_pct(cagr_base),
            "最大回撤 (MDD)": fmt_pct(mdd_base),
            "年化波動": fmt_pct(vol_base),
            "Sharpe Ratio": fmt_num(sharpe_base),
            "總觸發再平衡次數": "—",
        },
        f"策略不再平衡 ({portfolio_mode[:4]})": {
            "期末資產": fmt_money(capital_no_rebal_final),
            "CAGR (年化)": fmt_pct(cagr_no_rebal),
            "最大回撤 (MDD)": fmt_pct(mdd_no_rebal),
            "年化波動": fmt_pct(vol_no_rebal),
            "Sharpe Ratio": fmt_num(sharpe_no_rebal),
            "總觸發再平衡次數": "0", 
        }
    }

    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)
    st.table(df_vertical)
    
    # 匯出 CSV 區塊
    st.markdown("<br>", unsafe_allow_html=True)
    export_cols = ["Price_base", "Price_lev", "SMA_200", "Signal", "Equity_Strat", "Equity_No_Rebal"]
    valid_cols = [c for c in export_cols if c in df.columns]
    csv_data = df[valid_cols].to_csv(index=True).encode('utf-8-sig')
    
    st.download_button(
        label="📥 下載詳細回測數據 (CSV)",
        data=csv_data,
        file_name=f"Rebalance_Backtest_{base_label}_{start}_{end}.csv",
        mime="text/csv"
    )

    st.markdown("<br><hr>", unsafe_allow_html=True)
    footer_html = """
    <div style="text-align: center; color: gray; font-size: 0.85rem; line-height: 1.6;">
        <p style="font-style: italic;">免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。投資必定有風險，過去之績效不保證未來表現，使用者應自行審慎評估風險並自負盈虧。</p>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
