###############################################################
# app.py — 50/50 比例再平衡策略 (戰情室配置版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面設定與高級樣式
###############################################################

st.set_page_config(
    page_title="50/50 比例再平衡 | 倉鼠量化戰情室",
    page_icon="⚖️",
    layout="wide",
)

# 高級 CSS 樣式 (K-PI 與 表格)
st.markdown("""
<style>
    .reportview-container { background: #fdfdfd; }
    .kpi-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #eee;
        text-align: center;
    }
    .comp-table { width: 100%; border-collapse: collapse; margin-top: 20px; font-family: 'Noto Sans TC', sans-serif; }
    .comp-table th { background: #f8f9fa; padding: 15px; text-align: center; border-bottom: 2px solid #dee2e6; color: #495057; }
    .comp-table td { padding: 12px; border-bottom: 1px solid #eee; text-align: center; color: #212529; }
    .win-cell { color: #28a745; font-weight: bold; background: #f4fff6; }
    .metric-name { text-align: left !important; font-weight: 500; background: #fcfcfc; width: 30%; }
</style>
""", unsafe_allow_html=True)

###############################################################
# 2. Sidebar 側邊欄導覽 (完全照要求設定)
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

###############################################################
# 3. 主頁面標題與策略參數 (移至中間)
###############################################################

st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 50/50 比例觸發再平衡回測</h1>", unsafe_allow_html=True)

# ----------------- 策略參數開始 -----------------
st.write("### ⚙️ 策略參數設定")
p_col1, p_col2, p_col3 = st.columns(3)

with p_col1:
    base_ticker = st.selectbox("原型 ETF (0050)", ["0050.TW", "006208.TW"], index=0)
    capital = st.number_input("初始總投入本金", 100000, 10000000, 1000000, step=100000)

with p_col2:
    lev_ticker = st.selectbox("配置槓桿 ETF (正2)", ["00631L.TW", "00675L.TW"], index=0)
    start_d = st.date_input("回測開始日期", dt.date(2015, 1, 1))

with p_col3:
    rebalance_mode = st.radio("運作模式", ["比例觸發再平衡", "不進行再平衡"], horizontal=True)
    end_d = st.date_input("回測結束日期", dt.date.today())

st.write("---")
st.write("### 📈 比例再平衡區間設定")
s_col1, s_col2 = st.columns(2)

with s_col1:
    upper_limit = st.slider("正2 比例上限 (%)", 51, 95, 70, disabled=(rebalance_mode == "不進行再平衡"))
    st.caption("當正2價值超過總資產此比例時，賣出並收回現金。")

with s_col2:
    lower_limit = st.slider("正2 比例下限 (%)", 5, 49, 30, disabled=(rebalance_mode == "不進行再平衡"))
    st.caption("當正2價值低於總資產此比例時，動用現金買入正2。")

# ----------------- 策略參數結束 -----------------

###############################################################
# 4. 工具函式與核心引擎
###############################################################

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[col]].rename(columns={col: "Price"})

def calc_metrics(series: pd.Series):
    daily_rets = series.pct_change().dropna()
    if len(daily_rets) <= 1: return 0, 0, 0
    vol = daily_rets.std() * np.sqrt(252)
    sharpe = (daily_rets.mean() / daily_rets.std()) * np.sqrt(252) if daily_rets.std() > 0 else 0
    rolling_max = series.cummax()
    mdd = (series / rolling_max - 1).min()
    return vol, sharpe, mdd

def run_5050_logic(df, initial_capital, up_pct, low_pct, mode):
    cash = initial_capital * 0.5
    shares = (initial_capital * 0.5) / df["Price_lev"].iloc[0]
    up_th = up_pct / 100.0
    low_th = low_pct / 100.0
    history = []
    
    for i in range(len(df)):
        date = df.index[i]
        p_lev = df["Price_lev"].iloc[i]
        stock_val = shares * p_lev
        total_val = cash + stock_val
        current_ratio = stock_val / total_val
        
        triggered = False
        if mode == "比例觸發再平衡":
            if current_ratio >= up_th or current_ratio <= low_th:
                cash = total_val * 0.5
                shares = (total_val * 0.5) / p_lev
                triggered = True
                stock_val = shares * p_lev
                current_ratio = 0.5
            
        history.append({
            "Date": date, "Total_Equity": total_val, "Cash": cash, "Stock": stock_val,
            "Ratio": current_ratio, "Triggered": 1 if triggered else 0
        })
    return pd.DataFrame(history).set_index("Date")

###############################################################
# 5. 回測啟動
###############################################################

