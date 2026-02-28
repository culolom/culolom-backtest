###############################################################
# app.py — 倉鼠量化戰情室：0050 多空切換 (反一雙重保險機制 + 單次扣打)
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

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

###############################################################
# 2. 核心工具函式
###############################################################
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

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

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

def fmt_money(v):
    try: return f"{v:,.0f} 元"
    except: return "—"

def fmt_pct(v, d=2):
    try: return f"{v:.{d}%}"
    except: return "—"

def fmt_num(v, d=2):
    try: return f"{v:.{d}f}"
    except: return "—"

###############################################################
# 3. UI 介面設計
###############################################################
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    
    st.markdown("### ⚙️ 策略參數設定")
    sma_window = st.number_input("均線週期 (SMA)", min_value=10, max_value=240, value=200, step=10)
    
    st.markdown("#### 🛡️ 反一雙重保險機制 (抄底)")
    enable_early_exit = st.toggle("啟用雙重保險", value=True)
    bear_profit_target = st.number_input("1. 反一獲利轉向點 (%)", min_value=1.0, max_value=50.0, value=10.0, step=0.5, disabled=not enable_early_exit) / 100
    sma_drop_target = st.number_input("2. 跌破均線乖離抄底 (%)", min_value=5.0, max_value=50.0, value=20.0, step=0.5, disabled=not enable_early_exit) / 100
    
    if enable_early_exit:
        st.info("💡 規則 1：買入反一後，若反一獲利達標，提前轉回正 2。\n\n💡 規則 2：0050 跌破均線過深 (乖離率達標)，提前轉回正 2 抄底。\n\n⚠️ 每次跌破 200SMA 的空頭循環中，反一最多只會買進一次。")
    
    st.divider()
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050 多空切換：反一雙重保險機制</h1>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    capital = st.number_input("投入本金 (元)", 1000, 5000000, 100000, step=10000)
with col2:
    start_date = st.date_input("開始日期", dt.date(2020, 1, 1))
with col3:
    end_date = st.date_input("結束日期", dt.date.today())

