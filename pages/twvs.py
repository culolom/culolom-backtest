import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面設定與側邊欄 (遵照指定格式)
###############################################################
st.set_page_config(page_title="ETF 單筆 vs DCA 大對決", page_icon="⚔️", layout="wide")

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>📊 ETF 單筆投入 vs 定期定額回測大對決</h1>",
    unsafe_allow_html=True,
)

###############################################################
# 2. 資料與工具函式
###############################################################
DATA_DIR = Path("data")
ETF_OPTIONS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "0056 元大高股息": "0056.TW",
    "00878 國泰永續高股息": "00878.TW",
    "2330 台積電": "2330.TW",
}

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    return df[["Close"]].rename(columns={"Close": "Price"})

def calc_risk_metrics(returns):
    """計算年化波動、夏普、索提諾"""
    if returns.empty: return 0, 0, 0
    vol = returns.std() * np.sqrt(252)
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() != 0 else 0
    
    downside_returns = returns[returns < 0]
    sortino = (returns.mean() / downside_returns.std()) * np.sqrt(252) if not downside_returns.empty and downside_returns.std() != 0 else 0
    return vol, sharpe, sortino

def calculate_dca(price_series, monthly_investment):
    """計算定期定額"""
    monthly_prices = price_series.resample('MS').first()
    current_shares = 0
    total_invested = 0
    daily_shares = pd.Series(0.0, index=price_series.index)
    
    for date in price_series.index:
        if date in monthly_prices.index:
            buy_price = price_series.loc[date]
            current_shares += (monthly_investment / buy_price)
            total_invested += monthly_investment
        daily_shares.loc[date] = current_shares
    
    equity = daily_shares * price_series
    return equity, total_invested

###############################################################
# 3. 主頁面參數設定區 (取代原本側邊欄)
###############################################################
with st.expander("🛠️ 回測參數設定", expanded=True):
    col_a, col_b = st.columns(2)
    with col_a:
        selected_names = st.multiselect("選擇對決標的 (最多4筆)", list(ETF_OPTIONS.keys()), default=list(ETF_OPTIONS.keys())[:2])
    with col_b:
        invest_mode = st.radio("投資模式", ["單筆投入 (Lump Sum)", "定期定額 (DCA)"], horizontal=True)

    col_c, col_d, col_e = st.columns(3)
    with col_c:
        if invest_mode == "單筆投入 (Lump Sum)":
            capital_input = st.number_input("投入本金 (元)", value=100000, step=10000)
        else:
            capital_input = st.number_input("每月投入金額 (元)", value=10000, step=1000)
    
    # 預先抓取時間範圍
    all_dates = []
    if selected_names:
        for name in selected_names:
            df_temp = load_csv(ETF_OPTIONS[name])
            if not df_temp.empty:
                all_dates.append(df_temp.index.min())
                all_dates.append(df_temp.index.max())
    
    if all_dates:
        min_d, max_d = min(all_dates), max(all_dates)
        with col_d:
            start_date = st.date_input("開始日期", value=min_d, min_value=min_d, max_value=max_d)
        with col_e:
            end_date = st.date_input("結束日期", value=max_d, min_value=min_d, max_value=max_d)
    
    run_btn = st.button("開始回測大對決 🚀", use_container_width=True)

###############################################################
# 4. 回測執行與呈現
###############################################################
if run_btn and selected_names:
    if len(selected_names) > 4:
        st.error("⚠️ 標的多於 4 筆會使表格顯示過擠，請重新選取。")
        st.stop()

    all_dfs = {}
    for name in selected_names:
        df = load_csv(ETF_OPTIONS[name])
        if not df.empty:
            all_dfs[name] = df.loc[str(start_date):str(end_date)]

    # 取得共同交集區間
    common_index = None
    for df in all_dfs.values():
        if common_index is None:
            common_index = df.index
        else:
            common_index = common_index.intersection(df.index)
    
    if common_index is None or common_index.empty:
        st.error("❌ 所選標的在選定時間內沒有共同交易資料。")
        st.stop()

    results = {}
    fig_equity = go.Figure()

    for name in selected_names:
        prices = all_dfs[name].loc[common_index, "Price"]
        daily_returns = prices.pct_change().fillna(0)
        
        if invest_mode == "單筆投入 (Lump Sum)":
            equity = (prices / prices.iloc[0]) * capital_input
            cost = capital_input
        else:
            equity, cost = calculate_dca(prices, capital_input)
        
        # 績效計算
        final_val = equity.iloc[-1]
        total_ret = (final_val / cost) - 1
        years = (common_index[-1] - common_index[0]).days / 365.25
        cagr = (final_val / cost)**(1/years) - 1 if years > 0 else 0
        mdd = (equity / equity.cummax() - 1).min()
        
        # 風險指標
        vol, sharpe, sortino = calc_risk_metrics(daily_returns)
        
        results[name] = {
            "累積投入本金": cost,
            "期末資產市值": final_val,
            "總報酬率": total_ret,
            "年化報酬率 (CAGR)": cagr,
            "年化波動率": vol,
            "夏普值 (Sharpe)": sharpe,
            "索提諾值 (Sortino)": sortino,
            "最大回撤 (MDD)": mdd,
        }
        fig_equity.add_trace(go.Scatter(x=equity.index, y=equity, name=name))

    st.plotly_chart(fig_equity, use_container_width=True)

    # 5. PK 表格
    st.subheader("🏆 績效指標大對決")
    metrics_def = {
        "累積投入本金": {"fmt": lambda x: f"{x:,.0f} 元", "invert": False},
        "期末資產市值": {"fmt": lambda x: f"{x:,.0f} 元", "invert": False},
        "總報酬率": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "年化報酬率 (CAGR)": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "年化波動率": {"fmt": lambda x: f"{x:.2%}", "invert": True},
        "夏普值 (Sharpe)": {"fmt": lambda x: f"{x:.2f}", "invert": False},
        "索提諾值 (Sortino)": {"fmt": lambda x: f"{x:.2f}", "invert": False},
        "最大回撤 (MDD)": {"fmt": lambda x: f"{x:.2%}", "invert": True},
    }

    html = '<style>.pk-t { width:100%; border-collapse:collapse; } .pk-t th { background:#262730; color:white; padding:10px; } .pk-t td { border-bottom:1px solid #eee; padding:10px; text-align:center; } .m-label { background:#f8f9fb; text-align:left !important; font-weight:bold; } .win { color:#f63366; font-weight:bold; }</style>'
    html += '<table class="pk-t"><thead><tr><th class="m-label">指標 / 標的</th>'
    for name in selected_names: html += f'<th>{name}</th>'
    html += '</tr></thead><tbody>'

    for m, cfg in metrics_def.items():
        vals = [results[n][m] for n in selected_names]
        best = min(vals) if cfg["invert"] else max(vals)
        html += f'<tr><td class="m-label">{m}</td>'
        for n in selected_names:
            v = results[n][m]
            is_win = (v == best and len(selected_names) > 1)
            display = cfg["fmt"](v)
            html += f'<td><span class="{"win" if is_win else ""}">{display}{" 🏆" if is_win else ""}</span></td>'
        html += '</tr>'
    html += '</tbody></table>'
    st.write(html, unsafe_allow_html=True)

elif not selected_names:
    st.info("請於上方設定標的與日期後，點擊「開始回測大對決」。")
