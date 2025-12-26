###############################################################
# app.py — 0050LRS + 布林通道調節 (優先買進版)
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
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(
    page_title="LRS + 布林通道 (優先買進版)",
    page_icon="📉",
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
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 布林優先買進策略</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>策略邏輯 (優先級調整)：</b><br>
1️⃣ <b>抄底 (最高優先)</b>：收盤 < 布林下軌 (-2σ) ⮕ <span style='color:#66BB6A'><b>買進加碼</b></span> (無視均線)。<br>
2️⃣ <b>進場</b>：漲破 200SMA ⮕ <span style='color:#4CAF50'><b>All In (100%)</b></span>。<br>
3️⃣ <b>獲利調節</b>：收盤 > 布林上軌 (2σ) ⮕ <span style='color:#FFA726'><b>賣出減碼</b></span>。<br>
4️⃣ <b>停損</b>：收盤 < 200SMA 且 未跌破下軌 ⮕ <span style='color:#FF5252'><b>清空 (0%)</b></span>。<br>
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

# 基本參數
col3, col4, col5, col6 = st.columns(4)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)
with col6:
    sma_window = st.number_input("均線週期 (SMA)", min_value=10, max_value=240, value=200, step=10)

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 策略參數設定")

col_bb1, col_bb2 = st.columns(2)

with col_bb1:
    st.markdown("#### 🌊 布林通道設定")
    bb_std_dev = st.number_input("布林通道倍數 (σ)", min_value=1.0, max_value=4.0, value=2.0, step=0.1, help="設定通道寬度，通常為 2.0")
    # 移除緩衝設定
    st.caption("✅ 已移除停損緩衝功能，現在跌破下軌將強制買進。")
    
