import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面設定與樣式
###############################################################
st.set_page_config(page_title="ETF 投資大對決 (單筆 vs DCA)", page_icon="💰", layout="wide")

# 套用自定義 CSS 讓表格更漂亮
st.markdown("""
    <style>
        .pk-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 16px; border-radius: 8px; overflow: hidden; }
        .pk-table th { background-color: #262730; color: white; padding: 12px; text-align: center; }
        .pk-table td { padding: 12px; text-align: center; border-bottom: 1px solid #eee; }
        .metric-label { text-align: left !important; font-weight: bold; background-color: #f8f9fb; }
        .winner { color: #f63366; font-weight: bold; }
        .trophy { margin-left: 5px; }
    </style>
""", unsafe_allow_html=True)

###############################################################
# 2. 資料庫與工具函式
###############################################################
DATA_DIR = Path("data")
ETF_OPTIONS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "0056 元大高股息": "0056.TW",
    "00878 國泰永續高股息": "00878.TW",
    "00919 群益台灣精選高息": "00919.TW",
}

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    return df[["Close"]].rename(columns={"Close": "Price"})

def calculate_dca(price_series, monthly_investment):
    """計算定期定額邏輯"""
    # 取得每個月第一個交易日
    monthly_prices = price_series.resample('MS').first()
    shares = 0
    total_invested = 0
    portfolio_values = []
    
    # 建立一個與日線對齊的持股數 Series
    daily_shares = pd.Series(0.0, index=price_series.index)
    
    current_shares = 0
    for dateInSeries in price_series.index:
        # 如果是該月的第一個交易日(且在日線中存在)
        if dateInSeries in monthly_prices.index:
            buy_price = price_series.loc[dateInSeries]
            new_shares = monthly_investment / buy_price
            current_shares += new_shares
            total_invested += monthly_investment
        
        daily_shares.loc[dateInSeries] = current_shares
    
    equity_curve = daily_shares * price_series
    return equity_curve, total_invested

###############################################################
# 3. 側邊欄輸入
###############################################################
with st.sidebar:
    st.header("⚙️ 回測設定")
    selected_names = st.multiselect("選擇對決標的 (最多4筆)", list(ETF_OPTIONS.keys()), default=list(ETF_OPTIONS.keys())[:2])
    
    if len(selected_names) > 4:
        st.error("❌ 超過 4 筆標的會導致表格太擠，請減少選取。")
        st.stop()
        
    invest_mode = st.radio("投資模式", ["單筆投入 (Lump Sum)", "定期定額 (DCA)"])
    
    if invest_mode == "單筆投入 (Lump Sum)":
        initial_capital = st.number_input("投入本金 (元)", 10000, 10000000, 100000, 10000)
        monthly_fund = 0
    else:
        monthly_fund = st.number_input("每月投入金額 (元)", 1000, 1000000, 10000, 1000)
        initial_capital = 0

    st.divider()
    run_button = st.button("開始回測大對決 🚀", use_container_width=True)

###############################################################
# 4. 主程式執行
###############################################################
st.title("📊 ETF 單筆 vs DCA 績效大對決")

if run_button and selected_names:
    all_dfs = []
    for name in selected_names:
        df = load_csv(ETF_OPTIONS[name])
        if not df.empty:
            all_dfs.append(df.rename(columns={"Price": name}))
    
    if not all_dfs:
        st.error("找不到資料檔案，請確認 data 資料夾內有對應的 CSV。")
        st.stop()

    # 取得共同的時間區間
    df_combined = pd.concat(all_dfs, axis=1).dropna()
    start_date = df_combined.index.min()
    end_date = df_combined.index.max()
    
    st.info(f"📅 回測區間：{start_date.date()} ~ {end_date.date()} (共計 {(end_date-start_date).days // 365} 年)")

    results = {}
    fig_equity = go.Figure()

    for name in selected_names:
        prices = df_combined[name]
        
        if invest_mode == "單筆投入 (Lump Sum)":
            # 單筆投入計算
            shares = initial_capital / prices.iloc[0]
            equity = prices * shares
            cost = initial_capital
        else:
            # 定期定額計算
            equity, cost = calculate_dca(prices, monthly_fund)
        
        # 指標計算
        final_value = equity.iloc[-1]
        total_return = (final_value / cost) - 1
        mdd = (equity / equity.cummax() - 1).min()
        
        # 年化報酬 (CAGR)
        years = (end_date - start_date).days / 365.25
        cagr = (final_value / cost)**(1/years) - 1 if years > 0 else 0
        
        results[name] = {
            "累積投入本金": cost,
            "期末資產市值": final_value,
            "總報酬率": total_return,
            "年化報酬率 (CAGR)": cagr,
            "最大回撤 (MDD)": mdd,
        }
        
        fig_equity.add_trace(go.Scatter(x=equity.index, y=equity, name=name))

    # 畫圖
    fig_equity.update_layout(
        title=f"資產增長曲線 ({invest_mode})",
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="資產價值 (TWD)",
        height=500
    )
    st.plotly_chart(fig_equity, use_container_width=True)

    ###############################################################
    # 5. PK 表格渲染
    ###############################################################
    st.subheader("🏆 績效指標大對決")
    
    # 定義指標與格式
    metrics = {
        "累積投入本金": {"fmt": lambda x: f"{x:,.0f} 元", "invert": False},
        "期末資產市值": {"fmt": lambda x: f"{x:,.0f} 元", "invert": False},
        "總報酬率": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "年化報酬率 (CAGR)": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "最大回撤 (MDD)": {"fmt": lambda x: f"{x:.2%}", "invert": True}, # 越小(越接近0)越好
    }

    html_table = '<table class="pk-table"><thead><tr><th class="metric-label">指標 / 標的</th>'
    for name in selected_names:
        html_table += f'<th>{name}</th>'
    html_table += '</tr></thead><tbody>'

    for m_name, config in metrics.items():
        html_table += f'<tr><td class="metric-label">{m_name}</td>'
        
        # 找出該列贏家
        current_values = [results[n][m_name] for n in selected_names]
        if config["invert"]:
            winner_val = max(current_values) # MDD 是負數，max 是最接近 0 的
        else:
            winner_val = max(current_values)
            
        for name in selected_names:
            val = results[name][m_name]
            is_winner = (val == winner_val and len(selected_names) > 1)
            display = config["fmt"](val)
            
            if is_winner:
                html_table += f'<td><span class="winner">{display} <span class="trophy">🏆</span></span></td>'
            else:
                html_table += f'<td>{display}</td>'
        html_table += '</tr>'

    html_table += '</tbody></table>'
    st.write(html_table, unsafe_allow_html=True)

    st.caption(f"註：回測數據對齊至所有標的之共同交易日。定期定額設定為每月第一個交易日扣款。")

elif not selected_names:
    st.warning("請先在左側選取要比較的標的。")
else:
    st.info("💡 調整參數後點擊「開始回測大對決」查看結果。")