###############################################################
# 4. 回測核心邏輯
###############################################################
if st.button("開始回測 🚀"):
    
    # 讀取資料
    with st.spinner("讀取 CSV 資料中..."):
        df_base = load_csv("0050.TW")
        df_bull = load_csv("00631L.TW")
        df_bear = load_csv("00632R.TW")

    if df_base.empty or df_bull.empty or df_bear.empty:
        st.error("⚠️ 資料夾內缺失檔案！請確認 data/ 內有 0050.TW.csv, 00631L.TW.csv, 00632R.TW.csv")
        st.stop()

    # 資料合併與對齊
    df = pd.DataFrame(index=df_base.index)
    df["Price_base"] = df_base["Price"]
    df = df.join(df_bull["Price"].rename("Price_bull"), how="inner")
    df = df.join(df_bear["Price"].rename("Price_bear"), how="inner")
    
    # 計算均線
    df["SMA"] = df["Price_base"].rolling(sma_window).mean()
    df = df.loc[start_date:end_date].dropna(subset=["SMA"])

    if df.empty:
        st.error("⚠️ 選擇的日期區間內沒有足夠的有效資料進行回測。")
        st.stop()

    # --- 策略核心：訊號生成與提前轉向判斷 ---
    signals = [1] * len(df)
    is_early_exited = [0] * len(df) # 0: 正常, 1: 獲利轉向, 2: 乖離抄底
    bear_entry_price = 0.0
    current_sig = 1
    
    # 新增：記錄本次空頭循環是否已經買過反一
    has_traded_bear_in_downtrend = False 

    for i in range(1, len(df)):
        pb = df["Price_base"].iloc[i]
        sma = df["SMA"].iloc[i]
        p_bear = df["Price_bear"].iloc[i]
        
        # 基礎趨勢
        trend = 1 if pb > sma else -1
        
        if trend == 1:
            current_sig = 1
            bear_entry_price = 0.0
            has_traded_bear_in_downtrend = False # 站回均線，重置反一扣打
        else:
            if current_sig == 1: 
                # 目前持有正2，且在均線之下
                # 只有當「還沒買過反一」時，才切換到反一
                if not has_traded_bear_in_downtrend:
                    current_sig = -1
                    bear_entry_price = p_bear
                    has_traded_bear_in_downtrend = True # 用掉本次空頭的扣打
            elif current_sig == -1 and enable_early_exit:
                # 規則 1: 反一獲利達標
                profit_pct = (p_bear / bear_entry_price) - 1 if bear_entry_price > 0 else 0
                if profit_pct >= bear_profit_target:
                    current_sig = 1
                    is_early_exited[i] = 1
                # 規則 2: 0050 跌破均線過深 (乖離)
                elif pb < sma * (1 - sma_drop_target):
                    current_sig = 1
                    is_early_exited[i] = 2
        
        signals[i] = current_sig

    df["Signal"] = signals
    df["Early_Exit"] = is_early_exited
    
    # --- 報酬率與淨值計算 ---
    df["Ret_bull"] = df["Price_bull"].pct_change().fillna(0)
    df["Ret_bear"] = df["Price_bear"].pct_change().fillna(0)
    df["Strategy_Ret"] = 0.0
    
    # 避免未來函數：使用昨日收盤決定的訊號，決定今日的報酬
    for i in range(1, len(df)):
        prev_sig = df["Signal"].iloc[i-1]
        if prev_sig == 1:
            df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bull"].iloc[i]
        else:
            df.iloc[i, df.columns.get_loc("Strategy_Ret")] = df["Ret_bear"].iloc[i]

    df["Equity_Strategy"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_0050"] = (1 + df["Price_base"].pct_change().fillna(0)).cumprod()
    df["Equity_Bull_BH"] = (1 + df["Ret_bull"]).cumprod()
    
    # 圖表右軸用的累積百分比
    df["Cum_Bull_Pct"] = (df["Price_bull"] / df["Price_bull"].iloc[0] - 1)
    df["Cum_Bear_Pct"] = (df["Price_bear"] / df["Price_bear"].iloc[0] - 1)

    # 提取各類標記點位
    switch_to_bull_normal = df[(df["Signal"].diff() == 2) & (df["Early_Exit"] == 0)]
    switch_to_bear = df[df["Signal"].diff() == -2]
    early_profit_pts = df[df["Early_Exit"] == 1]
    early_drop_pts = df[df["Early_Exit"] == 2]

    ###############################################################
    # 5. 視覺化：分離式雙軸圖表
    ###############################################################
    st.markdown("---")
    st.markdown("<h3>📌 策略訊號與累積報酬 (雙軸對照)</h3>", unsafe_allow_html=True)
    
    # --- 第一張圖：0050 vs 00631L (正2) ---
    st.markdown("#### 1️⃣ 0050 價格 (左軸) vs 00631L 累積報酬 (右軸)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 價格", line=dict(color="#636EFA", width=2)))
    fig1.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)))
    fig1.add_trace(go.Scatter(x=df.index, y=df["Cum_Bull_Pct"], name="正2 累積報酬", yaxis="y2", line=dict(dash='dot', color="#00CC96"), opacity=0.4))
    
    fig1.add_trace(go.Scatter(x=switch_to_bull_normal.index, y=switch_to_bull_normal["Price_base"], mode="markers", name="趨勢轉正2", marker=dict(symbol="triangle-up", size=10, color="green")))
    if not early_profit_pts.empty:
        fig1.add_trace(go.Scatter(x=early_profit_pts.index, y=early_profit_pts["Price_base"], mode="markers", name="⭐ 反一獲利轉向", marker=dict(symbol="star", size=12, color="gold", line=dict(width=1, color="black"))))
    if not early_drop_pts.empty:
        fig1.add_trace(go.Scatter(x=early_drop_pts.index, y=early_drop_pts["Price_base"], mode="markers", name="🔥 跌深乖離抄底", marker=dict(symbol="diamond", size=10, color="red", line=dict(width=1, color="black"))))
    fig1.add_trace(go.Scatter(x=switch_to_bear.index, y=switch_to_bear["Price_base"], mode="markers", name="轉向反一", marker=dict(symbol="triangle-down", size=8, color="gray"), opacity=0.6))

    fig1.update_layout(template="plotly_white", height=450, hovermode="x unified",
                       yaxis=dict(title="0050 價格"), yaxis2=dict(title="正2 累積報酬 (%)", overlaying="y", side="right", tickformat=".0%", showgrid=False),
                       legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"))
    st.plotly_chart(fig1, use_container_width=True)

    # --- 第二張圖：0050 vs 00632R (反一) ---
    st.markdown("#### 2️⃣ 0050 價格 (左軸) vs 00632R 累積報酬 (右軸)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="0050 價格", line=dict(color="#636EFA", width=2)))
    fig2.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_window}SMA", line=dict(color="#FFA15A", width=1.5)))
    fig2.add_trace(go.Scatter(x=df.index, y=df["Cum_Bear_Pct"], name="反一 累積報酬", yaxis="y2", line=dict(dash='dashdot', color="#EF553B"), opacity=0.4))
    
    fig2.add_trace(go.Scatter(x=switch_to_bear.index, y=switch_to_bear["Price_base"], mode="markers", name="轉向反一", marker=dict(symbol="triangle-down", size=12, color="red")))
    if not early_profit_pts.empty:
        fig2.add_trace(go.Scatter(x=early_profit_pts.index, y=early_profit_pts["Price_base"], mode="markers", name="⭐ 結束反一 (獲利)", marker=dict(symbol="star", size=10, color="gold")))
    if not early_drop_pts.empty:
        fig2.add_trace(go.Scatter(x=early_drop_pts.index, y=early_drop_pts["Price_base"], mode="markers", name="🔥 結束反一 (乖離)", marker=dict(symbol="diamond", size=10, color="red")))

    fig2.update_layout(template="plotly_white", height=450, hovermode="x unified",
                       yaxis=dict(title="0050 價格"), yaxis2=dict(title="反一 累積報酬 (%)", overlaying="y", side="right", tickformat=".0%", showgrid=False),
                       legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"))
    st.plotly_chart(fig2, use_container_width=True)

    ###############################################################
    # 6. 視覺化：資金曲線與風險解析 (四個 Tabs)
    ###############################################################
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_eq, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])
    
    with tab_eq:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]-1, name="多空切換策略", line=dict(width=3, color="#636EFA")))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_0050"]-1, name="0050 B&H", line=dict(width=1.5, color="#AB63FA", dash="dash")))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Bull_BH"]-1, name="正2 B&H", line=dict(width=1.5, color="#00CC96"), opacity=0.5))
        
        fig_eq.update_layout(template="plotly_white", height=450, yaxis=dict(title="累積報酬率", tickformat=".0%"), hovermode="x unified")
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab_dd:
        dd_strat = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1)
        dd_0050 = (df["Equity_0050"] / df["Equity_0050"].cummax() - 1)
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_strat, name="策略回撤", fill="tozeroy", line=dict(color="#EF553B")))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_0050, name="0050 回撤", line=dict(color="gray")))
        fig_dd.update_layout(template="plotly_white", height=450, yaxis=dict(title="回撤幅度", tickformat=".0%"))
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe Ratio", "Sortino Ratio", "Calmar Ratio", "低波動性 (反轉)"]
        
        def get_full_stats(eq, rets):
            years = (df.index[-1] - df.index[0]).days / 365
            f_ret = eq.iloc[-1] - 1
            cagr = (1 + f_ret)**(1/years) - 1 if years > 0 else 0
            mdd = 1 - (eq / eq.cummax()).min()
            vol, sharpe, sortino = calc_metrics(rets)
            calmar = cagr / mdd if mdd > 0 else 0
            return [eq.iloc[-1]*capital, f_ret, cagr, calmar, mdd, vol, sharpe, sortino]

        # 準備資料
        stats_strat = get_full_stats(df["Equity_Strategy"], df["Strategy_Ret"])
        stats_bull = get_full_stats(df["Equity_Bull_BH"], df["Ret_bull"])
        stats_base = get_full_stats(df["Equity_0050"], df["Price_base"].pct_change().fillna(0))

        def normalize_radar(stats_list):
            c = nz(stats_list[2]) * 2
            s = nz(stats_list[6])
            so = nz(stats_list[7])
            cal = nz(stats_list[3])
            v_inv = 1 / (nz(stats_list[5]) + 0.1) 
            return [c, s, so, cal, v_inv]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=normalize_radar(stats_strat), theta=radar_categories, fill='toself', name='多空策略', line=dict(color='#636EFA')))
        fig_radar.add_trace(go.Scatterpolar(r=normalize_radar(stats_bull), theta=radar_categories, fill='toself', name='正2 BH', line=dict(color='#00CC96')))
        fig_radar.add_trace(go.Scatterpolar(r=normalize_radar(stats_base), theta=radar_categories, fill='toself', name='0050 BH', line=dict(color='gray', dash='dot')))
        
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=False)), showlegend=True, height=450, margin=dict(t=40, b=40))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Strategy_Ret"]*100, name="多空策略", nbinsx=60, marker_color='#636EFA', opacity=0.75))
        fig_hist.add_trace(go.Histogram(x=df["Ret_bull"]*100, name="正2", nbinsx=60, marker_color='#00CC96', opacity=0.4))
        fig_hist.update_layout(template="plotly_white", barmode='overlay', height=450, xaxis=dict(title="日漲跌幅 (%)"), yaxis=dict(title="出現天數"))
        st.plotly_chart(fig_hist, use_container_width=True)

    ###############################################################
    # 7. 高級比較表格
    ###############################################################
    st.markdown("### 🏆 策略指標深度對比")
    
    metrics_labels = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio"]
    data_dict = {
        "多空切換策略": stats_strat,
        "正2 Buy & Hold": stats_bull,
        "0050 Buy & Hold": stats_base
    }
    
    df_compare = pd.DataFrame(data_dict, index=metrics_labels)

    html_table = """
    <style>
        .win {font-weight: 900; color: #d4af37;}
        .comp-table {width: 100%; border-collapse: collapse; font-family: sans-serif; margin-bottom: 1rem;}
        .comp-table th {background-color: rgba(128,128,128,0.05); padding: 14px; text-align: center; border-bottom: 2px solid #ddd;}
        .comp-table td {padding: 12px; text-align: center; border-bottom: 1px solid rgba(128,128,128,0.1);}
        .metric-col {text-align: left !important; font-weight: bold; width: 25%;}
    </style>
    <table class='comp-table'><tr><th class='metric-col'>指標</th>
    """
    for col in df_compare.columns:
        html_table += f"<th>{col}</th>"
    html_table += "</tr>"

    for metric in metrics_labels:
        row_vals = df_compare.loc[metric].values
        # 判斷好壞 (MDD 與 波動率 越小越好)
        is_invert = metric in ["最大回撤 (MDD)", "年化波動"]
        best_val = min(row_vals) if is_invert else max(row_vals)
        
        html_table += f"<tr><td class='metric-col'>{metric}</td>"
        for val in row_vals:
            # 格式化數值
            if "資產" in metric: display_val = fmt_money(val)
            elif any(x in metric for x in ["Ratio", "Sharpe", "Sortino"]): display_val = fmt_num(val)
            else: display_val = fmt_pct(val)
            
            # 標註冠軍
            if val == best_val:
                html_table += f"<td class='win'>{display_val} 🏆</td>"
            else:
                html_table += f"<td>{display_val}</td>"
        html_table += "</tr>"
    html_table += "</table>"
    
    st.write(html_table, unsafe_allow_html=True)

    ###############################################################
    # 8. 下載與 Footer
    ###############################################################
    st.markdown("<br>", unsafe_allow_html=True)
    
    export_df = df[["Price_base", "SMA", "Price_bull", "Price_bear", "Signal", "Early_Exit", "Equity_Strategy", "Equity_Bull_BH", "Equity_0050"]]
    csv_data = export_df.to_csv(index=True).encode('utf-8-sig')
    
    st.download_button(
        label="📥 下載詳細回測數據 (CSV)",
        data=csv_data,
        file_name=f"0050_LongShort_Backtest.csv",
        mime="text/csv"
    )
    
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align: center; color: gray; font-size: 0.85rem;">
        <p>免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。投資必定有風險，過去之績效不保證未來表現。</p>
        <p>倉鼠人生實驗室 © 2026</p>
    </div>
    """, unsafe_allow_html=True)
