###############################################################
# app.py — 0050LRS 回測 (Ultimate UX/UI Edition)
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

###############################################################
# 1. 全域設定與 CSS 美化
###############################################################

# 字型設定
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# Streamlit 設定
st.set_page_config(
    page_title="0050LRS 戰情室",
    page_icon="📈",
    layout="wide",
)

# --- CSS Hack: 卡片式設計與優化 ---
st.markdown("""
<style>
    /* 調整 Metric 樣式 */
    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 700;
        font-family: 'Roboto Mono', monospace; /* 數字使用等寬字體 */
    }
    [data-testid="stMetricDelta"] {
        font-weight: 600;
    }
    
    /* 自定義卡片容器樣式 (給 Heat Square 用) */
    .metric-card {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        border-color: rgba(255, 255, 255, 0.3);
    }
    
    /* 表格字體優化 */
    [data-testid="stDataFrame"] {
        font-family: 'Noto Sans TC', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# 常數定義
BASE_ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
}

LEV_ETFS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW",
}

WINDOW = 200
DATA_DIR = Path("data")

###############################################################
# 2. 工具函式
###############################################################

def fmt_money(v):
    return f"{v:,.0f}" if not np.isnan(v) else "—"

def fmt_pct(v, d=2):
    return f"{v:.{d}%}" if not np.isnan(v) else "—"

def fmt_num(v, d=2):
    return f"{v:.{d}f}" if not np.isnan(v) else "—"

def nz(x, default=0.0):
    return float(np.nan_to_num(x, nan=default))

def calc_metrics_series(daily_series: pd.Series):
    """計算單一序列的各種風險指標"""
    daily = daily_series.dropna()
    if len(daily) <= 1:
        return np.nan, np.nan, np.nan
    
    avg = daily.mean()
    std = daily.std()
    downside = daily[daily < 0].std()
    
    vol = std * np.sqrt(252)
    sharpe = (avg / std) * np.sqrt(252) if std > 0 else np.nan
    sortino = (avg / downside) * np.sqrt(252) if downside > 0 else np.nan
    return vol, sharpe, sortino

def calc_performance_summary(equity_series, ret_series, years_len):
    """計算並回傳完整的績效 Dict"""
    final_eq = equity_series.iloc[-1]
    final_ret = final_eq - 1
    cagr = (1 + final_ret) ** (1 / years_len) - 1 if years_len > 0 else np.nan
    
    # MDD 計算
    roll_max = equity_series.cummax()
    drawdown = equity_series / roll_max - 1
    mdd = -drawdown.min()
    
    vol, sharpe, sortino = calc_metrics_series(ret_series)
    calmar = cagr / mdd if mdd > 0 else np.nan
    
    return {
        "final_equity_mult": final_eq,
        "total_return": final_ret,
        "cagr": cagr,
        "mdd": mdd,
        "vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar
    }

# --- 色盲友善配色邏輯 (Blue / Orange) ---

def _hs_color_gen(values, color_type="blue"):
    """
    根據數值生成 RGBA 顏色字串
    color_type: "blue" (正向指標) or "orange" (風險指標)
    """
    vmin, vmax = min(values), max(values)
    span = vmax - vmin if vmax != vmin else 1.0
    
    colors = []
    for v in values:
        t = (v - vmin) / span
        
        if color_type == "blue":
            # Royal Blue: #2563EB (RGB: 37, 99, 235)
            # 讓顏色稍微亮一點，避免在黑底太暗
            base_r, base_g, base_b = 59, 130, 246 
            alpha = 0.2 + 0.8 * t 
        elif color_type == "orange":
            # Orange: #F97316 (RGB: 249, 115, 22)
            base_r, base_g, base_b = 249, 115, 22
            alpha = 0.2 + 0.8 * t
            
        colors.append(f"rgba({base_r},{base_g},{base_b},{alpha:.2f})")
    return colors

def render_heat_square(metrics_data):
    names = list(metrics_data.keys())
    
    vals_final = [metrics_data[n]["final_equity_mult"] for n in names]
    vals_cagr = [metrics_data[n]["cagr"] for n in names]
    vals_sharpe = [metrics_data[n]["sharpe"] for n in names]
    vals_sortino = [metrics_data[n]["sortino"] for n in names]
    vals_mdd = [metrics_data[n]["mdd"] for n in names]
    vals_vol = [metrics_data[n]["vol"] for n in names]

    # 生成顏色
    c_final = _hs_color_gen(vals_final, "blue")
    c_cagr  = _hs_color_gen(vals_cagr, "blue")
    c_shrp  = _hs_color_gen(vals_sharpe, "blue")
    c_sort  = _hs_color_gen(vals_sortino, "blue")
    c_mdd   = _hs_color_gen(vals_mdd, "orange")
    c_vol   = _hs_color_gen(vals_vol, "orange")

    # 產生 HTML (使用 flex-wrap 與新的 metric-card class)
    html_blocks = []
    for i, name in enumerate(names):
        # 為了避免 Markdown 縮排問題，這裡寫成緊湊格式
        # 注意 style 中的 color:white，確保深色背景可讀性
        block = (
            f'<div class="metric-card" style="flex:1; min-width:200px;">'
            f'<div style="font-size:14px;margin-bottom:12px;color:#e5e7eb;font-weight:bold;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:8px;">{name}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;">'
            f'<div style="padding:6px 10px;background:{c_final[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">💰 資產</div>'
            f'<div style="padding:6px 10px;background:{c_cagr[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">📈 CAGR</div>'
            f'<div style="padding:6px 10px;background:{c_shrp[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">⚖️ Sharpe</div>'
            f'<div style="padding:6px 10px;background:{c_sort[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">🛡️ Sortino</div>'
            f'<div style="padding:6px 10px;background:{c_mdd[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">📉 MDD</div>'
            f'<div style="padding:6px 10px;background:{c_vol[i]};color:white;border-radius:6px;font-size:13px;font-weight:500;">⚡ Vol</div>'
            f'</div>'
            f'</div>'
        )
        html_blocks.append(block)
    
    return f"<div style='display:flex;gap:16px;margin-top:8px;flex-wrap:wrap;'>{''.join(html_blocks)}</div>"

###############################################################
# 3. 資料處理與核心邏輯 (Vectorized)
###############################################################

@st.cache_data(ttl=3600)
def load_data(base_symbol: str, lev_symbol: str):
    path_base = DATA_DIR / f"{base_symbol}.csv"
    path_lev = DATA_DIR / f"{lev_symbol}.csv"
    
    if not path_base.exists() or not path_lev.exists():
        return pd.DataFrame()

    df_base = pd.read_csv(path_base, parse_dates=["Date"], index_col="Date")
    df_base = df_base.sort_index()[["Close"]].rename(columns={"Close": "Price_base"})
    
    df_lev = pd.read_csv(path_lev, parse_dates=["Date"], index_col="Date")
    df_lev = df_lev.sort_index()[["Close"]].rename(columns={"Close": "Price_lev"})
    
    df = df_base.join(df_lev, how="inner")
    df["MA_200"] = df["Price_base"].rolling(WINDOW).mean()
    return df.dropna(subset=["MA_200"])

def run_backtest_vectorized(df_input, start_date, end_date, initial_pos_full=False):
    df = df_input.loc[start_date:end_date].copy()
    if df.empty: return df
    
    df["Return_base"] = df["Price_base"].pct_change().fillna(0)
    df["Return_lev"] = df["Price_lev"].pct_change().fillna(0)
    
    # 邏輯
    raw_signal = (df["Price_base"] > df["MA_200"]).astype(int)
    df["Position"] = raw_signal
    df["Strategy_Ret"] = df["Position"].shift(1).fillna(0 if not initial_pos_full else 1) * df["Return_lev"]
    
    df["Equity_LRS"] = (1 + df["Strategy_Ret"]).cumprod()
    df["Equity_BH_Lev"] = (1 + df["Return_lev"]).cumprod()
    df["Equity_BH_Base"] = (1 + df["Return_base"]).cumprod()
    
    df["DD_LRS"] = (df["Equity_LRS"] / df["Equity_LRS"].cummax() - 1) * 100
    df["DD_Lev"] = (df["Equity_BH_Lev"] / df["Equity_BH_Lev"].cummax() - 1) * 100
    df["DD_Base"] = (df["Equity_BH_Base"] / df["Equity_BH_Base"].cummax() - 1) * 100
    
    df["Trade_Action"] = df["Position"].diff()
    return df

###############################################################
# 4. 圖表繪製 (Visualization - Blue/Orange Theme)
###############################################################

def plot_price_ma(df, base_label):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name=f"{base_label} 收盤價", line=dict(width=1.5, color='#9CA3AF')))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200 日 SMA", line=dict(color='#F59E0B', width=1.5))) # Amber
    
    buys = df[df["Trade_Action"] == 1]
    sells = df[df["Trade_Action"] == -1]
    
    if not buys.empty:
        fig.add_trace(go.Scatter(x=buys.index, y=buys["Price_base"], mode="markers", name="買進 Buy", marker=dict(color="#3B82F6", size=8, symbol="triangle-up")))
    if not sells.empty:
        fig.add_trace(go.Scatter(x=sells.index, y=sells["Price_base"], mode="markers", name="賣出 Sell", marker=dict(color="#EF4444", size=8, symbol="triangle-down")))
        
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_equity(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Base"]-1, name="原型 BH", line=dict(color='#9CA3AF', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH_Lev"]-1, name="槓桿 BH", line=dict(color='#F97316', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_LRS"]-1, name="LRS 策略", line=dict(color='#2563EB', width=2)))
    fig.update_layout(template="plotly_white", height=420, yaxis=dict(tickformat=".0%"), margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_drawdown(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_Base"], name="原型 BH", line=dict(color='#9CA3AF', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_Lev"], name="槓桿 BH", line=dict(color='#F97316', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df["DD_LRS"], name="LRS 策略", fill="tozeroy", line=dict(color='#2563EB', width=1)))
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h", y=1.02))
    return fig

def plot_radar(metrics_dict):
    categories = ["CAGR", "Sharpe", "Sortino", "-MDD", "波動率(反轉)"]
    fig = go.Figure()
    
    colors = {'LRS 策略': '#2563EB', list(metrics_dict.keys())[1]: '#F97316', list(metrics_dict.keys())[2]: '#9CA3AF'}
    
    for name, m in metrics_dict.items():
        vals = [
            nz(m["cagr"]), nz(m["sharpe"]), nz(m["sortino"]),
            nz(-m["mdd"]), nz(-m["vol"])
        ]
        color = colors.get(name, 'gray')
        fig.add_trace(go.Scatterpolar(r=vals, theta=categories, fill="toself", name=name, line=dict(color=color)))
        
    fig.update_layout(template="plotly_white", height=450, polar=dict(radialaxis=dict(visible=True, range=[-1, 2])), margin=dict(t=20, b=20))
    return fig

def plot_histogram(df):
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df["Return_base"] * 100, name="原型BH", opacity=0.5, marker_color='#9CA3AF'))
    fig.add_trace(go.Histogram(x=df["Return_lev"] * 100, name="槓桿BH", opacity=0.5, marker_color='#F97316'))
    fig.add_trace(go.Histogram(x=df["Strategy_Ret"] * 100, name="LRS", opacity=0.6, marker_color='#2563EB'))
    fig.update_layout(barmode="overlay", template="plotly_white", height=450, margin=dict(t=20, b=20))
    return fig

###############################################################
# 5. Streamlit 主程式 (Main Layout)
###############################################################

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 戰情室</h1>", unsafe_allow_html=True)
st.markdown("""
<b>本工具比較三種策略：</b><br>
1️⃣ 原型 ETF Buy & Hold (Benchmark) <span style='color:#9CA3AF'>■</span><br>
2️⃣ 槓桿 ETF Buy & Hold <span style='color:#F97316'>■</span><br>
3️⃣ <b>槓桿 ETF LRS 策略</b> (依據原型 200MA 進出) <span style='color:#2563EB'>■</span><br>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    base_label = st.selectbox("原型 ETF（訊號來源）", list(BASE_ETFS.keys()))
    base_symbol = BASE_ETFS[base_label]
with col2:
    lev_label = st.selectbox("槓桿 ETF（實際交易）", list(LEV_ETFS.keys()))
    lev_symbol = LEV_ETFS[lev_label]

df_preview = load_data(base_symbol, lev_symbol)
if not df_preview.empty:
    s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
    st.info(f"📌 資料庫區間：{s_min} ~ {s_max}")
else:
    s_min, s_max = dt.date(2012, 1, 1), dt.date.today()
    st.warning("⚠️ 尚未找到對應 CSV，請確認 data 資料夾")

col3, col4, col5 = st.columns(3)
with col3:
    start_input = st.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5 * 365)), min_value=s_min, max_value=s_max)
