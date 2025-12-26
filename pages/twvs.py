###############################################################
# app.py — 正2 核心衛星策略 (50% B&H + 50% 布林網格)
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
    page_title="正2 核心衛星策略",
    page_icon="🛡️",
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
    "<h1 style='margin-bottom:0.5em;'>🛡️ 50/50 核心衛星策略 (布林波動)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>策略邏輯：</b><br>
1️⃣ <b>核心部位 (Core)</b>：初始資金 50% 買進正2，<b>長期持有不動</b> (作為底倉)。<br>
2️⃣ <b>衛星部位 (Cash)</b>：初始資金 50% 保留為現金，依據布林通道進行加減碼。<br>
3️⃣ <b>交易規則 (不看 200SMA)</b>：<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <b>買進</b>：跌破布林下軌 ⮕ 動用現金加碼。<br>
&nbsp;&nbsp;&nbsp;&nbsp;• <b>賣出</b>：突破布林上軌 ⮕ 賣出<b>加碼的部位</b> (底倉不動)。<br>
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
    lev_label = st.selectbox("選擇交易標的", list(LEV_ETFS.keys()))
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
    capital = st.number_input("總投入本金（元）", 1000, 50_000_000, 100_000, step=10_000)
with col6:
    init_pos_pct = st.number_input("初始正2持倉比例 (%)", 0, 100, 50, step=10, help="剩下的比例為現金，用來加碼")

# --- 策略進階設定 ---
st.write("---")
st.write("### ⚙️ 參數設定")

col_bb1, col_bb2 = st.columns(2)

with col_bb1:
    st.markdown("#### 🌊 布林通道設定")
    bb_window = st.number_input("布林均線週期 (MA)", 10, 240, 20, 10, help="標準布林通道通常使用 20MA")
    bb_std_dev = st.number_input("布林通道倍數 (σ)", 1.0, 4.0, 2.0, 0.1, help="越大交易越少，但越精準")
    
with col_bb2:
    st.markdown("#### ⚖️ 加減碼規則")
    action_pct = st.number_input("單次交易金額 (%)", 1, 20, 10, step=1, help="每次加碼/減碼總本金的多少百分比")
    
    c1, c2 = st.columns(2)
    with c1:
        add_interval = st.number_input("加碼冷卻 (日)", 1, 30, 3, help="跌破下軌後的買進間隔")
    with c2:
        reduce_interval = st.number_input("減碼冷卻 (日)", 1, 30, 5, help="漲破上軌後的賣出間隔")

###############################################################
# 主程式開始
###############################################################

