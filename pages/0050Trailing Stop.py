import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# --- 1. 環境與版面配置 ---
st.set_page_config(page_title="0050LRS 趨勢保護版", page_icon="📈", layout="wide")

TICKER_NAMES = {
    "0050.TW": "0050 元大台灣50",
    "006208.TW": "006208 富邦台50",
    "00631L.TW": "00631L 元大台灣50正2",
    "00663L.TW": "00663L 國泰台灣加權正2",
    "00675L.TW": "00675L 富邦台灣加權正2",
    "00685L.TW": "00685L 群益台灣加權正2"
}

# 側邊欄：僅放資訊與連結
with st.sidebar:
    st.markdown("## 倉鼠量化戰情室")
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🌐")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

# 主頁面標題
st.markdown("<h1 style='margin-bottom:0.5em;'>📊 0050LRS 趨勢保護 + 絕對獲利版</h1>", unsafe_allow_html=True)

# --- 2. 數據處理函式 ---
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

def fmt_money(v): return f"{v:,.0f} 元"
def fmt_pct(v, d=2): return f"{v:.{d}%}"
def fmt_num(v, d=2): return f"{v:.{d}f}"

# --- 3. 右側主頁面：參數設定區 ---
with st.container():
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        base_id = st.selectbox("原型 ETF (訊號來源)", ["0050.TW", "006208.TW"], format_func=lambda x: TICKER_NAMES.get(x, x))
    with col_e2:
        lev_id = st.selectbox("槓桿 ETF (實際交易標的)", ["00631L.TW", "00663L.TW", "00675L.TW", "00685L.TW"], format_func=lambda x: TICKER_NAMES.get(x, x))

    df_preview = load_csv(base_id)
    s_min, s_max = df_preview.index.min().date(), df_preview.index.max().date()
    st.info(f"📌 可回測區間：{s_min} ~ {s_max}")

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    start = col_p1.date_input("開始日期", value=max(s_min, s_max - dt.timedelta(days=5*365)))
    end = col_p2.date_input("結束日期", value=s_max)
    capital = col_p3.number_input("投入本金", 1000, 10000000, 100000)
    sma_val = col_p4.number_input("均線週期 (SMA)", 10, 300, 200)

    st.markdown("#### ⚙️ 進出場閾值設定")
    col_set1, col_set2 = st.columns(2)
    buy_pct = col_set1.slider("進場：低點反彈 (%)", 0.5, 15.0, 3.0, 0.5)
    sell_pct = col_set2.slider("出場：高點回落 (%)", 0.5, 15.0, 3.0, 0.5)

# --- 4. 執行回測 ---
if st.button("啟動回測引擎 🚀", use_container_width=True):
    df_base = load_csv(base_id).rename(columns={"Price": "Price_base"})
    df_lev = load_csv(lev_id).rename(columns={"Price": "Price_lev"})
    df = df_base.join(df_lev, how="inner")
    
    df["SMA"] = df["Price_base"].rolling(sma_val).mean()
    df = df.loc[start:end].dropna(subset=["SMA"])

    # 狀態機
    in_pos = False
    cost_price = 0.0
    t_low = df["Price_base"].iloc[0]
    t_high = 0.0
    
    sigs, pos = [0]*len(df), [0.0]*len(df)

    for i in range(1, len(df)):
        pb, pl = df["Price_base"].iloc[i], df["Price_lev"].iloc[i]
        sma = df["SMA"].iloc[i]
        
        if not in_pos:
            t_low = min(t_low, pb)
            if pb > sma and pb >= t_low * (1 + buy_pct/100):
                in_pos, cost_price, t_high, sigs[i] = True, pl, pl, 1
        else:
            t_high = max(t_high, pl)
            # 強制停損
            if pb < sma:
                in_pos, sigs[i], t_low = False, -1, pb
            # 獲利才賣
            elif pl <= t_high * (1 - sell_pct/100) and pl > cost_price:
                in_pos, sigs[i], t_low = False, -1, pb
        pos[i] = 1.0 if in_pos else 0.0

    df["Position"] = pos
    
    # 計算報酬
    equity = [1.0]
    for i in range(1, len(df)):
        ret = (df["Price_lev"].iloc[i] / df["Price_lev"].iloc[i-1]) - 1
        equity.append(equity[-1] * (1 + (ret * df["Position"].iloc[i-1])))
    
    df["Equity"] = equity
    df["Eq_BH_Lev"] = df["Price_lev"] / df["Price_lev"].iloc[0]
    df["Eq_BH_Base"] = df["Price_base"] / df["Price_base"].iloc[0]

    # --- 5. 績效表格顯示 (找回消失的表格) ---
    st.markdown("### 🏆 策略績效總表")
    
    def get_kpis(eq, rets):
        cagr = (eq.iloc[-1])**(1/(len(eq)/252)) - 1
        mdd = 1 - (eq / eq.cummax()).min()
        sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0
        return eq.iloc[-1], cagr, mdd, sharpe

    k_lrs = get_kpis(df["Equity"], df["Equity"].pct_change().fillna(0))
    k_lev = get_kpis(df["Eq_BH_Lev"], df["Price_lev"].pct_change().fillna(0))
    k_base = get_kpis(df["Eq_BH_Base"], df["Price_base"].pct_change().fillna(0))

    metrics = [
        ("期末資產", [k_lrs[0]*capital, k_lev[0]*capital, k_base[0]*capital], fmt_money, False),
        ("CAGR (年化)", [k_lrs[1], k_lev[1], k_base[1]], fmt_pct, False),
        ("最大回撤 (MDD)", [k_lrs[2], k_lev[2], k_base[2]], fmt_pct, True),
        ("Sharpe Ratio", [k_lrs[3], k_lev[3], k_base[3]], fmt_num, False)
    ]

    # 建立 HTML 表格
    html = "<table style='width:100%; border-collapse: collapse; text-align: center;'>"
    html += f"<tr style='background-color: #f8f9fa;'><th>指標</th><th>LRS 趨勢保護</th><th>{lev_id} B&H</th><th>{base_id} B&H</th></tr>"
    
    for label, vals, func, invert in metrics:
        html += f"<tr><td style='padding:12px; border-bottom:1px solid #eee; text-align:left;'><b>{label}</b></td>"
        best_val = min(vals) if invert else max(vals)
        for v in vals:
            is_best = (v == best_val)
            style = "font-weight:bold; color:#1a1a1a;" if is_best else "color:#666;"
            html += f"<td style='padding:12px; border-bottom:1px solid #eee; {style}'>{func(v)}{' 🏆' if is_best else ''}</td>"
        html += "</tr>"
    html += "</table>"
    st.write(html, unsafe_allow_html=True)

    # --- 6. 圖表視覺化 ---
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.4, 0.6])
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity"], name="LRS 策略", line=dict(color="#00D494", width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["Eq_BH_Lev"], name="槓桿 B&H", line=dict(color="#94A3B8", dash="dash")), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df["Price_base"], name="原型股價", line=dict(color="#1E293B")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name=f"{sma_val}SMA", line=dict(color="#F59E0B")), row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)
