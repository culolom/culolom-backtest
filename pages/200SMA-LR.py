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

st.set_page_config(page_title="0050 多空切換戰情室", page_icon="📈", layout="wide")

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
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

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

def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))
def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"

###############################################################
# 3. UI 介面設計
###############################################################
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 多空切換回測</h1>", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    capital = st.number_input("投入本金", 1000, 5000000, 100000, step=10000)
with col2:
    sma_window = st.number_input("均線週期 (SMA)", 10, 240, 200, step=10)
with col3:
    start_date = st.date_input("開始日期", dt.date(2020, 1, 1))
with col4:
    end_date = st.date_input("結束日期", dt.date.today())

###############################################################
# 4. 回測執行
###############################################################
if st.button("開始回測 🚀"):
    # 讀取資料
    df_base = load_csv("0050.TW")
    df_bull = load_csv("00631L.TW")
    df_bear = load_csv("00632R.TW")

    if df_base.empty or df_bull.empty or df_bear.empty:
        st.error("⚠️ 資料夾內必須包含 0050.TW, 00631L.TW, 00632R.TW 三份 CSV 檔案")
        st.stop()

    # 合併與計算
    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_bull["Price"].rename("Price_bull"), how="inner")
    df = df.join(df_bear["Price"].rename("Price_bear"), how="inner")
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start_date:end_date].dropna(subset=["SMA"])

    # 策略訊號：1=正2, -1=反1
    df["Signal"] = np.where(df["Price_base"] > df["SMA"], 1, -1)
    df["Ret_bull"] = df["Price_bull"].pct_change().fillna(0)
    df["Ret_bear"] = df["Price_bear"].pct_change().fillna(0)
    
    # 核心邏輯：用昨日訊號，決定今日報酬
    df["Strategy_Ret"] = 0.0
    for i in range(1, len(df)):
        prev_sig = df["Signal"].iloc[i-1]
        df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bull"].iloc[i] if prev_sig == 1 else df["Ret_bear"].iloc[i]

    # 計算淨值
    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_0050"] = (1 + df["Price_base"].pct_change().fillna(0)).cumprod()
    df["Equity_Bull_BH"] = (1 + df["Ret_bull"]).cumprod()

    ###############################################################
    # 5. 視覺化：雙軸圖表
    ###############################################################
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 (左軸)", line=dict(color="#636EFA", width=2)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_bull"], name="00631L (右軸)", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.4))

    # 切換點標註
    switch_to_bull = df[df["Signal"].diff() == 2]
    switch_to_bear = df[df["Signal"].diff() == -2]
    fig_price.add_trace(go.Scatter(x=switch_to_bull.index, y=switch_to_bull["Price_base"], mode="markers", name="轉向正2", marker=dict(symbol="triangle-up", size=10, color="green")))
    fig_price.add_trace(go.Scatter(x=switch_to_bear.index, y=switch_to_bear["Price_base"], mode="markers", name="轉向反1", marker=dict(symbol="triangle-down", size=10, color="red")))

    fig_price.update_layout(template="plotly_white", height=450, hovermode="x unified",
                            yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(fig_price, use_container_width=True)

    ###############################################################
    # 6. 視覺化：Tabs 解析
    ###############################################################
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_eq, tab_dd, tab_radar = st.tabs(["資金曲線", "回撤比較", "風險雷達"])
    
    with tab_eq:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="多空切換策略", line=dict(width=3)))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_0050"]-1, name="0050 B&H"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Bull_BH"]-1, name="正2 B&H"))
        fig_eq.update_layout(template="plotly_white", yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab_dd:
        dd_strat = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1) * 100
        dd_0050 = (df["Equity_0050"] / df["Equity_0050"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略回撤", fill="tozeroy", line=dict(color="red")))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_0050, name="0050 回撤"))
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        st.info("💡 雷達圖展示各策略在 CAGR、風險、Sharpe 之綜合表現")
        # 此處可依原樣板加入 radar chart 代碼

    ###############################################################
    # 7. 高級比較表格 (🏆 獎盃邏輯)
    ###############################################################
    years = (df.index[-1] - df.index[0]).days / 365
    
    def get_full_stats(eq, rets):
        f_ret = eq.iloc[-1] - 1
        cagr = (1 + f_ret)**(1/years) - 1 if years > 0 else 0
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else 0
        return [eq.iloc[-1]*capital, f_ret, cagr, calmar, mdd, vol, sharpe, sortino]

    metrics_labels = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    
    # 計算各策略數據
    data_table = {
        "多空切換策略": get_full_stats(df["Equity_Strategy"], df["Strategy_Ret"]),
        "0050 B&H": get_full_stats(df["Equity_0050"], df["Price_base"].pct_change()),
        "正2 B&H": get_full_stats(df["Equity_Bull_BH"], df["Ret_bull"])
    }
    
    df_compare = pd.DataFrame(data_table, index=metrics_labels)

    # 生成 HTML 表格
    html_table = "<style>.win{font-weight:bold; color:#d4af37;}.comp-table{width:100%; border-collapse:collapse; font-family:sans-serif;} .comp-table th, .comp-table td{padding:12px; border-bottom:1px solid #eee; text-align:center;}</style>"
    html_table += "<table class='comp-table'><tr><th>指標</th>" + "".join([f"<th>{c}</th>" for c in df_compare.columns]) + "</tr>"

    for metric in metrics_labels:
        row_vals = df_compare.loc[metric]
        # 判斷好壞 (MDD 與 波動率 越小越好，其他越大越好)
        is_invert = metric in ["最大回撤 (MDD)", "年化波動"]
        best_val = min(row_vals) if is_invert else max(row_vals)
        
        html_table += f"<tr><td style='text-align:left;'>{metric}</td>"
        for val in row_vals:
            # 格式化
            if "資產" in metric: d_val = fmt_money(val)
            elif "Ratio" in metric or "Sharpe" in metric or "Sortino" in metric: d_val = fmt_num(val)
            else: d_val = fmt_pct(val)
            
            # 標註冠軍
            if val == best_val:
                html_table += f"<td class='win'>{d_val} 🏆</td>"
            else:
                html_table += f"<td>{d_val}</td>"
        html_table += "</tr>"
    html_table += "</table>"
    
    st.write("### 🏆 策略指標深度對比")
    st.write(html_table, unsafe_allow_html=True)

    # 8. 下載與頁尾
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button("📥 下載完整回測數據 (CSV)", df.to_csv().encode('utf-8-sig'), "backtest_full.csv")
    st.markdown("<hr><div style='text-align:center; color:gray; font-size:0.8em;'>倉鼠人生實驗室 © 2026 | 投資有風險，回測僅供參考</div>", unsafe_allow_html=True)
