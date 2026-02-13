###############################################################
# app.py — 正2 趨勢跟隨 + 布林移動停損 (Trend + Trailing Stop)
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
    page_title="正2 趨勢 + 移動停損策略",
    page_icon="⚡",
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
    "<h1 style='margin-bottom:0.5em;'>⚡ 正2 趨勢跟隨 + 布林移動停損</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>策略邏輯：</b><br>
1️⃣ <b>進場 (趨勢)</b>：<span style='color:#2962FF'><b>收盤價</b></span> 站上 200SMA ⮕ <span style='color:#4CAF50'><b>買進 (100%)</b></span>。<br>
2️⃣ <b>離場 (趨勢)</b>：<span style='color:#2962FF'><b>收盤價</b></span> 跌破 200SMA ⮕ <span style='color:#FF5252'><b>賣出清空</b></span>。<br>
3️⃣ <b>動態停損 (獲利保護)</b>：當價格突破 <span style='color:#FFA726'><b>布林上軌</b></span> 時啟動監控，若從波段高點回檔 <span style='color:#FF5252'><b>超過 X%</b></span> ⮕ <b>提早獲利了結</b>。<br>
<small>💡 優點：平時跟隨大趨勢，遇到瘋狂急漲時，利用布林通道啟動保護機制，避免獲利大幅回吐。</small>
""",
    unsafe_allow_html=True,
)

###############################################################
# ETF 名稱清單 (只保留槓桿)
###############################################################

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


def get_full_range_from_csv(symbol: str):
    df = load_csv(symbol)
    if df.empty:
        return dt.date(2012, 1, 1), dt.date.today()
    return df.index.min().date(), df.index.max().date()

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

###############################################################
# UI 輸入
###############################################################

col_sel, col_info = st.columns([1, 2])
with col_sel:
    lev_label = st.selectbox("選擇交易標的 (兼訊號源)", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(lev_symbol)
with col_info:
    st.info(f"📌 資料區間：{s_min} ~ {s_max}")

# 基本參數
col3, col4, col5, col6 = st.columns(4)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)
with col6:
    sma_window = st.number_input("長線趨勢 (SMA)", min_value=10, max_value=240, value=200, step=10)

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 策略參數設定")

col_bb_set, col_stop_set = st.columns(2)

with col_bb_set:
    st.markdown("#### 🌊 布林通道 (啟動條件)")
    bb_std_dev = st.number_input("通道倍數 (σ)", value=2.0, step=0.1, help="當價格超過上軌時，開始啟動移動停損監控")

with col_stop_set:
    st.markdown("#### 🛡️ 移動停損 (出場條件)")
    trailing_stop_pct = st.number_input("高點回檔賣出 (%)", value=10.0, step=1.0, help="啟動監控後，若價格從波段最高點下跌超過此幅度，則獲利了結")

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5)) 

    with st.spinner("讀取 CSV 中…"):
        df_raw = load_csv(lev_symbol)

    if df_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
        st.stop()

    df_raw = df_raw.loc[start_early:end]

    df = pd.DataFrame(index=df_raw.index)
    df["Price"] = df_raw["Price"]
    df = df.sort_index()

    # 1. 計算技術指標
    df["MA_Long"] = df["Price"].rolling(sma_window).mean()
    df["Std_Dev"] = df["Price"].rolling(sma_window).std()
    
    # 布林通道
    df["BB_Upper"] = df["MA_Long"] + (bb_std_dev * df["Std_Dev"])
    df["BB_Lower"] = df["MA_Long"] - (bb_std_dev * df["Std_Dev"])

    df = df.dropna(subset=["MA_Long", "BB_Upper"])
    df = df.loc[start:end]
    
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return"] = df["Price"].pct_change().fillna(0)

    # ###############################################################
    # 核心交易邏輯 (State Machine)
    # ###############################################################

    executed_signals = [0] * len(df)
    positions = [0.0] * len(df)
    stop_lines = [np.nan] * len(df) # 用於畫圖：移動停損線
    
    # 狀態變數
    current_pos = 0.0 
    trailing_mode = False     # 是否處於移動停損監控模式
    peak_price = 0.0          # 監控期間的最高價

    # 初始判斷 (第一天)
    if df["Price"].iloc[0] > df["MA_Long"].iloc[0]:
        current_pos = 1.0

    positions[0] = current_pos

    for i in range(1, len(df)):
        price = df["Price"].iloc[i]
        sma = df["MA_Long"].iloc[i]
        upper = df["BB_Upper"].iloc[i]
        
        signal_code = 0
        
        # 邏輯核心：
        # 1. 先判斷是否持有 (Hold)
        if current_pos > 0:
            
            # --- 出場條件檢查 ---
            
            # A. 趨勢反轉 (優先)：跌破 SMA -> 賣出
            if price < sma:
                current_pos = 0.0
                signal_code = -1 # Sell (Trend Break)
                trailing_mode = False # 重置監控
                peak_price = 0.0
            
            # B. 移動停損 (Trailing Stop)
            elif trailing_mode:
                # 更新波段最高價
                if price > peak_price:
                    peak_price = price
                
                # 計算當前的停損價位
                current_stop_price = peak_price * (1 - trailing_stop_pct / 100.0)
                stop_lines[i] = current_stop_price # 記錄下來畫圖用

                # 觸發停損
                if price < current_stop_price:
                    current_pos = 0.0
                    signal_code = -2 # Sell (Trailing Stop Hit)
                    trailing_mode = False
                    peak_price = 0.0
            
            # --- 狀態更新 ---
            # C. 檢查是否觸發布林上軌 (開啟監控模式)
            # 注意：如果已經在 trailing_mode，就繼續保持
            if current_pos > 0 and not trailing_mode:
                if price > upper:
                    trailing_mode = True
                    peak_price = price
                    # 設定當下的停損線供參考
                    stop_lines[i] = peak_price * (1 - trailing_stop_pct / 100.0)

        else:
            # --- 進場條件檢查 ---
            # 當前空手，檢查是否站上 SMA
            if price > sma:
                current_pos = 1.0
                signal_code = 1 # Buy
                trailing_mode = False # 剛買進，重置監控
                peak_price = 0.0

        positions[i] = current_pos
        executed_signals[i] = signal_code

    df["Signal"] = executed_signals
    df["Position"] = positions
    df["Stop_Line_Trace"] = stop_lines

    # ###############################################################
    # 資金曲線計算
    # ###############################################################

    equity_lrs = [1.0]
    
    for i in range(1, len(df)):
        pos_weight = df["Position"].iloc[i-1]
        lev_ret = df["Return"].iloc[i]
        new_equity = equity_lrs[-1] * (1 + (lev_ret * pos_weight))
        equity_lrs.append(new_equity)

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH"] = (1 + df["Return"]).cumprod()
    df["Pct_BH"] = df["Equity_BH"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    # 篩選訊號點位
    sig_buy = df[df["Signal"] == 1]
    sig_sell_trend = df[df["Signal"] == -1]
    sig_sell_trail = df[df["Signal"] == -2]

    # ###############################################################
    # 統計指標
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
    eq_bh_final, final_ret_bh, cagr_bh, mdd_bh, vol_bh, sharpe_bh, sortino_bh, calmar_bh = calc_core(
        df["Equity_BH"], df["Return"]
    )

    capital_lrs_final = eq_lrs_final * capital
    capital_bh_final = eq_bh_final * capital
    trade_count_lrs = int((df["Signal"] != 0).sum())

    # ###############################################################
    # 視覺化
    # ###############################################################

    st.markdown(f"<h3>📌 {lev_label} 策略執行圖</h3>", unsafe_allow_html=True)
    
    fig_price = go.Figure()

    # 1. 價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price"], name=f"{lev_label} 收盤價", 
        mode="lines", line=dict(width=1, color="rgba(99, 110, 250, 0.4)"),
    ))

    # 2. SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Long"], name=f"趨勢線 ({sma_window}SMA)", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
    ))

    # 3. 布林通道
    fig_price.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], name=f"布林通道 (±{bb_std_dev}σ)", 
        mode="lines", line=dict(width=0), fill='tonexty', fillcolor='rgba(128,128,128,0.1)'
    ))

    # 🌟 4. 動態停損線 (只在監控模式下顯示)
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Stop_Line_Trace"], name="移動停損線", 
        mode="lines", line=dict(width=2, color="#FF5252", dash="dot"),
        connectgaps=False # 不連線，斷開顯示
    ))

    # 5. 標記
    if not sig_buy.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_buy.index, y=sig_buy["Price"], mode="markers", name="買進 (站上SMA)", 
            marker=dict(color="#00C853", size=10, symbol="triangle-up", line=dict(width=1, color="white"))
        ))
    if not sig_sell_trend.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_sell_trend.index, y=sig_sell_trend["Price"], mode="markers", name="賣出 (跌破SMA)", 
            marker=dict(color="#757575", size=10, symbol="x", line=dict(width=1, color="white"))
        ))
    if not sig_sell_trail.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_sell_trail.index, y=sig_sell_trail["Price"], mode="markers", name="停利 (移動停損)", 
            marker=dict(color="#FF5252", size=10, symbol="star", line=dict(width=1, color="white"))
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
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_BH"], mode="lines", name=f"{lev_label} (Buy&Hold)"))
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="策略執行結果", line=dict(width=2.5)))
    fig_equity.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".0%"))
    st.plotly_chart(fig_equity, use_container_width=True)

    # --- KPI 區塊 (保持不變) ---
    asset_gap = ((capital_lrs_final / capital_bh_final) - 1) * 100
    cagr_gap = (cagr_lrs - cagr_bh) * 100
    vol_gap = (vol_lrs - vol_bh) * 100
    mdd_gap = (mdd_lrs - mdd_bh) * 100

    st.markdown("""<style>.kpi-card {background-color: var(--secondary-background-color); border-radius: 16px; padding: 24px 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1); display:flex; flex-direction:column; justify-content:space-between; height:100%;} .kpi-value {font-size:2.2rem; font-weight:900; margin-bottom:16px;} .delta-positive{background-color:rgba(33,195,84,0.12); color:#21c354; padding:6px 12px; border-radius:20px; font-weight:700; width:fit-content;} .delta-negative{background-color:rgba(255,60,60,0.12); color:#ff3c3c; padding:6px 12px; border-radius:20px; font-weight:700; width:fit-content;} .delta-neutral{background-color:rgba(128,128,128,0.1); color:gray; padding:6px 12px; border-radius:20px; width:fit-content;}</style>""", unsafe_allow_html=True)

    def kpi_html(lbl, val, gap):
        cls = "delta-positive" if gap > 0 else "delta-negative" if gap < 0 else "delta-neutral"
        sign = "+" if gap > 0 else ""
        return f"""<div class="kpi-card"><div style="opacity:0.7; font-weight:500; margin-bottom:8px;">{lbl}</div><div class="kpi-value">{val}</div><div class="{cls}">{sign}{gap:.2f}% (vs B&H)</div></div>"""

    rk = st.columns(4)
    with rk[0]: st.markdown(kpi_html("期末資產", fmt_money(capital_lrs_final), asset_gap), unsafe_allow_html=True)
    with rk[1]: st.markdown(kpi_html("CAGR", fmt_pct(cagr_lrs), cagr_gap), unsafe_allow_html=True)
    with rk[2]: st.markdown(kpi_html("波動率", fmt_pct(vol_lrs), vol_gap), unsafe_allow_html=True)
    with rk[3]: st.markdown(kpi_html("最大回撤", fmt_pct(mdd_lrs), mdd_gap), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 最終表格
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>策略 (SMA+Stop)</span>": {
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
            "期末資產": capital_bh_final,
            "總報酬率": final_ret_bh,
            "CAGR (年化)": cagr_bh,
            "Calmar Ratio": calmar_bh,
            "最大回撤 (MDD)": mdd_bh,
            "年化波動": vol_bh,
            "Sharpe Ratio": sharpe_bh,
            "Sortino Ratio": sortino_bh,
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
