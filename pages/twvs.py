###############################################################
# app.py — 正2 直球對決 + 布林通道調節 (參數分離版 - 修正SyntaxError)
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
    page_title="正2 布林動態策略",
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
    "<h1 style='margin-bottom:0.5em;'>⚡ 正2 布林動態調節 (直球對決版)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>策略邏輯 (直接使用正2均線)：</b><br>
1️⃣ <b>抄底 (最高優先)</b>：收盤 < 布林下軌 (-2σ) ⮕ <span style='color:#66BB6A'><b>買進加碼</b></span>。<br>
2️⃣ <b>進場</b>：漲破 200SMA ⮕ <span style='color:#4CAF50'><b>All In (100%)</b></span>。<br>
3️⃣ <b>獲利調節</b>：收盤 > 布林上軌 (2σ) ⮕ <span style='color:#FFA726'><b>賣出減碼</b></span>。<br>
4️⃣ <b>停損</b>：<b>剛跌破 200SMA 瞬間</b> ⮕ <span style='color:#FF5252'><b>清空 (0%)</b></span> (若已在線下則不再清空，保留抄底部位)。<br>
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

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

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
    sma_window = st.number_input("均線週期 (SMA)", min_value=10, max_value=240, value=200, step=10)

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 策略參數設定")

col_bb1, col_bb2 = st.columns(2)

with col_bb1:
    st.markdown("#### 🌊 布林通道設定")
    bb_std_dev = st.number_input("布林通道倍數 (σ)", min_value=1.0, max_value=4.0, value=2.0, step=0.1, help="設定通道寬度，通常為 2.0")
    st.caption("ℹ️ 訊號直接來自正2價格")
    