if st.button("開始回測 🚀"):

    start_early = start - dt.timedelta(days=int(bb_window * 2) + 60) 

    with st.spinner("讀取 CSV 中…"):
        df_raw = load_csv(lev_symbol)

    if df_raw.empty:
        st.error("⚠️ CSV 資料讀取失敗，請確認 data/*.csv 是否存在")
        st.stop()

    df_raw = df_raw.loc[start_early:end]

    df = pd.DataFrame(index=df_raw.index)
    df["Price"] = df_raw["Price"] 
    df = df.sort_index()

    # 1. 計算布林通道 (不做 SMA 交易訊號，純粹畫軌道)
    df["MA_BB"] = df["Price"].rolling(bb_window).mean()
    df["Std_Dev"] = df["Price"].rolling(bb_window).std()
    
    df["BB_Upper"] = df["MA_BB"] + (bb_std_dev * df["Std_Dev"])
    df["BB_Lower"] = df["MA_BB"] - (bb_std_dev * df["Std_Dev"])

    df = df.dropna(subset=["MA_BB", "BB_Upper"])

    df = df.loc[start:end]
    if df.empty:
        st.error("⚠️ 有效回測區間不足")
        st.stop()

    # ###############################################################
    # 核心交易邏輯 (現金流模擬)
    # ###############################################################
    
    # 初始化資金狀態
    current_cash = capital * (1 - init_pos_pct / 100.0)
    current_shares = (capital * (init_pos_pct / 100.0)) / df["Price"].iloc[0]
    
    # 設定「底倉股數」(Floor Shares) - 這部分是不動產
    base_shares_floor = current_shares 
    
    # 記錄每日狀態
    equity_curve = []
    cash_curve = []
    pos_pct_curve = []
    signals = [] # 1=Buy, -1=Sell, 0=None

    days_since_add = 999 
    days_since_reduce = 999
    
    trade_count = 0

    for i in range(len(df)):
        price = df["Price"].iloc[i]
        upper = df["BB_Upper"].iloc[i]
        lower = df["BB_Lower"].iloc[i]
        
        signal = 0
        days_since_add += 1
        days_since_reduce += 1
        
        # 交易金額基礎 (例如每次投入總本金的 10%)
        trade_amount = capital * (action_pct / 100.0)

        # === 規則 1: 跌破下軌 -> 用現金買進 ===
        if price < lower:
            if days_since_add >= add_interval:
                # 檢查現金夠不夠
                if current_cash >= trade_amount:
                    shares_to_buy = trade_amount / price
                    current_shares += shares_to_buy
                    current_cash -= trade_amount
                    
                    signal = 1 # Buy
                    days_since_add = 0
                    trade_count += 1
                else:
                    # 現金不足，All in 剩餘現金 (可選)
                    if current_cash > 0:
                        shares_to_buy = current_cash / price
                        current_shares += shares_to_buy
                        current_cash = 0
                        signal = 1
                        days_since_add = 0
                        trade_count += 1

        # === 規則 2: 漲破上軌 -> 賣出 (但保留底倉) ===
        elif price > upper:
            if days_since_reduce >= reduce_interval:
                # 計算可賣股數 (目前持股 - 底倉)
                tradable_shares = current_shares - base_shares_floor
                
                if tradable_shares > 0:
                    shares_to_sell = trade_amount / price
                    
                    # 如果想賣的 > 可賣的，就只賣可賣的
                    if shares_to_sell > tradable_shares:
                        shares_to_sell = tradable_shares
                    
                    if shares_to_sell > 0:
                        current_shares -= shares_to_sell
                        current_cash += (shares_to_sell * price)
                        
                        signal = -1 # Sell
                        days_since_reduce = 0
                        trade_count += 1
        
        # 記錄當日淨值
        total_equity = current_cash + (current_shares * price)
        equity_curve.append(total_equity)
        cash_curve.append(current_cash)
        pos_pct_curve.append((current_shares * price) / total_equity)
        signals.append(signal)

    df["Equity_Strategy"] = equity_curve
    df["Signal"] = signals
    df["Pos_Pct"] = pos_pct_curve
    
    # 比較基準: 100% Buy & Hold
    initial_shares_bh = capital / df["Price"].iloc[0]
    df["Equity_BH_100"] = initial_shares_bh * df["Price"]
    
    # 比較基準: 50% Buy & Hold (不做再平衡，剩下的現金放著)
    # 假設現金不生利息
    initial_cash_50 = capital * (1 - init_pos_pct/100.0)
    initial_shares_50 = (capital * (init_pos_pct/100.0)) / df["Price"].iloc[0]
    df["Equity_BH_50"] = initial_cash_50 + (initial_shares_50 * df["Price"])

    # ###############################################################
    # 指標計算
    # ###############################################################
    
    df["Ret_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Ret_BH_100"] = df["Equity_BH_100"].pct_change().fillna(0)

    years_len = (df.index[-1] - df.index[0]).days / 365

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        final_ret = (final_eq / capital) - 1
        cagr = (final_eq / capital)**(1/years_len) - 1 if years_len > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        return final_eq, final_ret, cagr, mdd, vol, sharpe

    eq_str_final, ret_str, cagr_str, mdd_str, vol_str, sharpe_str = calc_core(df["Equity_Strategy"], df["Ret_Strategy"])
    eq_bh_final, ret_bh, cagr_bh, mdd_bh, vol_bh, sharpe_bh = calc_core(df["Equity_BH_100"], df["Ret_BH_100"])

    # 篩選訊號點位 for Plotting
    sig_buy = df[df["Signal"] == 1]
    sig_sell = df[df["Signal"] == -1]

    # ###############################################################
    # 圖表呈現
    # ###############################################################

    st.markdown(f"<h3>📌 {lev_label} 交易執行圖</h3>", unsafe_allow_html=True)
    

