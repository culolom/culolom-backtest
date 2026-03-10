###############################################################
# app.py — 50/50 策略回測：再平衡 vs 不平衡 (倉鼠量化戰情室版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 基礎設定 ---
st.set_page_config(page_title="50/50 再平衡 vs 不平衡", page_icon="⚖️", layout="wide")

st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 50/50 策略回測：再平衡 vs 不平衡</h1>", unsafe_allow_html=True)
st.markdown("""
<b>功能升級：</b> 現在你可以比較「定期再平衡」與「完全不平衡」的差異。<br>
當你不進行再平衡時，隨著正2 上漲，你的實際曝險比例會逐漸失控。
""", unsafe_allow_html=True)

DATA_DIR = Path("data")

# --- 工具函式 ---
def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    return df[["Close"]]

def calc_metrics(series: pd.Series):
    daily_rets = series.pct_change().dropna()
    if len(daily_rets) <= 1: return 0, 0, 0
    vol = daily_rets.std() * np.sqrt(252)
    sharpe = (daily_rets.mean() / daily_rets.std()) * np.sqrt(252) if daily_rets.std() > 0 else 0
    downside = daily_rets[daily_rets < 0].std()
    sortino = (daily_rets.mean() / downside) * np.sqrt(252) if downside > 0 else 0
    return vol, sharpe, sortino

# 格式化
fmt_money = lambda v: f"{v:,.0f} 元"
fmt_pct = lambda v: f"{v*100:.2f}%"
fmt_num = lambda v: f"{v:.2f}"

# --- UI 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 設定參數")
    base_etf = st.selectbox("原型 ETF (基準)", ["0050.TW", "006208.TW"])
    lev_etf = st.selectbox("槓桿 ETF (配置標的)", ["00631L.TW", "00675L.TW"])
    
    capital = st.number_input("初始本金", 100000, 10000000, 1000000, step=100000)
    
    # 加入 "不進行再平衡" 的選項
    reb_freq = st.selectbox("再平衡頻率", 
                            ["None (不進行再平衡)", "Monthly (每月)", "Quarterly (每季)", "Semi-Annually (每半年)", "Annually (每年)"],
                            index=1)
    
    start_date = st.date_input("回測開始", dt.date(2015, 1, 1))
    end_date = st.date_input("回測結束", dt.date.today())

freq_map = {
    "None (不進行再平衡)": None,
    "Monthly (每月)": "M", 
    "Quarterly (每季)": "Q", 
    "Semi-Annually (每半年)": "6M", 
    "Annually (每年)": "A"
}

