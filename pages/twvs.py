###############################################################
# app.py — LevLRS + DCA (修正版：現金+股數帳戶制)
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
    page_title="LRS 回測系統 (帳戶制精確版)",
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
    "<h1 style='margin-bottom:0.5em;'>📊 槓桿 ETF 動態均線策略 (帳戶制精確版)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較兩種策略：</b><br>
1️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
2️⃣ <b>LRS + DCA 混合策略</b>：訊號<b>直接來自該 ETF 的 SMA 均線</b>。<br>
   &nbsp;&nbsp;&nbsp;&nbsp;採用<b>現金+股數</b>嚴謹計算，跌破均線後持有現金，DCA 僅投入部分資金，回撤計算更準確。
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

lev_label = st.selectbox("選擇回測標的", list(LEV_ETFS.keys()))
lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(lev_symbol)
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

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
st.write("### ⚙️ 策略進階設定")

position_mode = st.radio(
    "策略初始狀態",
    [ "一開始就全倉投入","空手起跑"],
    index=0,
    help="空手起跑：若開始時價格已在均線上，會保持空手，直到下次黃金交叉才進場。"
)

with st.expander("📉 跌破均線後的 DCA (定期定額) 設定", expanded=True):
    col_dca1, col_dca2, col_dca3 = st.columns([1, 2, 2])
    with col_dca1:
        enable_dca = st.toggle("啟用 DCA定期定額", value=False, help="開啟後，當賣出訊號出現，會分批買回。")
    with col_dca2:
        dca_interval = st.number_input("買進間隔天數 (日)", min_value=1, max_value=60, value=3, disabled=not enable_dca, help="賣出後每隔幾天買進一次")
    with col_dca3:
        dca_pct = st.number_input("每次買進資金比例 (%)", min_value=1, max_value=100, value=10, step=5, disabled=not enable_dca, help="以當時總資產的多少百分比金額買進")


