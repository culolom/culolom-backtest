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
# 1. 環境與字型設定
###############################################################
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="倉鼠量化戰情室", page_icon="📈", layout="wide")

# 🔒 驗證 (若無 auth.py 則跳過)
try:
    import auth 
    if not auth.check_password(): st.stop()
except: pass 

###############################################################
# 2. 核心工具函式
###############################################################
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    """安全讀取 CSV 檔案"""
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        df["Price"] = df["Close"]
        return df[["Price"]]
    except Exception as e:
        st.error(f"讀取 {symbol} 時出錯: {e}")
        return pd.DataFrame()

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg = daily.mean()
    std = daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"

###############################################################
# 3. UI 介面設計
###############################################################
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### ⚙️ 策略參數")
    sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)
    bear_target = st.number_input("反一提前轉向漲幅 (%)", 1.0, 50.0, 10.0, step=0.5) / 100
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 多空切換：反一提前轉向機制</h1>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    capital = st.number_input("投入本金", 1000, 5000000, 100000, step=10000)
with col2:
    start_date = st.date_input("開始日期", dt.date(2020, 1, 1))
with col3:
    end_date = st.date_input("結束日期", dt.date.today())

###############################################################
# 4. 回測核心邏輯
###############################################################
if st.button("開始回測 🚀"):
    # 讀取資料
    with st.spinner("正在讀取數據..."):
        df_base = load_csv("0050.TW")
        df_bull = load_csv("00631L.TW")
        df_bear = load_csv("00632R.TW")

    if df_base.empty or df_bull.empty or df_bear.empty:
        st.error("⚠️ 檔案缺失！請檢查 data/ 資料夾內是否有 0050.TW, 00631L.TW, 00632R.TW 的 CSV。")
        st.stop()

    # 資料合併
    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_bull["Price"].rename("Price_bull"), how="inner")
    df = df.join(df_bear["Price"].rename("Price_bear"), how="inner")
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start_date:end_date].dropna(subset=["SMA"])

    # 策略逐日計算
    signals = [1] * len(df)
    early_exit_flags = [False] * len(df)
    bear_entry_price = 0.0
    current_sig = 1

    for i in range(1, len(df)):
        pb = df["Price_base"].iloc[i]
        sma = df["SMA"].iloc[i]
        p_bear = df["Price_bear"].iloc[i]
        
        # 趨勢判定
        trend = 1 if pb > sma else -1
        
        if trend == 1:
            current_sig = 1
            bear_entry_price = 0.0
        else:
            if current_sig == 1: # 剛跌破或之前已切回
                current_sig = -1
                bear_entry_price = p_bear
            elif current_sig == -1: # 持有反一中，檢查提前轉向
                profit = (p_bear / bear_entry_price) - 1
                if profit >= bear_target:
                    current_sig = 1
                    early_exit_flags[i] = True
        
        signals[i] = current_sig

    df["Signal"] = signals
    df["Early_Exit"] = early_exit_flags
    
    # 報酬率計算
    df["Ret_bull"] = df["Price_bull"].pct_change().fillna(0)
    df["Ret_bear"] = df["Price_bear"].pct_change().fillna(0)
    
    df["Strategy_Ret"] = 0.0
    for i in range(1, len(df)):
        # 實務上用昨日訊號決定今日報酬
        s = df["Signal"].iloc[i-1]
        df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bull"].iloc[i] if s == 1 else df["Ret_bear"].iloc[i]

    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_0050"] = (1 + df["Price_base"].pct_change().fillna(0)).cumprod()
    df["Equity_Bull_BH"] = (1 + df["Ret_bull"]).cumprod()
    
    # 圖表用的百分比
    df["Cum_Bull_Pct"] = (df["Price_bull"] / df["Price_bull"].iloc[0] - 1)
    df["Cum_Bear_Pct"] = (df["Price_bear"] / df["Price_bear"].iloc[0] - 1)

    ###############################################################
    # 5. 視覺化：分開的兩張雙軸圖表
    ###############################################################
    st.markdown("### 📌 策略訊號與累積報酬 (雙軸對照)")
    
    # 第一張：0050 vs 正2
    st.markdown("#### 1️⃣ 0050 價格 vs 00631L 累積報酬 (%)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 價格", line=dict(color="#636EFA")))
    fig1.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A")))
    fig1.add_trace(go.Scatter(x=df.index, y=df["Cum_Bull_Pct"], name="正2 報酬 (右軸)", yaxis="y2", line=dict(dash='dot', color="#00CC96")))
    
    # 標記
    bull_pts = df[(df["Signal"].diff() == 2) & (~df["Early_Exit"])]
    early_pts = df[df["Early_Exit"]]
    fig1.add_trace(go.Scatter(x=bull_pts.index, y=bull_pts["Price_base"], mode="markers", name="轉向正2", marker=dict(symbol="triangle-up", size=10, color="green")))
    fig1.add_trace(go.Scatter(x=early_pts.index, y=early_pts["Price_base"], mode="markers", name="⭐ 提前轉向", marker=dict(symbol="star", size=12, color="gold")))

    fig1.update_layout(template="plotly_white", yaxis2=dict(overlaying="y", side="right", tickformat=".0%"))
    st.plotly_chart(fig1, use_container_width=True)

    # 第二張：0050 vs 反一
    st.markdown("#### 2️⃣ 0050 價格 vs 00632R 累積報酬 (%)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 價格", line=dict(color="#636EFA")))
    fig2.add_trace(go.Scatter(x=df.index, y=df["Cum_Bear_Pct"], name="反一 報酬 (右軸)", yaxis="y2", line=dict(dash='dashdot', color="#EF553B")))
    
    bear_pts = df[df["Signal"].diff() == -2]
    fig2.add_trace(go.Scatter(x=bear_pts.index, y=bear_pts["Price_base"], mode="markers", name="轉向反一", marker=dict(symbol="triangle-down", size=10, color="red")))
    
    fig2.update_layout(template="plotly_white", yaxis2=dict(overlaying="y", side="right", tickformat=".0%"))
    st.plotly_chart(fig2, use_container_width=True)

    ###############################################################
    # 6. 高級比較表格
    ###############################################################
    st.markdown("### 🏆 策略指標深度對比")
    years = (df.index[-1] - df.index[0]).days / 365
    
    def get_stats(eq, rets):
        f_ret = eq.iloc[-1] - 1
        cagr = (1 + f_ret)**(1/years) - 1 if years > 0 else 0
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else 0
        return [eq.iloc[-1]*capital, f_ret, cagr, calmar, mdd, vol, sharpe, sortino]

    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    data = {
        "多空切換策略": get_stats(df["Equity_Strategy"], df["Strategy_Ret"]),
        "0050 B&H": get_stats(df["Equity_0050"], df["Price_base"].pct_change()),
        "正2 B&H": get_stats(df["Equity_Bull_BH"], df["Ret_bull"])
    }
    
    df_compare = pd.DataFrame(data, index=metrics)
    
    # 生成帶有 🏆 的 HTML 表格
    html = "<style>.win{font-weight:bold; color:#d4af37;} table{width:100%; border-collapse:collapse;} td,th{padding:10px; border-bottom:1px solid #eee; text-align:center;}</style><table><tr><th>指標</th>"
    for col in df_compare.columns: html += f"<th>{col}</th>"
    html += "</tr>"
    
    for metric in metrics:
        row = df_compare.loc[metric]
        is_inv = metric in ["最大回撤 (MDD)", "年化波動"]
        best = min(row) if is_inv else max(row)
        html += f"<tr><td style='text-align:left'>{metric}</td>"
        for val in row:
            if "資產" in metric: dv = fmt_money(val)
            elif "Ratio" in metric or "Sharpe" in metric or "Sortino" in metric: dv = fmt_num(val)
            else: dv = fmt_pct(val)
            
            if val == best: html += f"<td class='win'>{dv} 🏆</td>"
            else: html += f"<td>{dv}</td>"
        html += "</tr>"
    html += "</table>"
    st.write(html, unsafe_allow_html=True)

    st.download_button("📥 下載完整回測數據", df.to_csv().encode('utf-8-sig'), "backtest.csv")