# --- 核心邏輯 ---
if st.button("開始計算策略 🚀"):
    df_base = load_csv(base_etf)
    df_lev = load_csv(lev_etf)

    if df_base.empty or df_lev.empty:
        st.error("資料讀取失敗。")
        st.stop()

    df = pd.merge(df_base.rename(columns={'Close': 'Price_base'}), 
                  df_lev.rename(columns={'Close': 'Price_lev'}), 
                  left_index=True, right_index=True)
    df = df.loc[start_date:end_date]
    
    # 1. 50/50 策略運算 (含再平衡與不平衡邏輯)
    f_code = freq_map[reb_freq]
    cash = capital * 0.5
    shares = (capital * 0.5) / df["Price_lev"].iloc[0]
    
    portfolio_values = []
    signals = [0] * len(df)
    
    # 如果有設定頻率，則抓取日期，否則為空
    reb_dates = df.resample(f_code).last().index if f_code else []
    
    for i in range(len(df)):
        current_date = df.index[i]
        price_lev = df["Price_lev"].iloc[i]
        
        # 今日市值
        total_val = cash + (shares * price_lev)
        portfolio_values.append(total_val)
        
        # 執行再平衡邏輯 (只有在 f_code 存在且日期匹配時)
        if f_code and current_date in reb_dates and i < len(df)-1:
            cash = total_val * 0.5
            shares = (total_val * 0.5) / price_lev
            signals[i] = 1

    df["Equity_Strategy"] = portfolio_values
    df["Reb_Signal"] = signals
    
    # 2. 基準策略 (0050 B&H)
    df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]

    # --- A. 策略訊號與執行價格 (雙軸對照) ---
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_etf} (左軸)", line=dict(color='#636EFA')))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_etf} (右軸)", yaxis="y2", line=dict(color='#00CC96', dash='dot')))
    
    if f_code:
        reb_points = df[df["Reb_Signal"] == 1]
        fig_price.add_trace(go.Scatter(x=reb_points.index, y=reb_points["Price_base"], mode="markers", 
                                       name="再平衡執行點", marker=dict(symbol="diamond", size=10, color="orange")))
    else:
        st.info("💡 目前設定為「不進行再平衡」，圖中不會出現校準訊號點。")

    fig_price.update_layout(template="plotly_white", hovermode="x unified",
                            yaxis=dict(title="原型價格"),
                            yaxis2=dict(title="槓桿價格", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_price, use_container_width=True)

    # --- B. 資金曲線與風險解析 ---
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["資金曲線", "回撤深度"])
    
    with tab1:
        fig_eq = go.Figure()
        # 
        label_text = f"50/50 ({reb_freq})"
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name=label_text, fill='tozeroy'))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"], name=f"{base_etf} 持有"))
        fig_eq.update_layout(template="plotly_white", yaxis_title="資產價值")
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab2:
        dd_strat = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略回撤", fill='tozeroy'))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name=f"{base_etf} 回撤"))
        fig_dd.update_layout(template="plotly_white", yaxis_title="回撤 %")
        st.plotly_chart(fig_dd, use_container_width=True)

    # --- C. 比較表格 ---
    def get_stats(eq_series):
        final = eq_series.iloc[-1]
        total_ret = (final / capital) - 1
        years = max((eq_series.index[-1] - eq_series.index[0]).days / 365, 0.1)
        cagr = (final / capital) ** (1/years) - 1
        mdd = (eq_series / eq_series.cummax() - 1).min()
        vol, sharpe, sortino = calc_metrics(eq_series)
        return [final, total_ret, cagr, mdd, vol, sharpe, sortino]

    stats_strat = get_stats(df["Equity_Strategy"])
    stats_base = get_stats(df["Equity_Base"])

    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    html_table = f"""
    <style>
        .comp-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-family: sans-serif; }}
        .comp-table th {{ background: #f0f2f6; padding: 12px; text-align: center; border: 1px solid #ddd; }}
        .comp-table td {{ padding: 12px; border: 1px solid #ddd; text-align: center; }}
        .win-cell {{ color: #21c354; font-weight: bold; background: #f9fffb; }}
    </style>
    <table class="comp-table">
        <thead><tr><th>比較指標</th><th>{label_text}</th><th>{base_etf} 買進持有</th></tr></thead>
        <tbody>
    """
    
    for i, m in enumerate(metrics):
        val1, val2 = stats_strat[i], stats_base[i]
        
        # 贏家判定邏輯
        is_win = False
        if m in ["最大回撤 (MDD)", "年化波動"]:
            is_win = val1 > val2 # 因為是負數或需要更小
            d1, d2 = fmt_pct(val1), fmt_pct(val2)
        elif m == "期末資產":
            is_win = val1 > val2
            d1, d2 = fmt_money(val1), fmt_money(val2)
        elif m in ["Sharpe Ratio", "Sortino Ratio"]:
            is_win = val1 > val2
            d1, d2 = fmt_num(val1), fmt_num(val2)
        else:
            is_win = val1 > val2
            d1, d2 = fmt_pct(val1), fmt_pct(val2)
            
        w_class = "win-cell" if is_win else ""
        html_table += f"<tr><td>{m}</td><td class='{w_class}'>{d1}</td><td>{d2}</td></tr>"

    html_table += "</tbody></table>"
    st.write(html_table, unsafe_allow_html=True)
