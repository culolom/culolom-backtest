###############################################################
# app.py — 單一標的趨勢保護版 (專業戰情室 UI + 絕對獲利邏輯)
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

st.set_page_config(page_title="趨勢保護策略", page_icon="📈", layout="wide")

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

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 趨勢保護與絕對獲利策略</h1>", unsafe_allow_html=True)
st.markdown("""
<b>本工具比較三種績效：</b><br>
1️⃣ <b>趨勢保護策略</b>：直接以交易標的計算 SMA 與反彈幅度，結合「跌破均線停損」與「絕對獲利才停利」的波段策略。<br>
2️⃣ 交易標的 Buy & Hold<br>
3️⃣ 對照標的 Buy & Hold（僅供大盤比較參考）
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 資料與工具函式
# ------------------------------------------------------
ALL_ETFS = {
    "0050 元大台灣50": "0050.TW", 
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW", 
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW", 
    "00685L 群益台灣加權正2": "00685L.TW",
    "BTC-USD 比特幣": "BTC-USD"
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

# ------------------------------------------------------
# 主頁面：參數設定區
# ------------------------------------------------------
col1, col2 = st.columns(2)
target_label = col1.selectbox("🎯 交易標的 (計算 SMA 與進出場)", list(ALL_ETFS.keys()), index=2) # 預設正2
bench_label = col2.selectbox("📊 對照標的 (僅供績效比較)", list(ALL_ETFS.keys()), index=0) # 預設0050
target_symbol, bench_symbol = ALL_ETFS[target_label], ALL_ETFS[bench_label]

df_target_raw = load_csv(target_symbol)
df_bench_raw = load_csv(bench_symbol)
if df_target_raw.empty or df_bench_raw.empty:
    st.error("⚠️ 資料讀取失敗")
    st.stop()

s_min = max(df_target_raw.index.min().date(), df_bench_raw.index.min().date())
s_max = min(df_target_raw.index.max().date(), df_bench_raw.index.max().date())
st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

col3, col4, col5, col6 = st.columns(4)
start = col3.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)))
end = col4.date_input("結束日期", value=s_max)
capital = col5.number_input("投入本金（元）", 1000, 10000000, 100000, step=10000)
sma_window = col6.number_input("均線週期 (SMA)", 10, 300, 200, step=10)

st.write("---")
st.markdown("### ⚙️ 進出場閾值設定")
col_set1, col_set2 = st.columns(2)
buy_pct = col_set1.number_input("進場：低點反彈 (%)", 0.5, 30.0, 9.0, step=0.5)
sell_pct = col_set2.number_input("出場：高點回落 (%)", 0.5, 30.0, 15.0, step=0.5)

# ------------------------------------------------------
# 回測核心引擎 (全權由交易標的驅動)
# ------------------------------------------------------
if st.button("開始回測 🚀", use_container_width=True):
    start_early = start - dt.timedelta(days=int(sma_window * 1.5) + 60)
    
    df = pd.DataFrame(index=df_target_raw.loc[start_early:end].index)
    df["Price_target"] = df_target_raw["Price"]
    df = df.join(df_bench_raw["Price"].rename("Price_bench"), how="inner").sort_index()
    
    # 🌟 關鍵修改：MA 訊號直接由「交易標的」計算
    df["MA_Signal"] = df["Price_target"].rolling(sma_window).mean()
    df = df.dropna(subset=["MA_Signal"]).loc[start:end]

    df["Return_target"] = df["Price_target"].pct_change().fillna(0)
    df["Return_bench"] = df["Price_bench"].pct_change().fillna(0)

    # --- 策略狀態變數 ---
    in_position = False
    entry_price = 0.0
    trailing_low = df["Price_target"].iloc[0]
    trailing_high = 0.0
    
    sigs, pos = [0] * len(df), [0.0] * len(df)

    # 🌟 關鍵修改：進出場判斷全部看 p (Price_target)
    for i in range(1, len(df)):
        p = df["Price_target"].iloc[i]
        sma = df["MA_Signal"].iloc[i]

        if not in_position:
            trailing_low = min(trailing_low, p)
            # 進場條件：均線之上 + 從低點反彈
            if p > sma and p >= trailing_low * (1 + buy_pct / 100.0):
                in_position = True
                entry_price = p
                trailing_high = p
                sigs[i] = 1
        else:
            trailing_high = max(trailing_high, p)
            # 出場條件 1：破 SMA 強制停損
            if p < sma:
                in_position = False
                sigs[i] = -1
                trailing_low = p
            # 出場條件 2：絕對獲利賣出 (高點回落 + 沒賠錢)
            elif p <= trailing_high * (1 - sell_pct / 100.0) and p > entry_price:
                in_position = False
                sigs[i] = -1
                trailing_low = p

        pos[i] = 1.0 if in_position else 0.0

    df["Signal"], df["Position"] = sigs, pos

    # --- 資金曲線計算 ---
    equity_strategy = [1.0]
    for i in range(1, len(df)):
        ret = df["Return_target"].iloc[i]
        equity_strategy.append(equity_strategy[-1] * (1 + ret * df["Position"].iloc[i-1]))

    df["Equity_Strategy"] = equity_strategy
    df["Return_Strategy"] = df["Equity_Strategy"].pct_change().fillna(0)
    df["Equity_BH_Target"] = (1 + df["Return_target"]).cumprod()
    df["Equity_BH_Bench"] = (1 + df["Return_bench"]).cumprod()

    df["Pct_Strategy"] = df["Equity_Strategy"] - 1
    df["Pct_Target"] = df["Equity_BH_Target"] - 1
    df["Pct_Bench"] = df["Equity_BH_Bench"] - 1

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

    eq_str, cagr_str, mdd_str, vol_str, sh_str, so_str, cal_str = calc_core(df["Equity_Strategy"], df["Return_Strategy"])
    eq_tgt, cagr_tgt, mdd_tgt, vol_tgt, sh_tgt, so_tgt, cal_tgt = calc_core(df["Equity_BH_Target"], df["Return_target"])
    eq_ben, cagr_ben, mdd_ben, vol_ben, sh_ben, so_ben, cal_ben = calc_core(df["Equity_BH_Bench"], df["Return_bench"])

    trades = (df["Signal"] != 0).sum()

    # ------------------------------------------------------
    # 1. 策略訊號與執行價格 (單軸清晰版)
    # ------------------------------------------------------
    st.markdown("<h3>📌 策略訊號與執行價格</h3>", unsafe_allow_html=True)
    fig_price = go.Figure()
    
    # 🌟 因為訊號和標的都是同一個，不需要雙Y軸了，圖表會變得非常乾淨！
    fig_price.add_trace(go.Scatter(x=df.index, y=df["Price_target"], name=f"{target_label} 價格", mode="lines", line=dict(width=2, color="#636EFA")))
    fig_price.add_trace(go.Scatter(x=df.index, y=df["MA_Signal"], name=f"{sma_window} 日 SMA", mode="lines", line=dict(width=1.5, color="#FFA15A")))

    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    if not buys.empty:
        fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Price_target"], mode="markers", name="買進點", marker=dict(color="#00C853", size=12, symbol="triangle-up", line=dict(width=1, color="white"))))
    if not sells.empty:
        fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Price_target"], mode="markers", name="賣出點", marker=dict(color="#D50000", size=12, symbol="triangle-down", line=dict(width=1, color="white"))))

    fig_price.update_layout(
        template="plotly_white", height=450, hovermode="x unified",
        yaxis=dict(title=f"{target_label} 價格", showgrid=True),
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
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Bench"], mode="lines", name="對照標的 B&H"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Target"], mode="lines", name="交易標的 B&H"))
        fig_eq.add_trace(go.Scatter(x=df.index, y=df["Pct_Strategy"], mode="lines", name="策略趨勢保護", line=dict(width=2.5)))
        fig_eq.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_eq, use_container_width=True)

    with tab_dd:
        dd_bench = (df["Equity_BH_Bench"] / df["Equity_BH_Bench"].cummax() - 1) * 100
        dd_target = (df["Equity_BH_Target"] / df["Equity_BH_Target"].cummax() - 1) * 100
        dd_str = (df["Equity_Strategy"] / df["Equity_Strategy"].cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_bench, name="對照標的 B&H"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_target, name="交易標的 B&H"))
        fig_dd.add_trace(go.Scatter(x=df.index, y=dd_str, name="策略趨勢保護", fill="tozeroy"))
        fig_dd.update_layout(template="plotly_white", height=420)
        st.plotly_chart(fig_dd, use_container_width=True)

    with tab_radar:
        radar_categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
        radar_str = [nz(cagr_str), nz(sh_str), nz(so_str), nz(-mdd_str), nz(-vol_str)]
        radar_tgt = [nz(cagr_tgt), nz(sh_tgt), nz(so_tgt), nz(-mdd_tgt), nz(-vol_tgt)]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=radar_str, theta=radar_categories, fill='toself', name='策略趨勢保護', line=dict(color='#00CC96')))
        fig_radar.add_trace(go.Scatterpolar(r=radar_tgt, theta=radar_categories, fill='toself', name='交易標的 B&H', line=dict(color='#EF553B')))
        fig_radar.update_layout(height=480, polar=dict(radialaxis=dict(visible=True, ticks='')))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_hist:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=df["Return_target"] * 100, name="交易標的 B&H", opacity=0.6))
        fig_hist.add_trace(go.Histogram(x=df["Return_Strategy"] * 100, name="策略趨勢保護", opacity=0.7))
        fig_hist.update_layout(barmode="overlay", template="plotly_white", height=480)
        st.plotly_chart(fig_hist, use_container_width=True)

    # ------------------------------------------------------
    # 3. KPI 總表
    # ------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    
    metrics_order = ["期末資產", "總報酬率", "CAGR (年化)", "Calmar Ratio", "最大回撤 (MDD)", "年化波動", "Sharpe Ratio", "Sortino Ratio", "交易次數"]
    
    data_dict = {
        f"<b>{target_label}</b><br><span style='font-size:0.8em; opacity:0.7'>策略趨勢保護</span>": {
            "期末資產": eq_str * capital, "總報酬率": eq_str - 1, "CAGR (年化)": cagr_str,
            "Calmar Ratio": cal_str, "最大回撤 (MDD)": mdd_str, "年化波動": vol_str,
            "Sharpe Ratio": sh_str, "Sortino Ratio": so_str, "交易次數": trades,
        },
        f"<b>{target_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold</span>": {
            "期末資產": eq_tgt * capital, "總報酬率": eq_tgt - 1, "CAGR (年化)": cagr_tgt,
            "Calmar Ratio": cal_tgt, "最大回撤 (MDD)": mdd_tgt, "年化波動": vol_tgt,
            "Sharpe Ratio": sh_tgt, "Sortino Ratio": so_tgt, "交易次數": -1, 
        },
        f"<b>{bench_label}</b><br><span style='font-size:0.8em; opacity:0.7'>Buy & Hold (對照)</span>": {
            "期末資產": eq_ben * capital, "總報酬率": eq_ben - 1, "CAGR (年化)": cagr_ben,
            "Calmar Ratio": cal_ben, "最大回撤 (MDD)": mdd_ben, "年化波動": vol_ben,
            "Sharpe Ratio": sh_ben, "Sortino Ratio": so_ben, "交易次數": -1,
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
        .comparison-table td.str-col { background-color: rgba(128, 128, 128, 0.03); }
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
            
            str_class = "str-col" if i == 0 else ""
            font_weight = "bold" if i == 0 else "normal"
            html_code += f"<td class='data-cell {str_class}' style='font-weight:{font_weight};'>{display_text}</td>"
        html_code += "</tr>"

    html_code += "</tbody></table>"
    st.write(html_code, unsafe_allow_html=True)

    # ------------------------------------------------------
    # 4. 下載 CSV 按鈕
    # ------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    export_cols = ["Price_target", "MA_Signal", "Signal", "Position", "Equity_BH_Target", "Equity_Strategy", "Equity_BH_Bench"]
    valid_cols = [c for c in export_cols if c in df.columns]
    csv_data = df[valid_cols].to_csv(index=True).encode('utf-8-sig')
    
    st.download_button(
        label="📥 下載詳細回測數據 (CSV)",
        data=csv_data,
        file_name=f"Strategy_Backtest_{target_symbol}_{start}_{end}.csv",
        mime="text/csv"
    )

    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown("""<div style="text-align: center; color: gray; font-size: 0.85rem;"><p style="font-style: italic;">免責聲明：本工具僅供策略回測研究參考，不構成任何形式之投資建議。</p></div>""", unsafe_allow_html=True)