with col_bb2:
    st.markdown("#### ⚖️ 加減碼規則")
    action_pct = st.number_input("單次加/減碼比例 (%)", min_value=5, max_value=50, value=10, step=5)
    
    c1, c2 = st.columns(2)
    with c1:
        add_interval = st.number_input("加碼間隔天數", min_value=1, max_value=30, value=3, help="跌破下軌後的買進冷卻時間")
    with c2:
        reduce_interval = st.number_input("減碼間隔天數", min_value=1, max_value=30, value=5, help="漲破上軌後的賣出冷卻時間")

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60) 

    with st.spinner("讀取 CSV 中…"):
        df_raw = load_csv(lev_symbol)

    if df_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
        st.stop()

    df_raw = df_raw.loc[start_early:end]

    df = pd.DataFrame(index=df_raw.index)
    df["Price"] = df_raw["Price"] # 單一價格來源
    df = df.sort_index()

    # 1. 計算技術指標 (直接用正2算)
    df["MA_Signal"] = df["Price"].rolling(sma_window).mean()
    df["Std_Dev"] = df["Price"].rolling(sma_window).std()
    
    # 布林通道
    df["BB_Upper"] = df["MA_Signal"] + (bb_std_dev * df["Std_Dev"])
    df["BB_Lower"] = df["MA_Signal"] - (bb_std_dev * df["Std_Dev"])

    df = df.dropna(subset=["MA_Signal", "BB_Upper"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return"] = df["Price"].pct_change().fillna(0)

    # ###############################################################
    # 核心交易邏輯
    # ###############################################################

    executed_signals = [0] * len(df)  # 記錄訊號
    positions = [0.0] * len(df)       # 記錄持倉比例
    
    # 初始狀態
    current_pos = 0.0 
    days_since_add = 999 
    days_since_reduce = 999

    # 如果第一天價格就在均線上，給予初始倉位
    if df["Price"].iloc[0] > df["MA_Signal"].iloc[0]:
        current_pos = 1.0

    positions[0] = current_pos

    for i in range(1, len(df)):
        price = df["Price"].iloc[i]
        prev_price = df["Price"].iloc[i-1]
        
        sma = df["MA_Signal"].iloc[i]
        prev_sma = df["MA_Signal"].iloc[i-1]
        
        upper = df["BB_Upper"].iloc[i]
        lower = df["BB_Lower"].iloc[i]

        signal_code = 0
        days_since_add += 1
        days_since_reduce += 1

        # ==========================================================
        # 交易邏輯
        # ==========================================================

        # 1. 【霸王條款】跌破布林下軌 -> 買進 (Buy on Dip)
        if price < lower:
            if days_since_add >= add_interval:
                current_pos += (action_pct / 100.0)
                if current_pos > 1.0: current_pos = 1.0
                signal_code = 2 # Buy Signal
                days_since_add = 0

        # 2. 站上均線 -> All In (Trend Following)
        elif price > sma and prev_price <= prev_sma:
            current_pos = 1.0
            signal_code = 1 # All In
            # 這裡不重置 add/reduce 計數，讓它們獨立運作比較合理

        # 3. 漲破布林上軌 -> 減碼 (Take Profit)
        elif price > upper and current_pos > 0:
            if days_since_reduce >= reduce_interval:
                current_pos -= (action_pct / 100.0)
                if current_pos < 0.0: current_pos = 0.0
                signal_code = -2 # Sell Signal
                days_since_reduce = 0

        # 4. 剛跌破均線 -> 清空 (Stop Loss)
        # 關鍵：只在跌破瞬間執行
        elif price < sma and prev_price >= prev_sma:
            if current_pos > 0: 
                current_pos = 0.0
                signal_code = -1 # Clear Signal
                # 這裡不需要重置間隔計數，因為清空是最高指導原則

        # 5. 其他情況：續抱
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
        lev_ret = df["Return"].iloc[i]
        new_equity = equity_lrs[-1] * (1 + (lev_ret * pos_weight))
        equity_lrs.append(new_equity)

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)

    # Buy & Hold (就是正2本身)
    df["Equity_BH"] = (1 + df["Return"]).cumprod()

    df["Pct_BH"] = df["Equity_BH"] - 1
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
    eq_bh_final, final_ret_bh, cagr_bh, mdd_bh, vol_bh, sharpe_bh, sortino_bh, calmar_bh = calc_core(
        df["Equity_BH"], df["Return"]
    )

    capital_lrs_final = eq_lrs_final * capital
    capital_bh_final = eq_bh_final * capital
    
    trade_count_lrs = int((df["Signal"] != 0).sum())

    # ###############################################################
    # 圖表 + KPI + 表格
    # ###############################################################

    st.markdown(f"<h3>📌 {lev_label} 策略執行圖</h3>", unsafe_allow_html=True)
    
    fig_price = go.Figure()

    # 1. 價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price"], name=f"{lev_label}", 
        mode="lines", line=dict(width=2, color="#636EFA"),
    ))

    # 2. SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Signal"], name=f"{sma_window} SMA", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
    ))

    # 3. 布林通道
    fig_price.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], name=f"布林通道 (±{bb_std_dev}σ)", 
        mode="lines", line=dict(width=0), fill='tonexty', fillcolor='rgba(128,128,128,0.1)'
    ))

    # 4. 訊號
    if not sig_all_in.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_all_in.index, y=sig_all_in["Price"], mode="markers", name="All In (站上均線)", 
            marker=dict(color="#00C853", size=12, symbol="star", line=dict(width=1, color="white"))
        ))
    if not sig_clear.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_clear.index, y=sig_clear["Price"], mode="markers", name="清空 (剛跌破)", 
            marker=dict(color="#D50000", size=10, symbol="x", line=dict(width=1, color="white"))
        ))
    if not sig_buy_bb.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_buy_bb.index, y=sig_buy_bb["Price"], mode="markers", name=f"抄底加碼 ({action_pct}%)", 
            marker=dict(color="#66BB6A", size=8, symbol="triangle-up")
        ))
    if not sig_sell_bb.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_sell_bb.index, y=sig_sell_bb["Price"], mode="markers", name=f"高檔減碼 ({action_pct}%)", 
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
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_BH"], mode="lines", name=f"{lev_label} (Buy&Hold)"))
    fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS+BB動態", line=dict(width=2.5)))
    fig_equity.update_layout(template="plotly_white", height=450, yaxis=dict(tickformat=".0%"))
    st.plotly_chart(fig_equity, use_container_width=True)

    # --- KPI 表格 ---
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