###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)

    with st.spinner("讀取 CSV 中…"):
        df_lev_raw = load_csv(lev_symbol)

    if df_lev_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
        st.stop()

    df_lev_raw = df_lev_raw.loc[start_early:end]
    df = pd.DataFrame(index=df_lev_raw.index)
    df["Price_lev"] = df_lev_raw["Price"]
    df = df.sort_index()

    # 計算 SMA
    df["MA_Signal"] = df["Price_lev"].rolling(sma_window).mean()
    df = df.dropna(subset=["MA_Signal"])

    # 切割到用戶指定區間
    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    ###############################################################
    # LRS + DCA 混合策略邏輯 (現金+股數 嚴格帳戶制)
    ###############################################################

    # 1. 初始化容器
    executed_signals = [0] * len(df) # 記錄訊號
    positions_pct = [0.0] * len(df)  # 記錄"市值佔比"供繪圖用
    equity_curve = [0.0] * len(df)   # 記錄每日總淨值

    # 2. 初始化帳戶
    cash = float(capital)
    shares = 0.0
    
    # 根據設定決定初始狀態
    first_price = df["Price_lev"].iloc[0]
    first_ma = df["MA_Signal"].iloc[0]
    
    can_buy_permission = False
    
    if "全倉" in position_mode:
        # 開局直接買滿
        shares = cash / first_price
        cash = 0.0
        can_buy_permission = True
        positions_pct[0] = 1.0
    else:
        # 空手起跑
        positions_pct[0] = 0.0
        can_buy_permission = False # 需等待跌破後才能解鎖

    equity_curve[0] = cash + (shares * first_price)
    
    dca_wait_counter = 0 

    # 3. 逐日遍歷 (Event-driven Loop)
    for i in range(1, len(df)):
        # 今日價格數據
        price = df["Price_lev"].iloc[i]
        ma = df["MA_Signal"].iloc[i]
        
        # 昨日數據 (用於判斷交叉)
        prev_price = df["Price_lev"].iloc[i-1]
        prev_ma = df["MA_Signal"].iloc[i-1]

        # 1. 計算當前總資產 (Mark to Market)
        # 這是"交易前"的資產價值，DCA 金額會基於此計算
        curr_total_equity = cash + (shares * price)
        
        # 2. 判斷訊號
        is_above_sma = price > ma
        daily_signal = 0

        # === 狀況 1: 價格在均線上 ===
        if is_above_sma:
            if can_buy_permission:
                # 應該全倉，檢查是否有現金
                if cash > 100: # 留一點緩衝，大於100元才買
                    shares += cash / price
                    cash = 0.0
                    daily_signal = 1 if prev_price <= prev_ma else 0 # 剛突破標記
            else:
                # 無權限，強制空手
                # 理論上若空手起跑，這裡應該 shares=0，確保乾淨
                if shares > 0:
                    cash += shares * price
                    shares = 0.0
                daily_signal = 0
            
            dca_wait_counter = 0

        # === 狀況 2: 價格在均線下 ===
        else:
            can_buy_permission = True # 解鎖買入權限
            
            # 2-1. 剛跌破 (死亡交叉) -> 清倉
            if prev_price > prev_ma:
                if shares > 0:
                    cash += shares * price
                    shares = 0.0
                daily_signal = -1
                dca_wait_counter = 0
            
            # 2-2. 持續在均線下 -> 檢查 DCA
            else:
                if enable_dca:
                    # 只有當還有現金時才 DCA
                    if cash > 100:
                        dca_wait_counter += 1
                        if dca_wait_counter >= dca_interval:
                            # 執行買進
                            # 計算買入金額：總資產 * (dca_pct%)
                            target_invest_amt = curr_total_equity * (dca_pct / 100.0)
                            
                            # 實際能買的金額 (不能超過現金)
                            actual_invest_amt = min(cash, target_invest_amt)
                            
                            if actual_invest_amt > 0:
                                shares += actual_invest_amt / price
                                cash -= actual_invest_amt
                                daily_signal = 2
                                dca_wait_counter = 0

        # 3. 結算今日資產 (交易後)
        final_equity = cash + (shares * price)
        equity_curve[i] = final_equity
        executed_signals[i] = daily_signal
        
        # 計算實際持倉比例 (供圖表用)
        if final_equity > 0:
            positions_pct[i] = (shares * price) / final_equity
        else:
            positions_pct[i] = 0.0

    # 4. 寫回 DataFrame
    df["Signal"] = executed_signals
    df["Position"] = positions_pct # 這是真實的市值佔比
    df["Equity_LRS"] = equity_curve
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)

    # 計算 Buy & Hold Equity
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod() * capital

    # 計算百分比回報 (用於畫圖)
    df["Pct_Lev"] = (df["Equity_BH_Lev"] / capital) - 1
    df["Pct_LRS"] = (df["Equity_LRS"] / capital) - 1

    # 篩選訊號點位
    buys = df[df["Signal"] == 1]       # 黃金交叉全倉
    sells = df[df["Signal"] == -1]     # 死亡交叉清倉
    dca_buys = df[df["Signal"] == 2]   # DCA 加碼點

    ###############################################################
    # 指標計算
    ###############################################################

    years_len = (df.index[-1] - df.index[0]).days / 365

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = (final_eq / capital) - 1
        cagr = (final_eq / capital)**(1/years_len) - 1 if years_len > 0 else np.nan
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

    capital_lrs_final = eq_lrs_final
    capital_lev_final = eq_lev_final
    
    trade_count_lrs = int((df["Signal"] != 0).sum())

    ###############################################################
    # 圖表 + KPI + 表格
    ###############################################################

    # --- 價格與 SMA 圖表 ---
    st.markdown("<h3>📌 策略訊號與執行價格</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    # 1. 價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price_lev"], name=f"{lev_label}", 
        mode="lines", line=dict(width=2, color="#636EFA"),
        hovertemplate=f"<b>{lev_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 2. SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Signal"], name=f"{sma_window} 日 SMA", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
        hovertemplate=f"<b>{sma_window}SMA</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 3. [標記] 買進點 (Full Buy)
    if not buys.empty:
        buy_hover = [f"<b>▲ 黃金交叉 (全倉)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(buys.index, buys["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price_lev"], mode="markers", name="全倉買進", 
            marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=buy_hover
        ))

    # 4. [標記] 賣出點 (Full Sell)
    if not sells.empty:
        sell_hover = [f"<b>▼ 死亡交叉 (清倉)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(sells.index, sells["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price_lev"], mode="markers", name="清倉賣出", 
            marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=sell_hover
        ))

    # 5. [標記] DCA 買進點
    if not dca_buys.empty:
        dca_hover = [f"<b>● DCA 加碼 ({dca_pct}%)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(dca_buys.index, dca_buys["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=dca_buys.index, y=dca_buys["Price_lev"], mode="markers", name="DCA 買進", 
            marker=dict(color="#2E7D32", size=6, symbol="circle"),
            hoverinfo="text", hovertext=dca_hover
        ))

    fig_price.update_layout(
        template="plotly_white", height=450, hovermode="x unified",
        yaxis=dict(title=f"{lev_label} 價格", showgrid=True, zeroline=False),
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
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name=f"{lev_label} BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS+DCA"))
        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    with tab_dd:
        # DD 計算： (當前淨值 / 歷史最高淨值) - 1
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name=f"{lev_label} BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS+DCA", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill='toself', name='LRS+DCA', line=dict(color='#636EFA', width=3), fillcolor='rgba(99, 110, 250, 0.2)'))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill='toself', name=f'{lev_label} BH', line=dict(color='#EF553B', width=2), fillcolor='rgba(239, 85, 59, 0.15)'))
        
        fig_radar.update_layout(height=480, paper_bgcolor='rgba(0,0,0,0)', polar=dict(radialaxis=dict(visible=True, showticklabels=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name=f"{lev_label} BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS+DCA", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)

        st.plotly_chart(fig_hist, use_container_width=True)

    ###############################################################
    # KPI Summary & Table
    ###############################################################
    
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
    with rk[0]: st.markdown(kpi_html("期末資產", format_currency(capital_lrs_final), asset_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[1]: st.markdown(kpi_html("CAGR", format_percent(cagr_lrs), cagr_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[2]: st.markdown(kpi_html("波動率", format_percent(vol_lrs), vol_gap_lrs_vs_lev), unsafe_allow_html=True)
    with rk[3]: st.markdown(kpi_html("最大回撤", format_percent(mdd_lrs), mdd_gap_lrs_vs_lev), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 表格
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>LRS+DCA</span>": {
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

    # 建立 DataFrame 並排序
    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)

    # 定義格式化與「好壞方向」
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

    # 生成 HTML
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
    
    # 寫入表頭
    for col_name in df_vertical.columns:
        html_code += f"<th>{col_name}</th>"
    html_code += "</tr></thead><tbody>"

    # 寫入內容
    for metric in df_vertical.index:
        config = metrics_config.get(metric, {"fmt": fmt_num, "invert": False})
        
        raw_row_values = df_vertical.loc[metric].values
        valid_values = [x for x in raw_row_values if isinstance(x, (int, float)) and x != -1 and not pd.isna(x)]
        
        target_val = None
        if valid_values and metric != "交易次數": 
            if config["invert"]:
                target_val = min(valid_values) 
            else:
                target_val = max(valid_values) 

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