[Image of Bollinger Bands trading strategy]

    fig_price = go.Figure()

    # 1. 價格
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["Price"], name=f"{lev_label}", 
        mode="lines", line=dict(width=2, color="#636EFA"),
    ))

    # 2. 布林通道
    fig_price.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig_price.add_trace(go.Scatter(
        x=df.index, y=df["BB_Lower"], name=f"布林通道 (±{bb_std_dev}σ)", 
        mode="lines", line=dict(width=0), fill='tonexty', fillcolor='rgba(128,128,128,0.1)'
    ))

    # 3. 訊號
    if not sig_buy.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_buy.index, y=sig_buy["Price"], mode="markers", name=f"加碼買進", 
            marker=dict(color="#00C853", size=8, symbol="triangle-up")
        ))
    if not sig_sell.empty:
        fig_price.add_trace(go.Scatter(
            x=sig_sell.index, y=sig_sell["Price"], mode="markers", name=f"減碼獲利", 
            marker=dict(color="#FFA726", size=8, symbol="triangle-down")
        ))

    fig_price.update_layout(
        template="plotly_white", height=500, hovermode="x unified",
        yaxis=dict(title=f"價格", showgrid=True),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # --- 倉位變化圖 (Stack Area) ---
    st.markdown("<h3>📊 資產配置變化 (核心 vs 衛星)</h3>", unsafe_allow_html=True)
    fig_pos = go.Figure()
    
    # 這裡有點小技巧：我們畫出現金比例與股票比例
    # Stock Value = Total Equity - Cash
    df["Stock_Val"] = df["Equity_Strategy"] - cache_curve = df["Equity_Strategy"] - (df["Equity_Strategy"] * (1-df["Pos_Pct"])) # 這裡直接用 Pos_Pct 反推比較快
    
    # 修正變數名稱錯誤
    cash_vals = [c for c in cash_curve]
    stock_vals = [e - c for e, c in zip(equity_curve, cash_vals)]
    
    fig_pos.add_trace(go.Scatter(
        x=df.index, y=stock_vals, mode='lines', name='正2持倉 (含底倉)', stackgroup='one', line=dict(width=0, color="#636EFA")
    ))
    fig_pos.add_trace(go.Scatter(
        x=df.index, y=cash_vals, mode='lines', name='現金部位', stackgroup='one', line=dict(width=0, color="#00CC96")
    ))
    
    fig_pos.update_layout(template="plotly_white", height=350, yaxis=dict(title="資產價值 (元)"), hovermode="x unified")
    st.plotly_chart(fig_pos, use_container_width=True)

    # --- 資金曲線比較 ---
    st.markdown("<h3>💰 策略績效比較</h3>", unsafe_allow_html=True)
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], mode="lines", name="50/50 核心衛星", line=dict(width=2.5, color="#636EFA")))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_100"], mode="lines", name="100% 正2 B&H (高風險)", line=dict(width=1.5, color="#EF553B", dash="dot")))
    fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_50"], mode="lines", name="50% 正2 B&H (躺平)", line=dict(width=1.5, color="gray")))
    
    fig_eq.update_layout(template="plotly_white", height=450, yaxis=dict(title="總資產 (元)"))
    st.plotly_chart(fig_eq, use_container_width=True)

    # --- KPI Table ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    with col_kpi1: st.metric("期末總資產", fmt_money(eq_str_final), delta=f"{ret_str*100:.1f}%")
    with col_kpi2: st.metric("CAGR (年化)", fmt_pct(cagr_str))
    with col_kpi3: st.metric("最大回撤 (MDD)", fmt_pct(mdd_str), help="越小越好")
    with col_kpi4: st.metric("夏普比率 (Sharpe)", fmt_num(sharpe_str))
    with col_kpi5: st.metric("交易次數", trade_count)

    st.caption(f"比較基準：100% Buy&Hold 之 CAGR 為 {fmt_pct(cagr_bh)}，最大回撤為 {fmt_pct(mdd_bh)}。")
