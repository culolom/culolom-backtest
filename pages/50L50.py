###############################################################
# app.py — 50/50 再平衡策略回測系統 (倉鼠量化戰情室版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面與字型初步設定
###############################################################

st.set_page_config(page_title="50/50 再平衡回測", page_icon="⚖️", layout="wide")

st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 50/50 再平衡策略回測</h1>", unsafe_allow_html=True)
st.markdown("""
本工具模擬 **50% 槓桿 ETF + 50% 現金** 的配置，並在固定週期進行強制比例校準（再平衡）。<br>
觀察在不同市場循環下，再平衡如何透過「高賣低買」降低回撤並提升效率。
""", unsafe_allow_html=True)

DATA_DIR = Path("data")

###############################################################
# 2. 工具函式 (保留原本架構)
###############################################################

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

# 格式化工具
fmt_money = lambda v: f"{v:,.0f} 元"
fmt_pct = lambda v: f"{v*100:.2f}%"
fmt_num = lambda v: f"{v:.2f}"

###############################################################
# 3. UI 輸入區
###############################################################

with st.sidebar:
    st.header("⚙️ 設定參數")
    base_etf = st.selectbox("原型 ETF (基準)", ["0050.TW", "006208.TW"])
    lev_etf = st.selectbox("槓桿 ETF (配置標的)", ["00631L.TW", "00675L.TW", "00663L.TW"])
    
    capital = st.number_input("初始本金", 100000, 10000000, 1000000, step=100000)
    reb_freq = st.selectbox("再平衡頻率", 
                            ["Monthly (每月)", "Quarterly (每季)", "Semi-Annually (每半年)", "Annually (每年)"],
                            index=0)
    
    start_date = st.date_input("回測開始", dt.date(2015, 1, 1))
    end_date = st.date_input("回測結束", dt.date.today())

freq_map = {"Monthly (每月)": "M", "Quarterly (每季)": "Q", "Semi-Annually (每半年)": "6M", "Annually (每年)": "A"}

###############################################################
# 4. 核心回測邏輯
###############################################################

if st.button("開始計算策略 🚀"):
    df_base = load_csv(base_etf)
    df_lev = load_csv(lev_etf)

    if df_base.empty or df_lev.empty:
        st.error("資料讀取失敗，請確認 data 目錄下的 CSV 檔。")
        st.stop()

    # 合併數據
    df = pd.merge(df_base.rename(columns={'Close': 'Price_base'}), 
                  df_lev.rename(columns={'Close': 'Price_lev'}), 
                  left_index=True, right_index=True)
    df = df.loc[start_date:end_date]
    
    # --- 50/50 策略運算 ---
    f_code = freq_map[reb_freq]
    reb_dates = df.resample(f_code).last().index
    
    cash = capital * 0.5
    shares = (capital * 0.5) / df["Price_lev"].iloc[0]
    
    portfolio_values = []
    signals = [0] * len(df) # 1 代表再平衡日
    
    for i in range(len(df)):
        current_date = df.index[i]
        price_lev = df["Price_lev"].iloc[i]
        
        # 今日市值
        total_val = cash + (shares * price_lev)
        portfolio_values.append(total_val)
        
        # 再平衡觸發
        if current_date in reb_dates and i < len(df)-1:
            cash = total_val * 0.5
            shares = (total_val * 0.5) / price_lev
            signals[i] = 1

    df["Equity_5050"] = portfolio_values
    df["Reb_Signal"] = signals
    
    # 基準策略 (0050 B&H)
    df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]

    ###############################################################
    # 5. 視覺化：策略訊號與執行價格 (雙軸對照)
    ###############################################################
    
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    # 左軸：基準價格
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_etf} (左軸)", line=dict(color='#636EFA')))
    # 右軸：槓桿價格
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_etf} (右軸)", yaxis="y2", line=dict(color='#00CC96', dash='dot')))
    
    # 標記再平衡點
    reb_points = df[df["Reb_Signal"] == 1]
    fig_price.add_trace(go.Scatter(x=reb_points.index, y=reb_points["Price_base"], mode="markers", 
                                   name="再平衡執行點", marker=dict(symbol="diamond", size=10, color="orange")))

    fig_price.update_layout(template="plotly_white", hovermode="x unified",
                            yaxis=dict(title="原型價格"),
                            yaxis2=dict(title="槓桿價格", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # 6. 視覺化：資金曲線與風險解析
    ###############################################################
    
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["資金曲線 (Equity Curve)", "回撤深度 (Drawdown)"])
    
    with tab1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_5050"], name="50/50 策略", fill='tozeroy'))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"], name=f"{base_etf} 持有"))
        fig_eq.update_layout(template="plotly_white", yaxis_title="資產價值")
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab2:
        dd_5050 = (df["Equity_5050"] / df["Equity_5050"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_5050, name="50/50 回撤", fill='tozeroy'))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name=f"{base_etf} 回撤"))
        fig_dd.update_layout(template="plotly_white", yaxis_title="回撤 %")
        st.plotly_chart(fig_dd, use_container_width=True)

    ###############################################################
    # 7. 績效比較表格 (HTML 版)
    ###############################################################
    
    def get_stats(eq_series):
        final = eq_series.iloc[-1]
        total_ret = (final / capital) - 1
        years = (eq_series.index[-1] - eq_series.index[0]).days / 365
        cagr = (final / capital) ** (1/years) - 1
        mdd = (eq_series / eq_series.cummax() - 1).min()
        vol, sharpe, sortino = calc_metrics(eq_series)
        return [final, total_ret, cagr, mdd, vol, sharpe, sortino]

    stats_5050 = get_stats(df["Equity_5050"])
    stats_base = get_stats(df["Equity_Base"])

    # 渲染 HTML 表格 (沿用原本 CSS)
    metrics = ["期末資產", "總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    html_table = """
    <style>
        .comp-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-family: sans-serif; border-radius: 8px; overflow: hidden; }
        .comp-table th { background: #f0f2f6; padding: 12px; text-align: center; }
        .comp-table td { padding: 12px; border-bottom: 1px solid #eee; text-align: center; }
        .win-cell { color: #21c354; font-weight: bold; }
    </style>
    <table class="comp-table">
        <thead><tr><th>比較指標</th><th>50/50 再平衡</th><th>0050 買進持有</th></tr></thead>
        <tbody>
    """
    
    for i, m in enumerate(metrics):
        val1 = stats_5050[i]
        val2 = stats_base[i]
        
        # 簡單判定贏家 (MDD 與 波動率是越小越好)
        if m in ["最大回撤 (MDD)", "年化波動"]:
            w1 = "win-cell" if val1 > val2 else "" # 因為是負數或需要更小
            disp1, disp2 = fmt_pct(val1), fmt_pct(val2)
        elif m == "期末資產":
            w1 = "win-cell" if val1 > val2 else ""
            disp1, disp2 = fmt_money(val1), fmt_money(val2)
        elif m in ["Sharpe Ratio", "Sortino Ratio"]:
            w1 = "win-cell" if val1 > val2 else ""
            disp1, disp2 = fmt_num(val1), fmt_num(val2)
        else:
            w1 = "win-cell" if val1 > val2 else ""
            disp1, disp2 = fmt_pct(val1), fmt_pct(val2)
            
        html_table += f"<tr><td>{m}</td><td class='{w1}'>{disp1}</td><td>{disp2}</td></tr>"

    html_table += "</tbody></table>"
    st.write(html_table, unsafe_allow_html=True)
