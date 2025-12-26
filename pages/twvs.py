###############################################################
# app.py — 正2 策略 (SMA 斜率 + 布林通道 雙重邏輯版)
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

# ... (字型設定與 Page Config 保持不變，省略以節省篇幅) ...
# ... (請保留原本的字型設定程式碼) ...

st.set_page_config(
    page_title="正2 智能濾網回測",
    page_icon="🧠",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證守門員 (保持不變)
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ... (Sidebar 保持不變) ...

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>🧠 槓桿 ETF 智能濾網 (斜率 + 布林)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<b>解決「盤整被洗、崩盤要跑」的矛盾：</b><br>
此策略引入 <b>SMA 斜率</b> 來判斷當下是「多頭回檔」還是「空頭破底」。<br>
1️⃣ <b>SMA 向上 (多頭)</b>：跌破布林下軌視為「回檔買點」，<b>堅持續抱</b> (不賣)。<br>
2️⃣ <b>SMA 下彎 (空頭)</b>：跌破布林下軌視為「崩盤開始」，<b>清倉停損</b>。<br>
""",
    unsafe_allow_html=True,
)

# ... (ETF 清單與 load_csv 函式保持不變) ...
# ... (請保留原本的 load_csv, get_full_range_from_csv, calc_metrics 等工具函式) ...
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}
DATA_DIR = Path("data")

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

# ------------------------------------------------------
# UI 輸入
# ------------------------------------------------------

col_sel, col_info = st.columns([1, 2])
with col_sel:
    lev_label = st.selectbox("選擇交易標的", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

s_min, s_max = get_full_range_from_csv(lev_symbol)
with col_info:
    st.info(f"📌 資料區間：{s_min} ~ {s_max}")

col3, col4, col5, col6 = st.columns(4)
with col3:
    start = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金", 1000, 5_000_000, 100_000, step=10_000)
with col6:
    sma_window = st.number_input("SMA 週期", 10, 240, 200, 10)

st.write("---")
st.write("### ⚙️ 智能濾網設定")

col_bb, col_slope = st.columns(2)

with col_bb:
    st.markdown("#### 1. 布林通道 (停損/支撐參考)")
    bb_std = st.number_input("布林通道標準差 (Std)", 1.0, 4.0, 2.0, 0.1)

with col_slope:
    st.markdown("#### 2. SMA 斜率 (趨勢過濾)")
    slope_days = st.number_input("斜率計算天數", 1, 20, 5, help="比較今天與 N 天前的 SMA 值來決定斜率正負。")
    use_slope_filter = st.toggle("啟用「斜率保護」", value=True, help="開啟後：若 SMA 斜率向上，即使跌破下軌也不賣出 (視為回檔)。")

with st.expander("📉 DCA 加碼設定"):
    col_dca1, col_dca2 = st.columns(2)
    with col_dca1:
        enable_dca = st.toggle("啟用 DCA", value=False)
    with col_dca2:
        dca_interval = st.number_input("間隔天數", 1, 60, 3)
        dca_pct = st.number_input("加碼比例 %", 1, 100, 10)

# ------------------------------------------------------
# 主程式
# ------------------------------------------------------

if st.button("開始回測 🚀"):
    start_early = start - dt.timedelta(days=sma_window * 2) 

    df_raw = load_csv(lev_symbol)
    if df_raw.empty:
        st.error("Data not found.")
        st.stop()
        
    df = df_raw.loc[start_early:end].copy()
    df["Price"] = df["Price"]
    
    # 1. 計算 SMA & 斜率
    df["MA"] = df["Price"].rolling(sma_window).mean()
    # 斜率：比較 (今天MA - N天前MA)
    df["MA_Slope_Val"] = df["MA"].diff(slope_days)
    df["Is_Trend_Up"] = df["MA_Slope_Val"] > 0
    
    # 2. 計算布林通道
    df["Std"] = df["Price"].rolling(sma_window).std()
    df["BB_Upper"] = df["MA"] + (bb_std * df["Std"])
    df["BB_Lower"] = df["MA"] - (bb_std * df["Std"])
    
    df = df.dropna()
    df = df.loc[start:end]
    
    if df.empty:
        st.error("區間無資料")
        st.stop()
        
    df["Return"] = df["Price"].pct_change().fillna(0)

    # 策略邏輯
    executed_signals = [0] * len(df)
    positions = [0.0] * len(df)
    current_pos = 1.0 # 預設滿倉開始 (方便觀察中途變化)
    can_buy = True
    dca_counter = 0
    
    positions[0] = current_pos

    for i in range(1, len(df)):
        p = df["Price"].iloc[i]
        ma = df["MA"].iloc[i]
        bb_lower = df["BB_Lower"].iloc[i]
        is_trend_up = df["Is_Trend_Up"].iloc[i]
        
        # 狀態
        is_above_ma = p > ma
        is_below_bb = p < bb_lower
        
        daily_signal = 0
        
        # 1. 買進條件：站上 MA
        if is_above_ma:
            if current_pos < 1.0: # 如果之前是空手或減碼
                if can_buy:
                    current_pos = 1.0
                    daily_signal = 1
            else:
                # 已經滿倉，保持 1.0
                pass
            dca_counter = 0
        
        # 2. 賣出檢核：跌破布林下軌
        elif is_below_bb:
            can_buy = True # 只要跌破過，下次站上就可以買
            
            # 關鍵邏輯：要不要賣？看斜率！
            should_sell = True
            
            if use_slope_filter and is_trend_up:
                # 如果開啟濾網，且趨勢向上 -> 這是回檔，不賣！
                should_sell = False
            
            if should_sell:
                # 真的要賣 (空頭破底)
                if current_pos > 0:
                    current_pos = 0.0
                    daily_signal = -1
                    dca_counter = 0
            else:
                # 這是假跌破 (回檔)，續抱 (甚至可以 DCA)
                # 這裡簡單處理：維持原倉位，但如果原本就不是滿倉(例如之前被洗出去)，可以觸發 DCA
                if enable_dca and current_pos < 1.0:
                    dca_counter += 1
                    if dca_counter >= dca_interval:
                        current_pos += (dca_pct / 100.0)
                        if current_pos > 1.0: current_pos = 1.0
                        daily_signal = 2
                        dca_counter = 0
                pass 

        # 3. 灰色地帶 (SMA ~ BB Lower 之間)
        else:
             # 維持現狀
            if current_pos >= 1.0:
                pass
            else:
                # 續抱空手 或 繼續 DCA
                if enable_dca:
                    dca_counter += 1
                    if dca_counter >= dca_interval:
                        current_pos += (dca_pct / 100.0)
                        if current_pos > 1.0: current_pos = 1.0
                        daily_signal = 2
                        dca_counter = 0
                        
        executed_signals[i] = daily_signal
        positions[i] = round(current_pos, 4)
        
    df["Signal"] = executed_signals
    df["Position"] = positions
    
    # 計算淨值
    equity = [1.0]
    for i in range(1, len(df)):
        ret = df["Return"].iloc[i]
        pos = df["Position"].iloc[i-1]
        equity.append(equity[-1] * (1 + ret * pos))
    
    df["Equity_LRS"] = equity
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH"] = (1 + df["Return"]).cumprod()
    
    # 準備繪圖資料
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    
    # --- 繪圖 ---
    st.markdown("### 📈 策略執行圖 (斜率濾網生效中)")
    fig = go.Figure()
    
    # 價格 & MA
    fig.add_trace(go.Scatter(x=df.index, y=df["Price"], name=lev_label, line=dict(color='#00CC96', width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA"], name=f"{sma_window} SMA", line=dict(color='#FFA15A', width=1.5)))
    
    # 布林通道 (灰色區域)
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], name="布林通道", fill='tonexty', 
                             fillcolor='rgba(128,128,128,0.15)', line=dict(color='rgba(128,128,128,0.5)', dash='dot')))
    
    # 買賣點
    fig.add_trace(go.Scatter(x=buys.index, y=buys["Price"], mode='markers', name='買進/回補', marker=dict(symbol='triangle-up', size=12, color='#00C853')))
    fig.add_trace(go.Scatter(x=sells.index, y=sells["Price"], mode='markers', name='停損/清倉', marker=dict(symbol='triangle-down', size=12, color='#D50000')))

    fig.update_layout(height=500, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig, use_container_width=True)
    
    # --- KPI 表格 ---
    # 簡單計算 KPI
    final_eq = df["Equity_LRS"].iloc[-1]
    bh_eq = df["Equity_BH"].iloc[-1]
    
    years = (df.index[-1] - df.index[0]).days / 365
    cagr_lrs = (final_eq)**(1/years) - 1
    cagr_bh = (bh_eq)**(1/years) - 1
    
    mdd_lrs = 1 - (df["Equity_LRS"] / df["Equity_LRS"].cummax()).min()
    mdd_bh = 1 - (df["Equity_BH"] / df["Equity_BH"].cummax()).min()
    
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    with col_kpi1: st.metric("期末資產 (策略)", fmt_money(final_eq * capital), delta=f"{((final_eq/bh_eq)-1)*100:.1f}% vs B&H")
    with col_kpi2: st.metric("CAGR (年化)", fmt_pct(cagr_lrs))
    with col_kpi3: st.metric("MDD (最大回撤)", fmt_pct(mdd_lrs), delta=f"優化 { (mdd_bh - mdd_lrs)*100:.1f}%", delta_color="inverse")
    with col_kpi4: st.metric("交易次數", int(len(buys)+len(sells)))
