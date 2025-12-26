###############################################################
# app.py — 槓桿 ETF 策略 (SMA + 布林通道濾網版)
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
    page_title="正2 LRS + 布林通道回測",
    page_icon="📈",
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
    "<h1 style='margin-bottom:0.5em;'>📊 槓桿 ETF 動態策略 (布林通道濾網)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較兩種策略：</b><br>
1️⃣ <b>槓桿 ETF Buy & Hold</b>：買進後一路持有。<br>
2️⃣ <b>LRS + DCA + 布林通道濾網</b>：<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <b>買進</b>：突破 SMA 均線。<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <b>賣出</b>：可選擇「跌破緩衝線」或更進階的「跌破布林下通道」以過濾假跌破。<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <b>DCA</b>：賣出後可選擇定期定額買回。
""",
    unsafe_allow_html=True,
)

###############################################################
# ETF 名稱清單
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
    lev_label = st.selectbox("選擇交易標的 (同時作為訊號源)", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(lev_symbol)
with col_info:
    st.info(f"📌 資料區間：{s_min} ~ {s_max}")

# 基本參數
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
    capital = st.number_input("投入本金（元）", 1000, 5_000_000, 100_000, step=10_000)
with col6:
    sma_window = st.number_input("均線週期 (SMA)", min_value=10, max_value=240, value=200, step=10)

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 策略進階設定 (含布林通道)")

col_mode, col_bb, col_dca = st.columns([1, 1, 1])

with col_mode:
    position_mode = st.radio(
        "策略初始狀態",
        [ "一開始就全倉","空手起跑"],
        index=0,
    )
    st.write("") # Spacer

with col_bb:
    st.markdown("#### 🛡️ 賣出條件與濾網")
    use_bb_stop = st.toggle("使用「布林下通道」作為停損", value=False, help="若開啟，賣出訊號將依據價格是否跌破「SMA - N倍標準差」。這通常比單純跌破均線更能過濾假跌破。")
    
    if use_bb_stop:
        bb_std_dev = st.number_input("布林通道標準差 (StdDev)", min_value=1.0, max_value=4.0, value=2.0, step=0.1, help="通常設定為 2.0 或 2.5。數值越大通道越寬，越不容易被洗出場，但也越慢賣出。")
        sell_threshold_pct = 0.0 # 停用固定 %
    else:
        bb_std_dev = 2.0 # 預設計算用，但不影響策略
        sell_threshold_pct = st.number_input(
            "跌破 SMA 緩衝 (%)", 
            min_value=0.0, max_value=20.0, value=0.0, step=0.5,
            help="傳統模式：設定收盤價跌破均線多少 % 才賣出。"
        )

with col_dca:
    st.markdown("#### 💰 DCA 加碼設定")
    enable_dca = st.toggle("啟用 DCA 定期定額", value=False)
    dca_interval = st.number_input("買進間隔天數", min_value=1, max_value=60, value=3, disabled=not enable_dca)
    dca_pct = st.number_input("每次買進比例 (%)", min_value=1, max_value=100, value=10, step=5, disabled=not enable_dca)


###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60) # 動態緩衝

    with st.spinner("讀取 CSV 中…"):
        df_raw = load_csv(lev_symbol)

    if df_raw.empty:
        st.error(f"⚠️ 資料讀取失敗，請確認 data/{lev_symbol}.csv 是否存在")
        st.stop()

    df_raw = df_raw.loc[start_early:end]
    
    # 建立主 DataFrame
    df = pd.DataFrame(index=df_raw.index)
    df["Price"] = df_raw["Price"]
    df = df.sort_index()

    # 計算指標
    # 1. SMA (中軌)
    df["MA_Signal"] = df["Price"].rolling(sma_window).mean()
    
    # 2. 布林通道 (SMA +/- StdDev)
    df["Rolling_Std"] = df["Price"].rolling(sma_window).std()
    df["BB_Upper"] = df["MA_Signal"] + (bb_std_dev * df["Rolling_Std"])
    df["BB_Lower"] = df["MA_Signal"] - (bb_std_dev * df["Rolling_Std"])
    
    # 3. 決定「賣出線 (Sell Threshold)」
    if use_bb_stop:
        df["Sell_Threshold"] = df["BB_Lower"]
    else:
        df["Sell_Threshold"] = df["MA_Signal"] * (1 - sell_threshold_pct / 100.0)

    df = df.dropna(subset=["MA_Signal", "BB_Lower"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return"] = df["Price"].pct_change().fillna(0)

    ###############################################################
    # 策略邏輯
    ###############################################################

    executed_signals = [0] * len(df)
    positions = [0.0] * len(df)

    if "全倉" in position_mode:
        current_pos = 1.0
        can_buy_permission = True
    else:
        current_pos = 0.0
        can_buy_permission = False 
    
    positions[0] = current_pos
    dca_wait_counter = 0 

    for i in range(1, len(df)):
        p = df["Price"].iloc[i]
        m = df["MA_Signal"].iloc[i]
        threshold = df["Sell_Threshold"].iloc[i]

        # 狀態判斷
        # 買進：看的是是否「站上均線」(趨勢轉強)
        is_breakout = p > m          
        
        # 賣出：看的是是否「跌破賣出線」(根據設定可能是均線緩衝 或 布林下軌)
        is_breakdown = p < threshold 
        
        daily_signal = 0

        # === 狀況 1: 價格在均線上 (強勢區) ===
        if is_breakout:
            if can_buy_permission:
                if current_pos < 1.0: 
                    daily_signal = 1 
                current_pos = 1.0
            else:
                # 空手起跑中，尚未等到第一次跌破後的重置
                current_pos = 0.0
            
            dca_wait_counter = 0

        # === 狀況 2: 跌破賣出線 (弱勢區) ===
        elif is_breakdown:
            can_buy_permission = True # 解鎖權限
            
            if current_pos >= 1.0: 
                # 滿倉 -> 清倉
                current_pos = 0.0
                daily_signal = -1
                dca_wait_counter = 0
            else:
                # 已經賣出，檢查 DCA
                if enable_dca:
                    dca_wait_counter += 1
                    if dca_wait_counter >= dca_interval:
                        current_pos += (dca_pct / 100.0)
                        if current_pos > 1.0: 
                            current_pos = 1.0 
                        daily_signal = 2
                        dca_wait_counter = 0
                else:
                    current_pos = 0.0

        # === 狀況 3: 灰色地帶 (SMA 與 下軌/緩衝線 之間) ===
        else:
            # Hysteresis (遲滯區間)：維持原狀
            if current_pos >= 1.0:
                pass # 續抱
            else:
                # 視為尚未突破均線，繼續 DCA 邏輯
                if enable_dca:
                    dca_wait_counter += 1
                    if dca_wait_counter >= dca_interval:
                        current_pos += (dca_pct / 100.0)
                        if current_pos > 1.0: current_pos = 1.0
                        daily_signal = 2
                        dca_wait_counter = 0
                else:
                    pass

        executed_signals[i] = daily_signal
        positions[i] = round(current_pos, 4) 

    df["Signal"] = executed_signals
    df["Position"] = positions

    ###############################################################
    # 資金曲線
    ###############################################################

    equity_lrs = [1.0]
    
    for i in range(1, len(df)):
        pos_weight = df["Position"].iloc[i-1]
        lev_ret = df["Return"].iloc[i]
        new_equity = equity_lrs[-1] * (1 + (lev_ret * pos_weight))
        equity_lrs.append(new_equity)

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)

    # Buy & Hold
    df["Equity_BH"] = (1 + df["Return"]).cumprod()

    df["Pct_BH"] = df["Equity_BH"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    # 篩選訊號
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    dca_buys = df[df["Signal"] == 2]

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
    eq_bh_final, final_ret_bh, cagr_bh, mdd_bh, vol_bh, sharpe_bh, sortino_bh, calmar_bh = calc_core(
        df["Equity_BH"], df["Return"]
    )

    capital_lrs_final = eq_lrs_final * capital
    capital_bh_final = eq_bh_final * capital
    trade_count_lrs = int((df["Signal"] != 0).sum())

    ###############################################################
    # 圖表 + KPI
    ###############################################################

    st.markdown("<h3>📌 策略訊號與布林通道</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    # 1. 價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price"], name=f"{lev_label}", 
        mode="lines", line=dict(width=2, color="#00CC96"),
        hovertemplate=f"<b>{lev_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 2. SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Signal"], name=f"{sma_window} 日 SMA", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
        hovertemplate=f"<b>{sma_window}SMA</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 3. 布林通道 (上軌 - 隱藏)
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Upper"], 
        mode="lines", line=dict(width=0), showlegend=False, hoverinfo='skip'
    ))

    # 4. 布林通道 (下軌 + 填滿)
    fill_color = "rgba(128, 128, 128, 0.15)"
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], name=f"布林通道 (±{bb_std_dev}σ)",
        mode="lines", line=dict(width=1, color="rgba(128, 128, 128, 0.5)", dash='dot'),
        fill='tonexty', fillcolor=fill_color,
        hovertemplate=f"<b>布林下軌</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))
    
    # 若目前是使用固定%數緩衝，為了比較，也可以把緩衝線畫出來 (選配)
    if not use_bb_stop and sell_threshold_pct > 0:
         fig_price.add_trace(go.Scatter(
            x=df.index, y=df["Sell_Threshold"], name=f"賣出線 (緩衝{sell_threshold_pct}%)", 
            mode="lines", line=dict(width=1, color="#FF5722", dash='dot'),
            hovertemplate=f"<b>緩衝賣出線</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
        ))

    # 標記
    if not buys.empty:
        buy_hover = [f"<b>▲ 買進 (站上均線)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(buys.index, buys["Price"])]
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price"], mode="markers", name="全倉買進", 
            marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=buy_hover
        ))

    if not sells.empty:
        reason = "跌破布林下軌" if use_bb_stop else "跌破緩衝線"
        sell_hover = [f"<b>▼ 賣出 ({reason})</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(sells.index, sells["Price"])]
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price"], mode="markers", name="清倉賣出", 
            marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=sell_hover
        ))

    if not dca_buys.empty:
        dca_hover = [f"<b>● DCA 加碼 ({dca_pct}%)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(dca_buys.index, dca_buys["Price"])]
        fig_price.add_trace(go.Scatter(
            x=dca_buys.index, y=dca_buys["Price"], mode="markers", name="DCA 買進", 
            marker=dict(color="#2E7D32", size=6, symbol="circle"),
            hoverinfo="text", hovertext=dca_hover
        ))

    fig_price.update_layout(
        template="plotly_white", height=500, hovermode="x unified",
        yaxis=dict(title=f"價格 (TWD)", showgrid=True, zeroline=False),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # Tabs
    ###############################################################

    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])

    with tab_equity:
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_BH"], mode="lines", name="Buy & Hold"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS 策略"))
        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    with tab_dd:
        dd_bh = (df["Equity_BH"] / df["Equity_BH"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_bh, name="Buy & Hold"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS 策略", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_bh  = [nz(cagr_bh),  nz(sharpe_bh),  nz(sortino_bh),  nz(-mdd_bh),  nz(-vol_bh)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill='toself', name='LRS 策略', line=dict(color='#636EFA', width=3), fillcolor='rgba(99, 110, 250, 0.2)'))
        fig_radar.add_trace(go.Scatterpolar(r=radar_bh, theta=radar_categories, fill='toself', name='Buy & Hold', line=dict(color='#EF553B', width=2), fillcolor='rgba(239, 85, 59, 0.15)'))
        fig_radar.update_layout(height=480, paper_bgcolor='rgba(0,0,0,0)', polar=dict(radialaxis=dict(visible=True, showticklabels=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return"] * 100, name="Buy & Hold", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS 策略", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)
        st.plotly_chart(fig_hist, use_container_width=True)

    ###############################################################
    # KPI Summary & Table
    ###############################################################
    
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

    # 表格
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>LRS 策略</span>": {
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
        .comparison-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            border: 1px solid var(--secondary-background-color);
            font-family: 'Noto Sans TC', sans-serif;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }
        .comparison-table th {
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
        .comparison-table td.lrs-col {
            background-color: rgba(128, 128, 128, 0.03); 
        }
        .trophy-icon {
            margin-left: 6px;
            font-size: 1.1em;
            text-shadow: 0 0 5px rgba(255, 215, 0, 0.4);
        }
        .comparison-table tr:hover td {
            background-color: rgba(128,128,128, 0.05);
        }
    </style>
    <table class="comparison-table">
        <thead>
            <tr>
                <th style="text-align:left; padding-left:16px; width:25%;">指標</th>
    """
    for col_name in df_vertical.columns:
        html_code += f"<th>{col_name}</th>"
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
            if isinstance(val, (int, float)) and val != -1:
                display_text = config["fmt"](val)
            else:
                display_text = "—"
            
            is_winner = False
            if target_val is not None and isinstance(val, (int, float)) and val == target_val:
                is_winner = True
            if is_winner:
                display_text = f"{display_text} <span class='trophy-icon'>🏆</span>"
            
            is_lrs = (i == 0)
            lrs_class = "lrs-col" if is_lrs else ""
            font_weight = "bold" if is_lrs else "normal"
            html_code += f"<td class='data-cell {lrs_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        html_code += "</tr>"
    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)