with col_bb2:
    st.markdown("#### ⚖️ 加減碼規則")
    action_pct = st.number_input("單次加/減碼比例 (%)", min_value=5, max_value=50, value=10, step=5, help="觸及通道時，每次調整多少倉位")
    action_interval = st.number_input("加減碼間隔天數 (日)", min_value=1, max_value=30, value=3, help="防止連續觸及通道導致過度頻繁交易")

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60) 

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

    # 1. 計算技術指標
    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df["Std_Dev"] = df["Price_base"].rolling(sma_window).std()
    
    # 布林通道
    df["BB_Upper"] = df["MA_Signal"] + (bb_std_dev * df["Std_Dev"])
    df["BB_Lower"] = df["MA_Signal"] - (bb_std_dev * df["Std_Dev"])

    df = df.dropna(subset=["MA_Signal", "BB_Upper"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # ###############################################################
    # 核心交易邏輯 (權重重構)
    # ###############################################################

    executed_signals = [0] * len(df)  # 記錄訊號
    positions = [0.0] * len(df)       # 記錄持倉比例
    
    # 初始狀態
    current_pos = 0.0 
    days_since_action = 999 

    # 如果第一天價格就在均線上，給予初始倉位
    if df["Price_base"].iloc[0] > df["MA_Signal"].iloc[0]:
        current_pos = 1.0

    positions[0] = current_pos

    for i in range(1, len(df)):
        price = df["Price_base"].iloc[i]
        prev_price = df["Price_base"].iloc[i-1]
        
        sma = df["MA_Signal"].iloc[i]
        prev_sma = df["MA_Signal"].iloc[i-1]
        
        upper = df["BB_Upper"].iloc[i]
        lower = df["BB_Lower"].iloc[i]

        signal_code = 0
        days_since_action += 1

        # ==========================================================
        # 交易邏輯 (優先級調整：先檢查是否要抄底，再檢查是否要停損)
        # ==========================================================

        # 1. 【霸王條款】跌破布林下軌 -> 買進 (Buy on Dip)
        # 不管現在是不是在均線下，只要超跌就買
        if price < lower:
            if days_since_action >= action_interval:
                current_pos += (action_pct / 100.0)
                if current_pos > 1.0: current_pos = 1.0
                signal_code = 2 # Buy Signal
                days_since_action = 0
            # 若間隔未到，保持原倉位 (不會被下面的 Clear 清掉，因為用了 if-elif 結構)

        # 2. 站上均線 -> All In (Trend Following)
        elif price > sma and prev_price <= prev_sma:
            current_pos = 1.0
            signal_code = 1 # All In
            days_since_action = 0

        # 3. 漲破布林上軌 -> 減碼 (Take Profit)
        elif price > upper and current_pos > 0:
            if days_since_action >= action_interval:
                current_pos -= (action_pct / 100.0)
                if current_pos < 0.0: current_pos = 0.0
                signal_code = -2 # Sell Signal
                days_since_action = 0

        # 4. 跌破均線 (且沒跌破下軌) -> 清空 (Stop Loss)
        # 這是 "灰色地帶"： Lower < Price < SMA
        elif price < sma:
            current_pos = 0.0
            signal_code = -1 # Clear Signal
            days_since_action = 0

        # 5. 其他情況 (如 Price > SMA 但沒破上軌) -> 續抱
        else:
            pass
        
        positions[i] = round(current_pos, 4)
        executed_signals[i] = signal_code

    df["Signal"] = executed_signals
    df["Position"] = positions

    # ###############################################################
    # 資金曲線計算
    # ###############################################################

    equity_lrs = [1.0]
    
    for i in range(1, len(df)):
        pos_weight = df["Position"].iloc[i-1]
        lev_ret = df["Return_lev"].iloc[i]
        new_equity = equity_lrs[-1] * (1 + (lev_ret * pos_weight))
        equity_lrs.append(new_equity)

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)

    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    df["Pct_Base"] = df["Equity_BH_Base"] - 1
    df["Pct_Lev"] = df["Equity_BH_Lev"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    # 篩選訊號點位
    sig_all_in = df[df["Signal"] == 1]
    sig_clear  = df[df["Signal"] == -1]
    sig_buy_bb = df[df["Signal"] == 2]
    sig_sell_bb = df[df["Signal"] == -2]

    # ###############################################################
    # 指標計算
    # ###############################################################

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

    # ###############################################################
    # 圖表 + KPI + 表格
    # ###############################################################

    st.markdown("<h3>📌 策略訊號與布林通道 (原型ETF)</h3>", unsafe_allow_html=True)
        fig_price = go.Figure()

    # 1. 原型價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price_base"], name=f"{base_label}", 
        mode="lines", line=dict(width=2, color="#636EFA"),
    ))

    # 2. SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Signal"], name=f"{sma_window} SMA", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
    ))

    # 4. 布林通道 (上/下)
    fig_price.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], name=f"布林通道 (±{bb_std_dev}σ)", 
        mode="lines", line=dict(width=0), fill='tonexty', fillcolor='rgba(128,128,128,0.1)'
    ))

    # 5. 訊號標記
    if not sig_all_in.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_all_in.index, y=sig_all_in["Price_base"], mode="markers", name="All In (站上均線)", 
            marker=dict(color="#00C853", size=12, symbol="star", line=dict(width=1, color="white"))
        ))
    if not sig_clear.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_clear.index, y=sig_clear["Price_base"], mode="markers", name="清空 (跌破均線)", 
            marker=dict(color="#D50000", size=10, symbol="x", line=dict(width=1, color="white"))
        ))
    if not sig_buy_bb.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_buy_bb.index, y=sig_buy_bb["Price_base"], mode="markers", name=f"抄底加碼 ({action_pct}%)", 
            marker=dict(color="#66BB6A", size=8, symbol="triangle-up")
        ))
    if not sig_sell_bb.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_sell_bb.index, y=sig_sell_bb["Price_base"], mode="markers", name=f"高檔減碼 ({action_pct}%)", 
            marker=dict(color="#FFA726", size=8, symbol="triangle-down")
        ))

    fig_price.update_layout(
        template="plotly_white", height=500, hovermode="x unified",
        yaxis=dict(title=f"價格", showgrid=True),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # --- 資金曲線 ---
    st.markdown("<h3>📊 資金曲線比較</h3>", unsafe_allow_html=True)
    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型BH"))
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name="槓桿BH"))
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS+BB動態", line=dict(width=2.5)))
    fig_equity.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".0%"))
    st.plotly_chart(fig_equity, use_container_width=True)

    # --- KPI 表格 ---
    asset_gap_lrs_vs_lev = ((capital_lrs_final / capital_lev_final) - 1) * 100
    cagr_gap_lrs_vs_lev = (cagr_lrs - cagr_lev) * 100
    vol_gap_lrs_vs_lev = (vol_lrs - vol_lev) * 100
    mdd_gap_lrs_vs_lev = (mdd_lrs - mdd_lev) * 100

    st.markdown("""<style>.kpi-card {background-color: var(--secondary-background-color); border-radius: 16px; padding: 24px 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1); display:flex; flex-direction:column; justify-content:space-between; height:100%;} .kpi-value {font-size:2.2rem; font-weight:900; margin-bottom:16px;} .delta-positive{background-color:rgba(33,195,84,0.12); color:#21c354; padding:6px 12px; border-radius:20px; font-weight:700; width:fit-content;} .delta-negative{background-color:rgba(255,60,60,0.12); color:#ff3c3c; padding:6px 12px; border-radius:20px; font-weight:700; width:fit-content;} .delta-neutral{background-color:rgba(128,128,128,0.1); color:gray; padding:6px 12px; border-radius:20px; width:fit-content;}</style>""", unsafe_allow_html=True)

    def kpi_html(lbl, val, gap):
        cls = "delta-positive" if gap > 0 else "delta-negative" if gap < 0 else "delta-neutral"
        sign = "+" if gap > 0 else ""
        return f"""<div class="kpi-card"><div style="opacity:0.7; font-weight:500; margin-bottom:8px;">{lbl}</div><div class="kpi-value">{val}</div><div class="{cls}">{sign}{gap:.2f}% (vs 槓桿)</div></div>"""

    rk = st.columns(4)
    with rk[0]: st.markdown(kpi_html("期末資產", fmt_money(capital_lrs_final), asset_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[1]: st.markdown(kpi_html("CAGR", fmt_pct(cagr_lrs), cagr_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[2]: st.markdown(kpi_html("波動率", fmt_pct(vol_lrs), vol_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[3]: st.markdown(kpi_html("最大回撤", fmt_pct(mdd_lrs), mdd_gap_lrs_vs_lev), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 最終表格
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>LRS+BB動態</span>": {
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
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": capital_lev_final,
            "總報酬率": final_ret_lev,
            "CAGR (年化)": cagr_lev,
            "Calmar Ratio": calmar_lev,
            "最大回撤 (MDD)": mdd_lev,
            "年化波動": vol_lev,
            "Sharpe Ratio": sharpe_lev,
            "Sortino Ratio": sortino_lev,
            "交易次數": -1, 
        }
    }

    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)
    
    metrics_config = {
        "期末資產":       {"fmt": fmt_money, "invert": False},
        "總報酬率":       {"fmt": fmt_pct,   "invert": False},
        "CAGR (年化)":    {"fmt": fmt_pct,   "invert": False},
        "Calmar Ratio":   {"fmt": fmt_num,   "invert": False},
        "最大回撤 (MDD)": {"fmt": fmt_pct,   "invert": True},
        "年化波動":       {"fmt": fmt_pct,   "invert": True},
        "Sharpe Ratio":   {"fmt": fmt_num,   "invert": False},
        "Sortino Ratio":  {"fmt": fmt_num,   "invert": False},
        "交易次數":       {"fmt": lambda x: fmt_int(x) if x >= 0 else "—", "invert": True} 
    }
    
    html_code = """
    <style>
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); font-family: 'Noto Sans TC', sans-serif; margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); color: var(--text-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.metric-name { background-color: transparent; color: var(--text-color); font-weight: 500; text-align: left; padding: 12px 16px; width: 25%; font-size: 0.9rem; border-bottom: 1px solid rgba(128,128,128, 0.1); opacity: 0.9; }
        .comparison-table td.data-cell { text-align: center; padding: 12px; color: var(--text-color); border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.lrs-col { background-color: rgba(128, 128, 128, 0.03); }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255, 215, 0, 0.4); }
        .comparison-table tr:hover td { background-color: rgba(128,128,128, 0.05); }
    </style>
    <table class="comparison-table">
        <thead><tr><th style="text-align:left; padding-left:16px; width:25%;">指標</th>
    """
    for col_name in df_vertical.columns: html_code += f"<th>{col_name}</th>"
    html_code += "</tr></thead><tbody>"

    for metric in df_vertical.index:
        config = metrics_config.get(metric, {"fmt": fmt_num, "invert": False})
        raw_row_values = df_vertical.loc[metric].values
        valid_values = [x for x in raw_row_values if isinstance(x, (int, float)) and x != -1 and not pd.isna(x)]
        target_val = None
        if valid_values and metric != "交易次數": 
            target_val = min(valid_values) if config["invert"] else max(valid_values)

        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        for i, strategy in enumerate(df_vertical.columns):
            val = df_vertical.at[metric, strategy]
            display_text = config["fmt"](val) if isinstance(val, (int, float)) and val != -1 else "—"
            is_winner = target_val is not None and isinstance(val, (int, float)) and val == target_val
            if is_winner: display_text += " <span class='trophy-icon'>🏆</span>"
            is_lrs = (i == 0)
            lrs_class = "lrs-col" if is_lrs else ""
            font_weight = "bold" if is_lrs else "normal"
            html_code += f"<td class='data-cell {lrs_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        html_code += "</tr>"
    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)
