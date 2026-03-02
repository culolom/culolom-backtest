###############################################################
# app.py — 0050LRS 趨勢保護版 (專業戰情室 UI + 絕對獲利邏輯)
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

# ------------------------------------------------------
# 字型與頁面設定
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="0050LRS 趨勢保護版", page_icon="📈", layout="wide")

# 🔒 驗證守門員
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import auth 
    if not auth.check_password(): st.stop()
except: pass 

# ------------------------------------------------------
# 側邊欄：僅放資訊與連結
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 趨勢保護版</h1>", unsafe_allow_html=True)
st.markdown("""
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold<br>
2️⃣ 槓桿 ETF Buy & Hold<br>
3️⃣ <b>LRS 趨勢保護策略</b>：結合 SMA 均線停損與「絕對獲利才停利」的波段策略。
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 資料與工具函式
# ------------------------------------------------------
BASE_ETFS = {"0050 元大台灣50": "0050.TW", "006208 富邦台50": "006208.TW"}
LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW", "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW", "00685L 群益台灣加權正2": "00685L.TW",
}
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

def calc_metrics(series: pd.Series):
    daily = series.dropna()
    if len(daily) <= 1: return np.nan, np.nan, np.nan
    avg, std = daily.mean(), daily.std()
    downside = daily[daily < 0].std()
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def fmt_money(v): return f"{v:,.0f} 元" if pd.notnull(v) else "—"
def fmt_pct(v, d=2): return f"{v:.{d}%}" if pd.notnull(v) else "—"
def fmt_num(v, d=2): return f"{v:.{d}f}" if pd.notnull(v) else "—"
def fmt_int(v): return f"{int(v):,}" if pd.notnull(v) else "—"
def nz(x, default=0.0): return float(np.nan_to_num(x, nan=default))

# ------------------------------------------------------
# 主頁面：參數設定區
# ------------------------------------------------------
col1, col2 = st.columns(2)
base_label = col1.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
lev_label = col2.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_ETFS.keys()))
base_symbol, lev_symbol = BASE_ETFS[base_label], LEV_ETFS[lev_label]

df_base_raw = load_csv(base_symbol)
df_lev_raw = load_csv(lev_symbol)
if df_base_raw.empty or df_lev_raw.empty:
    st.error("⚠️ 資料讀取失敗")
    st.stop()

s_min = max(df_base_raw.index.min().date(), df_lev_raw.index.min().date())
s_max = min(df_base_raw.index.max().date(), df_lev_raw.index.max().date())
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col3, col4, col5, col6 = st.columns(4)
start = col3.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)))
end = col4.date_input("結束日期", value=s_max)
capital = col5.number_input("投入本金（元）", 1000, 10000000, 100000, step=10000)
sma_window = col6.number_input("均線週期 (SMA)", 10, 300, 200, step=10)

st.write("---")
st.markdown("### ⚙️ 進出場閾值設定")
col_set1, col_set2 = st.columns(2)
# 改回你喜歡的 st.number_input
buy_pct = col_set1.number_input("進場：低點反彈 (%)", 0.5, 30.0, 9.0, step=0.5)
sell_pct = col_set2.number_input("出場：高點回落 (%)", 0.5, 30.0, 15.0, step=0.5)

# ------------------------------------------------------
# 回測核心引擎 (趨勢保護 + 絕對獲利邏輯)
# ------------------------------------------------------
if st.button("開始回測 🚀", use_container_width=True):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    
    df = pd.DataFrame(index=df_base_raw.loc[start_early:end].index)
    df["Price_base"] = df_base_raw["Price"]
    df = df.join(df_lev_raw["Price"].rename("Price_lev"), how="inner").sort_index()
    
    df["MA_Signal"] = df["Price_base"].rolling(sma_window).mean()
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]

    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)

    # --- 策略狀態變數 ---
    in_position = False
    entry_price_lev = 0.0
    trailing_low_base = df["Price_base"].iloc[0]
    trailing_high_lev = 0.0
    
    sigs, pos = [0] * len(df), [0.0] * len(df)

    for i in range(1, len(df)):
        pb = df["Price_base"].iloc[i]
        pl = df["Price_lev"].iloc[i]
        sma = df["MA_Signal"].iloc[i]

        if not in_position:
            trailing_low_base = min(trailing_low_base, pb)
            # 進場條件：均線之上 + 從低點反彈
            if pb > sma and pb >= trailing_low_base * (1 + buy_pct / 100.0):
                in_position = True
                entry_price_lev = pl
                trailing_high_lev = pl
                sigs[i] = 1
        else:
            trailing_high_lev = max(trailing_high_lev, pl)
            # 出場條件 1：破 SMA 強制停損
            if pb < sma:
                in_position = False
                sigs[i] = -1
                trailing_low_base = pb
            # 出場條件 2：絕對獲利賣出 (高點回落 + 沒賠錢)
            elif pl <= trailing_high_lev * (1 - sell_pct / 100.0) and pl > entry_price_lev:
                in_position = False
                sigs[i] = -1
                trailing_low_base = pb

        pos[i] = 1.0 if in_position else 0.0

    df["Signal"], df["Position"] = sigs, pos

    # --- 資金曲線計算 ---
    equity_lrs = [1.0]
    for i in range(1, len(df)):
        lev_ret = df["Return_lev"].iloc[i]
        equity_lrs.append(equity_lrs[-1] * (1 + lev_ret * df["Position"].iloc[i-1]))

    df["Equity_LRS"] = equity_lrs
    df["Return_LRS"] = df["Equity_LRS"].pct_change().fillna(0)
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()

    df["Pct_Base"] = df["Equity_BH_Base"] - 1
    df["Pct_Lev"] = df["Equity_BH_Lev"] - 1
    df["Pct_LRS"] = df["Equity_LRS"] - 1

    # ------------------------------------------------------
    # 指標與 KPI 計算
    # ------------------------------------------------------
    years_len = (df.index[-1] - df.index[0]).days / 365

    def calc_core(eq, rets):
        final_eq = eq.iloc[-1]
        cagr = (final_eq)**(1/years_len) - 1 if years_len > 0 else np.nan
        mdd = 1 - (eq / eq.cummax()).min()
        vol, sharpe, sortino = calc_metrics(rets)
        calmar = cagr / mdd if mdd > 0 else np.nan
        return final_eq, cagr, mdd, vol, sharpe, sortino, calmar

    eq_lrs, cagr_lrs, mdd_lrs, vol_lrs, sh_lrs, so_lrs, cal_lrs = calc_core(df["Equity_LRS"], df["Return_LRS"])
    eq_lev, cagr_lev, mdd_lev, vol_lev, sh_lev, so_lev, cal_lev = calc_core(df["Equity_BH_Lev"], df["Return_lev"])
    eq_base, cagr_base, mdd_base, vol_base, sh_base, so_base, cal_base = calc_core(df["Equity_BH_Base"], df["Return_base"])

    trades = (df["Signal"] != 0).sum()

    # ------------------------------------------------------
    # 1. 策略訊號與執行價格 (雙軸對照)
    # ------------------------------------------------------
    st.markdown("<h3>📌 策略訊號與執行價格 (雙軸對照)</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label} (左軸)", mode="lines", line=dict(width=2, color="#636EFA")))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_window} 日 SMA", mode="lines", line=dict(width=1.5, color="#FFA15A")))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_lev"], name=f"{lev_label} (右軸)", mode="lines", line=dict(width=1, color="#00CC96", dash='dot'), opacity=0.6, yaxis="y2"))

    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    if not buys.empty:
        fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="買進點", marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white"))))
    if not sells.empty:
        fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="賣出點", marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white"))))

    fig_price.update_layout(
        template="plotly_white", height=450, hovermode="x unified",
        yaxis=dict(title=f"{base_label} 價格", showgrid=True),
        yaxis2=dict(title=f"{lev_label} 價格", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"), margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # ------------------------------------------------------
    # 2. 資金曲線與風險解析 Tabs
    # ------------------------------------------------------
    st.markdown("<h3>📊 資金曲線與風險解析</h3>", unsafe_allow_html=True)
    tab_equity, tab_dd, tab_radar, tab_hist = st.tabs(["資金曲線", "回撤比較", "風險雷達", "日報酬分佈"])

    with tab_equity:
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Base"], mode="lines", name="原型BH"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Lev"], mode="lines", name="槓桿BH"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_LRS"], mode="lines", name="LRS 趨勢保護", line=dict(width=2.5)))
        fig_eq.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab_dd:
        dd_base = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
        dd_lev = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
        dd_lrs = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_base, name="原型BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lev, name="槓桿BH"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_lrs, name="LRS 趨勢保護", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_lrs  = [nz(cagr_lrs), nz(sh_lrs), nz(so_lrs), nz(-mdd_lrs), nz(-vol_lrs)]
        radar_lev  = [nz(cagr_lev), nz(sh_lev), nz(so_lev), nz(-mdd_lev), nz(-vol_lev)]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_lrs, theta=radar_categories, fill='toself', name='LRS 趨勢保護', line=dict(color='#00CC96')))
        fig_radar.add_trace(go.Scatterpolar(r=radar_lev, theta=radar_categories, fill='toself', name='槓桿 BH', line=dict(color='#EF553B')))
        fig_radar.update_layout(height=480, polar=dict(radialaxis=dict(visible=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_LRS"] * 100, name="LRS 趨勢保護", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)
        st.plotly_chart(fig_hist, use_container_width=True)

    # ------------------------------------------------------
    # 3. KPI 總表 (恢復原本的高級 HTML 表格)
    # ------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>LRS 趨勢保護</span>": {
            "期末資產": eq_lrs * capital, "總報酬率": eq_lrs - 1, "CAGR (年化)": cagr_lrs,
            "Calmar Ratio": cal_lrs, "最大回撤 (MDD)": mdd_lrs, "年化波動": vol_lrs,
            "Sharpe Ratio": sh_lrs, "Sortino Ratio": so_lrs, "交易次數": trades,
        },
        f"<b>{lev_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": eq_lev * capital, "總報酬率": eq_lev - 1, "CAGR (年化)": cagr_lev,
            "Calmar Ratio": cal_lev, "最大回撤 (MDD)": mdd_lev, "年化波動": vol_lev,
            "Sharpe Ratio": sh_lev, "Sortino Ratio": so_lev, "交易次數": -1, 
        },
        f"<b>{base_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": eq_base * capital, "總報酬率": eq_base - 1, "CAGR (年化)": cagr_base,
            "Calmar Ratio": cal_base, "最大回撤 (MDD)": mdd_base, "年化波動": vol_base,
            "Sharpe Ratio": sh_base, "Sortino Ratio": so_base, "交易次數": -1,
        }
    }

    df_vertical = pd.DataFrame(data_dict).reindex(metrics_order)

    metrics_config = {
        "期末資產": {"fmt": lambda x: f"{x:,.0f} 元", "invert": False},
        "總報酬率": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "CAGR (年化)": {"fmt": lambda x: f"{x:.2%}", "invert": False},
        "Calmar Ratio": {"fmt": lambda x: f"{x:.2f}", "invert": False},
        "最大回撤 (MDD)": {"fmt": lambda x: f"{x:.2%}", "invert": True},
        "年化波動": {"fmt": lambda x: f"{x:.2%}", "invert": True},
        "Sharpe Ratio": {"fmt": lambda x: f"{x:.2f}", "invert": False},
        "Sortino Ratio": {"fmt": lambda x: f"{x:.2f}", "invert": False},
        "交易次數": {"fmt": lambda x: str(x) if x >= 0 else "—", "invert": True} 
    }

    html_code = """
    <style>
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid #f0f0f0; font-family: 'Noto Sans TC', sans-serif; margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: #f8f9fa; color: #1a1a1a; padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.metric-name { background-color: transparent; color: #1a1a1a; font-weight: 500; text-align: left; padding: 12px 16px; width: 25%; font-size: 0.9rem; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.data-cell { text-align: center; padding: 12px; color: #1a1a1a; border-bottom: 1px solid rgba(128,128,128, 0.1); }
        .comparison-table td.lrs-col { background-color: rgba(128, 128, 128, 0.03); }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255, 215, 0, 0.4); }
    </style>
    <table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>
    """
    for col_name in df_vertical.columns: html_code += f"<th>{col_name}</th>"
    html_code += "</tr></thead><tbody>"

    for metric in df_vertical.index:
        config = metrics_config.get(metric)
        raw_vals = df_vertical.loc[metric].values
        valid_vals = [x for x in raw_vals if isinstance(x, (int, float)) and x != -1 and not pd.isna(x)]
        
        target_val = None
        if valid_vals and metric != "交易次數":
            target_val = min(valid_vals) if config["invert"] else max(valid_vals)

        html_code += f"<tr><td class='metric-name'>{metric}</td>"
        for i, strategy in enumerate(df_vertical.columns):
            val = df_vertical.at[metric, strategy]
            display_text = config["fmt"](val) if isinstance(val, (int, float)) and val != -1 else "—"
            
            is_winner = (target_val is not None and val == target_val)
            if is_winner: display_text += " <span class='trophy-icon'>🏆</span>"
            
            lrs_class = "lrs-col" if i == 0 else ""
            font_weight = "bold" if i == 0 else "normal"
            html_code += f"<td class='data-cell {lrs_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        html_code += "</tr>"

    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)

    # ------------------------------------------------------
    # 4. 下載 CSV 按鈕
    # ------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    export_cols = ["Price_base", "Price_lev", "MA_Signal", "Signal", "Position", "Equity_BH_Base", "Equity_BH_Lev", "Equity_LRS"]
    valid_cols = [c for c in export_cols if c in df.columns]
    csv_data = df[valid_cols].to_csv(index=True).encode('utf-8-sig')
    
    st.download_button(
        label="📥 下載詳細回測數據 (CSV)",
        data=csv_data,
        file_name=f"LRS_Backtest_{base_symbol}_{start}_{end}.csv",
        mime="text/csv"
    )

    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown("""<div style="text-align: center; color: gray; font-size: 0.85rem;"><p style="font-style: italic;">免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。</p></div>""", unsafe_allow_html=True)
