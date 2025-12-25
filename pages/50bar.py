###############################################################
# app.py — 0050LRS + DCA (直覺版：空手即等待 + 日報酬分佈)
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
    page_title="0050LRS 回測系統",
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
    "<h1 style='margin-bottom:0.5em;'>📊 0050LRS 動態槓桿</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold（0050 / 006208）<br>
2️⃣ 槓桿 ETF Buy & Hold（00631L / 00663L / 00675L / 00685L）<br>
3️⃣ 槓桿 ETF LRS（訊號來自原型 ETF 的 SMA 均線，實際進出槓桿 ETF）<br>
4️⃣ <b>LRS + DCA 混合策略</b>：跌破均線賣出後，可選擇「定期定額買回」或「等待下次突破」。
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

# 移除 Checkbox，只保留 Radio Button
position_mode = st.radio(
    "策略初始狀態",
    ["空手起跑（嚴格等待黃金交叉）", "一開始就全倉槓桿 ETF"],
    index=0,
    help="空手起跑：若開始時價格已在均線上，會保持空手，直到下次黃金交叉才進場。"
)

with st.expander("📉 跌破均線後的 DCA (定期定額) 設定", expanded=True):
    col_dca1, col_dca2, col_dca3 = st.columns([1, 2, 2])
    with col_dca1:
        enable_dca = st.toggle("啟用 DCA 接刀", value=False, help="開啟後，當賣出訊號出現，會分批買回，而不是空手等待。")
    with col_dca2:
        dca_interval = st.number_input("買進間隔天數 (日)", min_value=1, max_value=60, value=3, disabled=not enable_dca, help="賣出後每隔幾天買進一次")
    with col_dca3:
        dca_pct = st.number_input("每次買進資金比例 (%)", min_value=1, max_value=100, value=10, step=5, disabled=not enable_dca, help="每次投入總資金的多少百分比")


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
    # LRS + DCA + 嚴格進場 混合策略邏輯
    ###############################################################

    # 1. 初始化容器
    executed_signals = [0] * len(df) # 記錄訊號 (1=Full Buy, -1=Full Sell, 2=DCA Buy)
    positions = [0.0] * len(df)      # 記錄持倉比例 (0.0 ~ 1.0)

    # 2. 設定初始狀態
    # 邏輯優化：根據 position_mode 直接決定「買入權限」
    if "全倉" in position_mode:
        current_pos = 1.0
        can_buy_permission = True
    else:
        # 空手起跑 = 0持倉 + 鎖住權限(直到跌破均線)
        current_pos = 0.0
        can_buy_permission = False 
    
    positions[0] = current_pos
    
    # DCA 計數器
    dca_wait_counter = 0 

    # 3. 逐日遍歷
    for i in range(1, len(df)):
        p = df["Price_base"].iloc[i]
        m = df["MA_Signal"].iloc[i]
        p0 = df["Price_base"].iloc[i-1]
        m0 = df["MA_Signal"].iloc[i-1]

        # 判斷當前價格狀態
        is_above_sma = p > m
        
        daily_signal = 0

        if is_above_sma:
            # === 狀況 1: 價格在均線上 ===
            
            # 檢查是否有買入權限
            if can_buy_permission:
                current_pos = 1.0
                daily_signal = 1 if p0 <= m0 else 0 # 剛突破時標記一下
            else:
                # 沒權限 (因為選空手起跑，且還沒經歷過跌破)，強迫空手
                current_pos = 0.0
                daily_signal = 0
            
            # 只要在均線上，重置 DCA 計數器
            dca_wait_counter = 0

        else:
            # === 狀況 2: 價格在均線下 ===
            
            # 關鍵：只要跌到均線下，就自動解鎖「買入權限」
            # 代表市場冷卻了，下一次的突破就是有效的黃金交叉
            can_buy_permission = True
            
            # 2-1. 剛跌破那天 (死亡交叉)
            if p0 > m0:
                current_pos = 0.0 # 先清空
                daily_signal = -1
                dca_wait_counter = 0 # 準備開始數天數
            
            # 2-2. 已經在均線下
            else:
                if enable_dca and current_pos < 1.0:
                    # 啟用 DCA 且還沒買滿
                    dca_wait_counter += 1
                    
                    # 達到間隔天數，執行買進
                    if dca_wait_counter >= dca_interval:
                        current_pos += (dca_pct / 100.0) # 增加倉位
                        if current_pos > 1.0: 
                            current_pos = 1.0 
                        
                        daily_signal = 2 # 標記為 DCA 買進點
                        dca_wait_counter = 0 

        # 記錄結果
        executed_signals[i] = daily_signal
        positions[i] = round(current_pos, 4) 

    # 4. 寫回 DataFrame
    df["Signal"] = executed_signals
    df["Position"] = positions

    ###############################################################
    # 資金曲線 (支援部分持倉運算)
    ###############################################################

    equity_lrs = [1.0]
    
    for i in range(1, len(df)):
        # 取得昨天的持倉比例
        pos_weight = df["Position"].iloc[i-1]
        
        # 槓桿 ETF 今天的漲跌幅
        lev_ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        
        # 計算新的淨值
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
    buys = df[df["Signal"] == 1]       # 黃金交叉全倉
    sells = df[df["Signal"] == -1]     # 死亡交叉清倉
    dca_buys = df[df["Signal"] == 2]   # DCA 加碼點

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
    # 交易次數包含 Full Buy, Full Sell, 和每次 DCA
    trade_count_lrs = int((df["Signal"] != 0).sum())

    ###############################################################
    # 圖表 + KPI + 表格
    ###############################################################

    # --- 原型 & MA & 槓桿價格 (雙軸圖表) ---
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)

    fig_price = go.Figure()

    # 1. [左軸] 原型 ETF
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price_base"], name=f"{base_label} (左軸)", 
        mode="lines", line=dict(width=2, color="#636EFA"),
        hovertemplate=f"<b>{base_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 2. [左軸] SMA
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["MA_Signal"], name=f"{sma_window} 日 SMA", 
        mode="lines", line=dict(width=1.5, color="#FFA15A"),
        hovertemplate=f"<b>{sma_window}SMA</b><br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 3. [右軸] 槓桿 ETF
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price_lev"], name=f"{lev_label} (右軸)", 
        mode="lines", line=dict(width=1, color="#00CC96", dash='dot'), opacity=0.6, yaxis="y2", 
        hovertemplate=f"<b>{lev_label}</b><br>日期: %{{x|%Y-%m-%d}}<br>價格: %{{y:,.2f}} 元<extra></extra>"
    ))

    # 4. [標記] 買進點 (Full Buy)
    if not buys.empty:
        buy_hover = [f"<b>▲ 黃金交叉 (全倉)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(buys.index, buys["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=buys.index, y=buys["Price_base"], mode="markers", name="全倉買進", 
            marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=buy_hover
        ))

    # 5. [標記] 賣出點 (Full Sell)
    if not sells.empty:
        sell_hover = [f"<b>▼ 死亡交叉 (清倉)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(sells.index, sells["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=sells.index, y=sells["Price_base"], mode="markers", name="清倉賣出", 
            marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white")),
            hoverinfo="text", hovertext=sell_hover
        ))

    # 6. [標記] DCA 買進點 (小綠點)
    if not dca_buys.empty:
        dca_hover = [f"<b>● DCA 加碼 ({dca_pct}%)</b><br>{d.strftime('%Y-%m-%d')}<br>成交: {p:.2f}" for d, p in zip(dca_buys.index, dca_buys["Price_lev"])]
        fig_price.add_trace(go.Scatter(
            x=dca_buys.index, y=dca_buys["Price_base"], mode="markers", name="DCA 買進", 
            marker=dict(color="#2E7D32", size=6, symbol="circle"),
            hoverinfo="text", hovertext=dca_hover
        ))

    fig_price.update_layout(
        template="plotly_white", height=450, hovermode="x unified",
        yaxis=dict(title=f"{base_label} 價格", showgrid=True, zeroline=False),
        yaxis2=dict(title=f"{lev_label} 價格", overlaying="y", side="right", showgrid=False, zeroline=False),
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
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name="槓桿BH"))
        fig_equity.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS+DCA"))
        fig_equity.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_equity, use_container_width=True)

    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS+DCA", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_lrs  = [nz(cagr_lrs),  nz(sharpe_lrs),  nz(sortino_lrs),  nz(-mdd_lrs),  nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev),  nz(sharpe_lev),  nz(sortino_lev),  nz(-mdd_lev),  nz(-vol_lev)]
        radar_base = [nz(cagr_base), nz(sharpe_base), nz(sortino_base), nz(-mdd_base), nz(-vol_base)]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill='toself', name='LRS+DCA', line=dict(color='#636EFA', width=3), fillcolor='rgba(99, 110, 250, 0.2)'))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill='toself', name=f'{lev_label} BH', line=dict(color='#EF553B', width=2), fillcolor='rgba(239, 85, 59, 0.15)'))
        fig_radar.add_trace(go.Scatterpolar(r=radar_base, theta=radar_categories, fill='toself', name=f'{base_label} BH', line=dict(color='#00CC96', width=2), fillcolor='rgba(0, 204, 150, 0.1)'))
        
        fig_radar.update_layout(height=480, paper_bgcolor='rgba(0,0,0,0)', polar=dict(radialaxis=dict(visible=True, showticklabels=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.6))
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
    
    # 準備原始數據
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
        },
        f"<b>{base_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
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

    # 建立 DataFrame 並排序
    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)

    # 定義格式化與「好壞方向」
    metrics_config = {
        "期末資產":       {"fmt": fmt_money, "invert": False},
        "總報酬率":       {"fmt": fmt_pct,   "invert": False},
        "CAGR (年化)":    {"fmt": fmt_pct,   "invert": False},
        "Calmar Ratio":   {"fmt": fmt_num,   "invert": False},
        "最大回撤 (MDD)": {"fmt": fmt_pct,   "invert": True},  # 越小越贏
        "年化波動":       {"fmt": fmt_pct,   "invert": True},  # 越小越贏
        "Sharpe Ratio":   {"fmt": fmt_num,   "invert": False},
        "Sortino Ratio":  {"fmt": fmt_num,   "invert": False},
        "交易次數":       {"fmt": lambda x: fmt_int(x) if x >= 0 else "—", "invert": True} 
    }

    # 生成 HTML (回復原本的高級樣式)
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
        
        # 1. 找出該列的「最佳值」
        raw_row_values = df_vertical.loc[metric].values
        # 過濾掉 -1 (代表無此數據) 和 NaN
        valid_values = [x for x in raw_row_values if isinstance(x, (int, float)) and x != -1 and not pd.isna(x)]
        
        target_val = None
        if valid_values and metric != "交易次數": 
            if config["invert"]:
                target_val = min(valid_values) 
            else:
                target_val = max(valid_values) 

        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        
        # 2. 逐欄填入
        for i, strategy in enumerate(df_vertical.columns):
            val = df_vertical.at[metric, strategy]
            
            # 格式化數值
            if isinstance(val, (int, float)) and val != -1:
                display_text = config["fmt"](val)
            else:
                display_text = "—"
            
            # 判斷是否為冠軍
            is_winner = False
            if target_val is not None and isinstance(val, (int, float)) and val == target_val:
                is_winner = True
            
            if is_winner:
                display_text = f"{display_text} <span class='trophy-icon'>🏆</span>"
            
            # 第一欄 (LRS+DCA) 加粗顯示
            is_lrs = (i == 0)
            lrs_class = "lrs-col" if is_lrs else ""
            font_weight = "bold" if is_lrs else "normal"
            
            html_code += f"<td class='data-cell {lrs_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        
        html_code += "</tr>"

    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)
