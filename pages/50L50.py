###############################################################
# app.py — 50/50 策略回測系統 (總曝險回撤視角版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 1. 頁面設定與高級 CSS 樣式
###############################################################

st.set_page_config(
    page_title="50/50 策略回測 | 倉鼠量化戰情室",
    page_icon="⚖️",
    layout="wide",
)

# 自定義 K-PI 與表格樣式
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
    .kpi-label { font-size: 0.9rem; color: #666; margin-bottom: 8px; }
    .kpi-value { font-size: 1.8rem; font-weight: 800; color: #1E1E1E; }
    
    .comp-table { width: 100%; border-collapse: collapse; margin-top: 20px; font-family: 'Noto Sans TC', sans-serif; }
    .comp-table th { background: #f8f9fa; padding: 15px; text-align: center; border-bottom: 2px solid #dee2e6; color: #495057; }
    .comp-table td { padding: 12px; border-bottom: 1px solid #eee; text-align: center; color: #212529; }
    .win-cell { color: #28a745; font-weight: bold; background: #f4fff6; }
    .metric-name { text-align: left !important; font-weight: 500; background: #fcfcfc; width: 25%; }
</style>
""", unsafe_allow_html=True)

###############################################################
# 2. 工具函式
###############################################################

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    # 支援 Close 或 Adj Close
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[col]].rename(columns={col: "Price"})

def calc_metrics(series: pd.Series):
    """計算風險指標"""
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

###############################################################
# 3. 核心回測引擎 (50/50 總曝險邏輯)
###############################################################

def run_5050_backtest(df, initial_capital, freq_code):
    """
    freq_code: 'M', 'Q', '6M', 'A' 或 None
    """
    # 初始分配：50萬現金, 50萬股票
    cash = initial_capital * 0.5
    shares = (initial_capital * 0.5) / df["Price_lev"].iloc[0]
    
    history = []
    reb_dates = df.resample(freq_code).last().index if freq_code else []
    
    for i in range(len(df)):
        date = df.index[i]
        p_lev = df["Price_lev"].iloc[i]
        
        # 當日資產狀態
        stock_val = shares * p_lev
        total_val = cash + stock_val
        
        # 紀錄歷史數據 (用於繪圖與 MDD)
        history.append({
            "Date": date,
            "Total_Equity": total_val,
            "Cash_Component": cash,
            "Stock_Component": stock_val,
            "Actual_Lev_Ratio": stock_val / total_val if total_val > 0 else 0
        })
        
        # 判斷是否執行再平衡
        if freq_code and date in reb_dates and i < len(df) - 1:
            cash = total_val * 0.5
            shares = (total_val * 0.5) / p_lev
            
    res_df = pd.DataFrame(history).set_index("Date")
    return res_df

###############################################################
# 4. UI 介面設計
###############################################################

st.markdown("<h1 style='color: #1E1E1E;'>📊 50/50 再平衡策略回測</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ 參數設定")
    base_ticker = st.selectbox("基準原型 ETF (0050)", ["0050.TW", "006208.TW"], index=0)
    lev_ticker = st.selectbox("配置槓桿 ETF (正2)", ["00631L.TW", "00675L.TW", "00663L.TW"], index=0)
    
    capital = st.number_input("初始投入總本金", 100000, 10000000, 1000000, step=100000)
    
    reb_option = st.selectbox("再平衡頻率", 
                            ["None (不進行再平衡)", "Monthly (每月)", "Quarterly (每季)", "Semi-Annually (每半年)", "Annually (每年)"],
                            index=1)
    
    start_d = st.date_input("回測開始日期", dt.date(2015, 1, 1))
    end_d = st.date_input("回測結束日期", dt.date.today())

freq_map = {
    "None (不進行再平衡)": None, "Monthly (每月)": "M", "Quarterly (每季)": "Q", 
    "Semi-Annually (每半年)": "6M", "Annually (每年)": "A"
}

###############################################################
# 5. 執行回測與呈現
###############################################################

if st.button("開始跑回測 🚀"):
    with st.spinner("正在讀取數據並計算中..."):
        df_base_raw = load_csv(base_ticker)
        df_lev_raw = load_csv(lev_ticker)

        if df_base_raw.empty or df_lev_raw.empty:
            st.error("找不到 CSV 資料，請檢查 data/ 資料夾。")
            st.stop()

        # 合併與對齊日期
        df = pd.merge(df_base_raw.rename(columns={"Price": "Price_base"}),
                      df_lev_raw.rename(columns={"Price": "Price_lev"}),
                      left_index=True, right_index=True, how="inner")
        df = df.loc[start_d:end_d]

        # 執行策略
        strategy_res = run_5050_backtest(df, capital, freq_map[reb_option])
        
        # 基準策略 (0050 B&H)
        df["Equity_Base"] = (capital / df["Price_base"].iloc[0]) * df["Price_base"]
        df["Equity_Strategy"] = strategy_res["Total_Equity"]

    # --- A. 策略訊號與執行價格 (雙軸對照) ---
    st.markdown("<h3>📌 策略訊號與價格對照</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_ticker} (左軸)", line=dict(color='#636EFA', width=2)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_ticker} (右軸)", yaxis="y2", line=dict(color='#00CC96', width=1, dash='dot')))
    
    # 若有再平衡，標記日期
    f_code = freq_map[reb_option]
    if f_code:
        reb_pts = df.resample(f_code).last().index
        reb_pts = [d for d in reb_pts if d in df.index]
        fig_price.add_trace(go.Scatter(x=reb_pts, y=df.loc[reb_pts, "Price_base"], mode="markers", 
                                       name="再平衡校準點", marker=dict(symbol="diamond", size=10, color="#FFA15A")))

    fig_price.update_layout(template="plotly_white", hovermode="x unified",
                            yaxis=dict(title="原型 ETF 價格"),
                            yaxis2=dict(title="槓桿 ETF 價格", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig_price, use_container_width=True)

    # --- B. 資金曲線與風險解析 ---
    st.markdown("<h3>📊 資金曲線與總曝險回撤解析</h3>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["資金曲線 (Equity)", "總曝險回撤 (Drawdown)", "資產組成變化"])
    
    with tab1:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name=f"50/50 ({reb_option})", line=dict(color='#FF4B4B', width=3)))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Base"], name=f"{base_ticker} 買進持有", line=dict(color='#1C83E1', width=2)))
        fig_eq.update_layout(template="plotly_white", yaxis_title="總資產價值 (TWD)")
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab2:
        # 重要：回撤是基於 (現金+股票) 的總價值
        dd_strat = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1) * 100
        dd_base = (df["Equity_Base"] / df["Equity_Base"].cummax() - 1) * 100
        
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="50/50 總資產回撤", fill='tozeroy', line=dict(color='#EF553B')))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="0050 全倉回撤", line=dict(color='#636EFA')))
        fig_dd.update_layout(template="plotly_white", yaxis_title="回撤幅度 (%)")
        st.plotly_chart(fig_dd, use_container_width=True)
        
    with tab3:
        # 顯示現金與股票的堆疊比例
        
        fig_stack = go.Figure()
        fig_stack.add_trace(go.Scatter(x=strategy_res.index, y=strategy_res["Cash_Component"], name="現金部位", stackgroup='one', fillcolor='rgba(200, 200, 200, 0.5)', line=dict(width=0)))
        fig_stack.add_trace(go.Scatter(x=strategy_res.index, y=strategy_res["Stock_Component"], name="正2 部位", stackgroup='one', fillcolor='rgba(255, 161, 90, 0.7)', line=dict(width=0)))
        fig_stack.update_layout(template="plotly_white", yaxis_title="資產組成 (元)", hovermode="x unified")
        st.plotly_chart(fig_stack, use_container_width=True)

    # --- C. 比較表格 ---
    def get_summary(eq_series):
        final = eq_series.iloc[-1]
        ret = (final / capital) - 1
        yrs = max((eq_series.index[-1] - eq_series.index[0]).days / 365, 0.1)
        cagr = (final / capital) ** (1/yrs) - 1
        mdd = (eq_series / eq_series.cummax() - 1).min()
        vol, sharpe, sortino = calc_metrics(eq_series)
        return [final, ret, cagr, mdd, vol, sharpe, sortino]

    s_strat = get_summary(df["Equity_Strategy"])
    s_base = get_summary(df["Equity_Base"])

    metrics_list = ["期末資產", "累積報酬率", "年化報酬 (CAGR)", "最大回撤 (MDD)", "年化波動率", "夏普比率 (Sharpe)", "索提諾比率 (Sortino)"]
    
    html_code = f"""
    <table class="comp-table">
        <thead>
            <tr>
                <th class="metric-name">比較指標 (以總曝險 {capital:,.0f} 為分母)</th>
                <th>50/50 策略 ({reb_option})</th>
                <th>{base_ticker} 買進持有</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, m in enumerate(metrics_list):
        v1, v2 = s_strat[i], s_base[i]
        
        # 判斷贏家
        if m in ["最大回撤 (MDD)", "年化波動率"]:
            win1 = v1 > v2 # 因為是負數，大於代表跌得少；或波動小
            d1, d2 = fmt_pct(v1), fmt_pct(v2)
        elif m == "期末資產":
            win1 = v1 > v2
            d1, d2 = fmt_money(v1), fmt_money(v2)
        elif m in ["夏普比率 (Sharpe)", "索提諾比率 (Sortino)"]:
            win1 = v1 > v2
            d1, d2 = fmt_num(v1), fmt_num(v2)
        else:
            win1 = v1 > v2
            d1, d2 = fmt_pct(v1), fmt_pct(v2)
            
        c1 = "class='win-cell'" if win1 else ""
        html_code += f"<tr><td class='metric-name'>{m}</td><td {c1}>{d1}</td><td>{d2}</td></tr>"

    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)

    st.info(f"💡 註：最大回撤 (MDD) 計算方式為：(當日總資產 / 歷史最高總資產) - 1。在 50/50 策略中，現金部位有效稀釋了槓桿 ETF 的波動。")