with col4:
    end_input = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
with col5:
    capital = st.number_input("投入本金（元）", 1000, 10_000_000, 100_000, step=10_000)

position_mode = st.radio("策略初始狀態", ["空手起跑 (標準 LRS)", "一開始就全倉 (模擬滿倉)"], index=0, horizontal=True)

st.divider()

if st.button("開始回測 🚀", type="primary", use_container_width=True):
    
    if df_preview.empty:
        st.error("資料讀取失敗，無法回測")
        st.stop()

    with st.spinner("🚀 正在進行運算..."):
        is_full_start = "全倉" in position_mode
        df_res = run_backtest_vectorized(df_preview, start_input, end_input, initial_pos_full=is_full_start)
        
        if df_res.empty:
            st.error("選定區間無資料")
            st.stop()
            
        years_len = (df_res.index[-1] - df_res.index[0]).days / 365.25
        
        perf_lrs = calc_performance_summary(df_res["Equity_LRS"], df_res["Strategy_Ret"], years_len)
        perf_lev = calc_performance_summary(df_res["Equity_BH_Lev"], df_res["Return_lev"], years_len)
        perf_base = calc_performance_summary(df_res["Equity_BH_Base"], df_res["Return_base"], years_len)
        
        trade_count = df_res["Trade_Action"].abs().sum() / 2
        
    # --- UI 顯示層 ---
    
    st.markdown("### 📈 價格與訊號檢視")
    st.plotly_chart(plot_price_ma(df_res, base_label), use_container_width=True)
    
    st.markdown("### 📊 策略深度分析")
    t1, t2, t3, t4 = st.tabs(["資金曲線", "回撤分析", "風險雷達", "報酬分佈"])
    
    metrics_bundle = {
        "LRS 策略": perf_lrs,
        f"Buy&Hold ({lev_label.split()[0]})": perf_lev,
        f"Buy&Hold ({base_label.split()[0]})": perf_base
    }
    
    with t1: st.plotly_chart(plot_equity(df_res), use_container_width=True)
    with t2: st.plotly_chart(plot_drawdown(df_res), use_container_width=True)
    with t3: st.plotly_chart(plot_radar(metrics_bundle), use_container_width=True)
    with t4: st.plotly_chart(plot_histogram(df_res), use_container_width=True)

    c_final = capital * perf_lrs["final_equity_mult"]
    c_lev_final = capital * perf_lev["final_equity_mult"]
    
    st.markdown("### 🏆 績效總結")
    
    # 簡潔有力的 KPI
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 LRS 期末資產", fmt_money(c_final), f"{(c_final/c_lev_final - 1)*100:+.1f}% vs BH")
    m2.metric("📈 CAGR", fmt_pct(perf_lrs["cagr"]), f"{(perf_lrs['cagr'] - perf_lev['cagr'])*100:+.1f}%")
    m3.metric("📉 Max Drawdown", fmt_pct(perf_lrs["mdd"]), f"{(perf_lrs['mdd'] - perf_lev['mdd'])*100:+.1f}%", delta_color="inverse")
    m4.metric("⚖️ Sharpe Ratio", fmt_num(perf_lrs["sharpe"]), f"{perf_lrs['sharpe'] - perf_lev['sharpe']:+.2f}")
    
    st.markdown("#### 🔥 策略強弱矩陣 (藍=優 / 橘=風險)")
    st.markdown(render_heat_square(metrics_bundle), unsafe_allow_html=True)
    


    st.markdown("#### 📋 詳細數據表")
    
    table_data = []
    for name, p in metrics_bundle.items():
        row = {
            "策略": name,
            "💰 期末資產": capital * p["final_equity_mult"],
            "📈 CAGR": p["cagr"],
            "📉 MDD": p["mdd"],
            "⚖️ Sharpe": p["sharpe"],
            "🛡️ Sortino": p["sortino"],
            "⚡ 波動率": p["vol"],
            "🌊 Calmar": p["calmar"],
            "總報酬率": p["total_return"]
        }
        table_data.append(row)
    
    df_table = pd.DataFrame(table_data).set_index("策略")
    
    # 修正步驟 1：先對 DataFrame 應用顏色樣式 (建立 Styler)
    styler = df_table.style\
        .background_gradient(cmap="Blues", subset=["💰 期末資產", "📈 CAGR", "⚖️ Sharpe", "🛡️ Sortino", "🌊 Calmar"])\
        .background_gradient(cmap="Oranges", subset=["📉 MDD", "⚡ 波動率"])

    # 修正步驟 2：再將 Styler 物件傳入 st.dataframe 進行格式化顯示
    st.dataframe(
        styler,
        use_container_width=True,
        column_config={
            "💰 期末資產": st.column_config.NumberColumn(format="$%d"),
            "📈 CAGR": st.column_config.NumberColumn(format="%.2f%%"),
            "📉 MDD": st.column_config.NumberColumn(format="%.2f%%"),
            "⚡ 波動率": st.column_config.NumberColumn(format="%.2f%%"),
            "總報酬率": st.column_config.NumberColumn(format="%.2f%%"),
            "⚖️ Sharpe": st.column_config.NumberColumn(format="%.2f"),
            "🛡️ Sortino": st.column_config.NumberColumn(format="%.2f"),
            "🌊 Calmar": st.column_config.NumberColumn(format="%.2f"),
        }
    )
