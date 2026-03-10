###############################################################
# app.py — 50/50 策略：比例觸發再平衡 (倉鼠量化戰情室版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 基礎設定 ---
st.set_page_config(page_title="50/50 比例再平衡 | 倉鼠量化戰情室", page_icon="⚖️", layout="wide")

st.markdown("<h1 style='color: #1E1E1E;'>⚖️ 50/50 比例觸發再平衡回測</h1>", unsafe_allow_html=True)
st.markdown("""
<b>策略邏輯：</b> 初始配置 50% 正2 + 50% 現金。<br>
當正2 佔比<b>超過上限</b>（例如 70%）或<b>低於下限</b>（例如 30%）時，強制校準回 50:50。
""", unsafe_allow_html=True)

# --- 工具函式 ---
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
    mdd = (series / series.cummax() - 1).min()
    return vol, sharpe, mdd

fmt_money = lambda v: f"{v:,.0f} 元"
fmt_pct = lambda v: f"{v*100:.2f}%"
fmt_num = lambda v: f"{v:.2f}"

# --- UI 側邊欄 ---
with st.sidebar:
    st.header("🛠️ 比例觸發設定")
    base_ticker = st.selectbox("基準原型 ETF (0050)", ["0050.TW", "006208.TW"])
    lev_ticker = st.selectbox("配置槓桿 ETF (正2)", ["00631L.TW", "00675L.TW"])
    
    capital = st.number_input("初始總本金", 100000, 10000000, 1000000, step=100000)
    
    st.divider()
    st.write("📈 **再平衡區間設定**")
    upper_limit = st.slider("正2 比例上限 (%)", 55, 90, 70, help="當正2超過此比例時，賣出並收回現金")
    lower_limit = st.slider("正2 比例下限 (%)", 10, 45, 30, help="當正2低於此比例時，動用現金加碼正2")
    
    st.divider()
    start_d = st.date_input("開始日期", dt.date(2015, 1, 1))
    end_d = st.date_input("結束日期", dt.date.today())

###############################################################
# 核心引擎：比例校準邏輯
###############################################################

def run_ratio_backtest(df, initial_capital, up_pct, low_pct):
    cash = initial_capital * 0.5
    shares = (initial_capital * 0.5) / df["Price_lev"].iloc[0]
    
    history = []
    up_th = up_pct / 100.0
    low_th = low_pct / 100.0
    
    for i in range(len(df)):
        date = df.index[i]
        p_lev = df["Price_lev"].iloc[i]
        
        # 1. 每日市值計算
        stock_val = shares * p_lev
        total_val = cash + stock_val
        current_ratio = stock_val / total_val
        
        # 2. 判斷是否觸發再平衡 (比例上限或下限)
        triggered = False
        if current_ratio >= up_th or current_ratio <= low_th:
            # 執行再平衡：重新校準至 50/50
            cash = total_val * 0.5
            shares = (total_val * 0.5) / p_lev
            triggered = True
            # 更新校準後的數值
            stock_val = shares * p_lev
            current_ratio = 0.5
            
        history.append({
            "Date": date,
            "Total_Equity": total_val,
            "Cash_Component": cash,
            "Stock_Component": stock_val,
            "Ratio": current_ratio,
            "Triggered": 1 if triggered else 0
        })
        
    return pd.DataFrame(history).set_index("Date")

###############################################################
# 運算與呈現
###############################################################