if st.button("開始回測 🚀", use_container_width=True):
    df_base = load_csv(base_ticker)
    df_lev = load_csv(lev_ticker)

    if df_base.empty or df_lev.empty:
        st.error("⚠️ 請確保 data/ 資料夾內有對應的 CSV 檔案。")
        st.stop()

    df = pd.merge(df_base.rename(columns={"Price": "Price_base"}),
                  df_lev.rename(columns={"Price": "Price_lev"}),
                  left_index=True, right_index=True).loc[start_d:end_d]

    res = run_5050_logic(df, capital, upper_limit, lower_limit, rebalance_mode)
    df = pd.concat([df, res], axis=1)
    df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]

    # --- A. 訊號與價格對照 ---
    st.markdown("<h3>📌 策略訊號與價格對照</h3>", unsafe_allow_html=True)
    fig_sig = go.Figure()
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_ticker}", line=dict(color='#636EFA', width=2)))
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_ticker} (右軸)", yaxis="y2", opacity=0.4, line=dict(color='#00CC96', dash='dot')))
    
    reb_pts = df[df["Triggered"] == 1]
    if not reb_pts.empty:
        fig_sig.add_trace(go.Scatter(x=reb_pts.index, y=reb_pts["Price_base"], mode="markers", 
                                     name="觸發再平衡", marker=dict(symbol="star", size=12, color="gold", line=dict(width=1, color="black"))))

    fig_sig.update_layout(template="plotly_white", hovermode="x unified",
                          yaxis=dict(title="原型價格"), yaxis2=dict(title="槓桿價格", overlaying="y", side="right", showgrid=False),
                          legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig_sig, use_container_width=True)

    # --- B. 資金與回撤解析 ---
    st.markdown("<h3>📊 總曝險回撤與資產成長</h3>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["資金曲線 (Equity)", "總曝險回撤 (Drawdown)", "正2 佔比變化軌道"])
    
    with t1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Total_Equity"], name="50/50 策略", line=dict(color='#FF4B4B', width=3)))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"], name="0050 買進持有", line=dict(color='#1C83E1')))
        st.plotly_chart(fig_eq, use_container_width=True)

    with t2:
        # 總曝險視角回撤
        dd_strat = (df["Total_Equity"] / df["Total_Equity"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略總資產回撤", fill='tozeroy', line=dict(color='#EF553B')))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="0050 回撤", line=dict(color='#636EFA')))
        st.plotly_chart(fig_dd, use_container_width=True)
        
    with t3:
        # 
        fig_ratio = go.Figure()
        fig_ratio.add_trace(go.Scatter(x=df.index, y=df["Ratio"]*100, name="目前正2 佔比", line=dict(color='#FFA15A', width=2)))
        fig_ratio.add_hline(y=upper_limit, line_dash="dash", line_color="red", annotation_text=f"上限 {upper_limit}%")
        fig_ratio.add_hline(y=lower_limit, line_dash="dash", line_color="green", annotation_text=f"下限 {lower_limit}%")
        fig_ratio.update_layout(template="plotly_white", yaxis_title="佔比 (%)", yaxis_range=[0, 100])
        st.plotly_chart(fig_ratio, use_container_width=True)

    # --- C. 績效比較表格 ---
    vol_s, shp_s, mdd_s = calc_metrics(df["Total_Equity"])
    vol_b, shp_b, mdd_b = calc_metrics(df["Equity_Base"])
    years = max((df.index[-1] - df.index[0]).days / 365, 0.1)
    cagr_s = (df["Total_Equity"].iloc[-1] / capital) ** (1/years) - 1
    cagr_b = (df["Equity_Base"].iloc[-1] / capital) ** (1/years) - 1

    fmt_money = lambda v: f"{v:,.0f} 元"
    fmt_pct = lambda v: f"{v*100:.2f}%"
    fmt_num = lambda v: f"{v:.2f}"

    metrics_map = [
        ("期末資產", df["Total_Equity"].iloc[-1], df["Equity_Base"].iloc[-1], fmt_money),
        ("年化報酬 (CAGR)", cagr_s, cagr_b, fmt_pct),
        ("最大回撤 (MDD)", mdd_s, mdd_b, fmt_pct),
        ("年化波動率", vol_s, vol_b, fmt_pct),
        ("夏普比率 (Sharpe)", shp_s, shp_b, fmt_num),
    ]

    html_table = f"""
    <table class="comp-table">
        <thead><tr><th class="metric-name">比較指標</th><th>50/50 策略 ({rebalance_mode})</th><th>{base_ticker} 買進持有</th></tr></thead>
        <tbody>
    """
    for label, v1, v2, func in metrics_map:
        win = v1 > v2 # 對 MDD 和 波動率來說，大於代表跌幅小/波動小，語意正確
        w_class = "class='win-cell'" if win else ""
        html_table += f"<tr><td class='metric-name'>{label}</td><td {w_class}>{func(v1)}</td><td>{func(v2)}</td></tr>"
    html_table += f"<tr><td class='metric-name'>再平衡執行總次數</td><td colspan='2' style='font-weight:bold;'>{int(df['Triggered'].sum())} 次</td></tr></tbody></table>"
    st.write(html_table, unsafe_allow_html=True)