if st.button("啟動量化回測 🚀"):
    df_base = load_csv(base_ticker)
    df_lev = load_csv(lev_ticker)

    if df_base.empty or df_lev.empty:
        st.error("找不到資料。")
        st.stop()

    df = pd.merge(df_base.rename(columns={"Price": "Price_base"}),
                  df_lev.rename(columns={"Price": "Price_lev"}),
                  left_index=True, right_index=True).loc[start_d:end_d]

    # 執行回測
    res = run_ratio_backtest(df, capital, upper_limit, lower_limit)
    df = pd.concat([df, res], axis=1)
    
    # 基準
    df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]

    # --- 1. 價格與觸發點 ---
    st.markdown("<h3>📌 比例觸發訊號對照</h3>", unsafe_allow_html=True)
    fig_sig = go.Figure()
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_ticker} (左軸)", line=dict(color='#636EFA')))
    fig_sig.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_ticker} (右軸)", yaxis="y2", line=dict(color='#00CC96', dash='dot', opacity=0.5)))
    
    # 標記再平衡點
    reb_pts = df[df["Triggered"] == 1]
    fig_sig.add_trace(go.Scatter(x=reb_pts.index, y=reb_pts["Price_base"], mode="markers", 
                                 name="比例觸發校準", marker=dict(symbol="star", size=12, color="gold")))

    fig_sig.update_layout(template="plotly_white", hovermode="x unified",
                          yaxis=dict(title="原型價格"), yaxis2=dict(title="槓桿價格", overlaying="y", side="right"))
    st.plotly_chart(fig_sig, use_container_width=True)

    # --- 2. 資金與回撤 ---
    st.markdown("<h3>📊 資金曲線與總曝險回撤解析</h3>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["資金曲線", "總曝險回撤", "正2 佔比變化"])
    
    with t1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Total_Equity"], name="比例觸發策略", line=dict(color='#FF4B4B', width=3)))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"], name="0050 買進持有", line=dict(color='#1C83E1')))
        st.plotly_chart(fig_eq, use_container_width=True)

    with t2:
        # 以總資產計算回撤
        dd_strat = (df["Total_Equity"] / df["Total_Equity"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略回撤", fill='tozeroy', line=dict(color='red')))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="0050 回撤", line=dict(color='blue')))
        st.plotly_chart(fig_dd, use_container_width=True)
        
    with t3:
        # 
        fig_ratio = go.Figure()
        fig_ratio.add_trace(go.Scatter(x=df.index, y=df["Ratio"]*100, name="目前正2 比例", line=dict(color='orange')))
        # 畫出上下限輔助線
        fig_ratio.add_hline(y=upper_limit, line_dash="dash", line_color="red", annotation_text="再平衡上限")
        fig_ratio.add_hline(y=lower_limit, line_dash="dash", line_color="green", annotation_text="再平衡下限")
        fig_ratio.update_layout(template="plotly_white", yaxis_title="佔比 (%)", yaxis_range=[0, 100])
        st.plotly_chart(fig_ratio, use_container_width=True)

    # --- 3. 績效表格 ---
    vol_s, shp_s, mdd_s = calc_metrics(df["Total_Equity"])
    vol_b, shp_b, mdd_b = calc_metrics(df["Equity_Base"])
    
    # 這裡的 MDD 已經是基於總曝險計算
    st.markdown(f"""
    <div style="background:#f0f2f6; padding:20px; border-radius:10px;">
        <h4 style="margin-top:0;">💡 核心數據比較 (總曝險視角)</h4>
        <table style="width:100%; text-align:center; border-collapse:collapse;">
            <tr style="border-bottom:1px solid #ccc;">
                <th>指標</th><th>比例再平衡策略 ({lower_limit}% ~ {upper_limit}%)</th><th>0050 買進持有</th>
            </tr>
            <tr><td>期末資產</td><td>{fmt_money(df["Total_Equity"].iloc[-1])}</td><td>{fmt_money(df["Equity_Base"].iloc[-1])}</td></tr>
            <tr><td>最大回撤 (MDD)</td><td style="color:red; font-weight:bold;">{fmt_pct(mdd_s)}</td><td>{fmt_pct(mdd_b)}</td></tr>
            <tr><td>年化波動率</td><td>{fmt_pct(vol_s)}</td><td>{fmt_pct(vol_b)}</td></tr>
            <tr><td>夏普比率 (Sharpe)</td><td>{fmt_num(shp_s)}</td><td>{fmt_num(shp_b)}</td></tr>
            <tr><td>再平衡執行次數</td><td colspan="2">{int(df["Triggered"].sum())} 次</td></tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
